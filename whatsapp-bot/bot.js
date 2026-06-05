/**
 * WhatsApp poster bot (multi-tenant)
 * ==================================
 *
 * Flow (DMs only):
 *   1. A paying tenant DMs the bot with a message starting "new poster"
 *      (case-insensitive). Group messages are ignored.
 *   2. The bot reads `message.from` (the WhatsApp JID — `@c.us` or `@lid`)
 *      and spawns `python -m imgbot generate --chat-id <jid>`. Python's
 *      store.resolve_tenant maps that to the tenant (by chat_id if known,
 *      else by phone-digit fallback), and binds chat_id on first contact.
 *   3. The Python CLI produces one branded poster, prints a legacy
 *      `✓ Final poster -> <abs path>` line, then a single JSON line with
 *      `{image_path, idea_title, quota_remaining}`.
 *   4. The bot sends the file back as a reply, using `idea_title` as the
 *      caption. Local files are cleaned up after delivery.
 *
 * Error handling:
 *   - The CLI uses exit code 2 (not onboarded) and 3 (quota exceeded), with a
 *     JSON error line on stderr. We translate those to user-friendly replies.
 */

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const REPO_ROOT = path.resolve(__dirname, "..");
const PYTHON = process.env.PYTHON_BIN || path.join(REPO_ROOT, ".venv/bin/python");
const DASHBOARD_URL = process.env.IMGBOT_DASHBOARD_URL || "http://127.0.0.1:8000";
const TRIGGER = "new poster";
const MAX_TRACKED = 500;

// Dedupe message + message_create.
const seenIds = new Set();

function rememberId(set, id) {
  set.add(id);
  if (set.size > MAX_TRACKED) set.delete(set.values().next().value);
}

function senderChatId(message) {
  // `message.from` is WhatsApp's canonical chat ID — either `<digits>@c.us`
  // (phone-based) or `<digits>@lid` (Linked Identifier, privacy layer).
  // We treat it as opaque and pass it straight through to Python; the tenant
  // row is keyed on whatever the user pasted into the onboarding form.
  // In groups, `message.from` is the GROUP id and `message.author` is the
  // sender — prefer `author` if present so a future group-DM toggle works.
  const id = (message.author || message.from || "").trim().toLowerCase();
  return id || null;
}

function isNonDmChat(message, chat) {
  // Belt-and-suspenders: whatsapp-web.js's `chat.isGroup` is sometimes false
  // when chat metadata isn't fully hydrated. Check the underlying chat id
  // suffix too — `@g.us` = group, `@newsletter`/`@broadcast` = channels.
  if (chat && chat.isGroup) return true;
  const chatId =
    (chat && chat.id && chat.id._serialized) || message.from || "";
  return (
    chatId.endsWith("@g.us") ||
    chatId.endsWith("@newsletter") ||
    chatId.endsWith("@broadcast")
  );
}

// ---------------------------------------------------------------------------
// WhatsApp client
// ---------------------------------------------------------------------------
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, ".wwebjs_auth") }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  },
});

client.on("qr", (qr) => {
  console.log("\nScan this QR in WhatsApp → Linked devices:\n");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => console.log("authenticated"));
client.on("auth_failure", (m) => console.error("auth failure:", m));
client.on("disconnected", (r) => console.error("disconnected:", r));
client.on("ready", () => {
  const wid = client.info && client.info.wid && client.info.wid._serialized;
  console.log("ready — bot wid:", wid);
});

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------
client.on("message", (m) => handleMessage(m));
client.on("message_create", (m) => {
  // Normally we skip messages WE sent (loop prevention). But during local
  // testing the operator often links the bot to their own WhatsApp account
  // and DMs themself — in that case `fromMe = true` for every test. Allow
  // self-messages ONLY when the body looks like our trigger so the bot can
  // still answer itself for testing without risk of self-talk loops.
  if (!m.fromMe) return handleMessage(m);
  const body = (m.body || "").trim().toLowerCase();
  if (body.startsWith(TRIGGER)) handleMessage(m);
});

async function handleMessage(message) {
  try {
    const msgId = message.id && message.id._serialized;
    if (msgId) {
      if (seenIds.has(msgId)) return;
      rememberId(seenIds, msgId);
    }

    if (message.type !== "chat") return;
    const chat = await message.getChat();
    if (isNonDmChat(message, chat)) {
      // Quiet drop — we don't want to spam groups with "you're not onboarded".
      const chatId = (chat && chat.id && chat.id._serialized) || message.from;
      console.log(`ignored non-DM (${chatId})`);
      return;
    }

    const body = (message.body || "").trim();
    if (!body.toLowerCase().startsWith(TRIGGER)) return;

    const chatId = senderChatId(message);
    if (!chatId) {
      console.warn(
        `could not read chat id (from=${message.from}, author=${message.author || "-"})`
      );
      await message.reply("⚠️ Couldn't read your WhatsApp chat ID from this message.");
      return;
    }

    // In a 1-on-1 DM, `message.from` IS the other party's JID — `@c.us`
    // when their account is phone-based, and its digits are the real phone.
    // The LID (when present) only shows up as `message.author` and is the
    // sender's privacy-layer identifier. We use `from` as the phone source.
    let resolvedPhone = null;
    const fromDigits = (message.from || "").split("@")[0].replace(/\D+/g, "");
    if ((message.from || "").endsWith("@c.us") && fromDigits.length >= 8) {
      resolvedPhone = "+" + fromDigits;
    }

    console.log(
      `trigger → ${chatId}  (from=${message.from}, author=${
        message.author || "-"
      }, phone=${resolvedPhone || "-"})`
    );
    await message.reply("⏳ Generating your poster…");
    chat.sendStateTyping().catch(() => {});

    let result;
    try {
      result = await runPipeline(chatId, resolvedPhone);
    } catch (err) {
      console.error("pipeline failed:", err.message);
      if (err.errorKind === "not_onboarded") {
        // Drop them into the admin's pending inbox so they can be click-onboarded.
        notifyPending(chatId, body);
      }
      await message.reply(replyForError(err, chatId));
      return;
    }

    try {
      const media = MessageMedia.fromFilePath(result.image_path);
      const caption =
        `✅ ${result.idea_title}` +
        (typeof result.quota_remaining === "number"
          ? `\n(${result.quota_remaining} posters left this period)`
          : "");
      await message.reply(media, undefined, { caption });
      cleanupRunFiles(result);
    } catch (err) {
      console.error("send error:", err.message);
      await message.reply(`❌ Failed to send poster: ${err.message}`);
    }
  } catch (err) {
    console.error("handler error:", err.message);
  }
}

async function notifyPending(chatId, lastMessage) {
  // Fire-and-forget POST to the dashboard so the admin sees this chat ID
  // in the /pending inbox. Never block the WhatsApp reply on this.
  try {
    const resp = await fetch(`${DASHBOARD_URL}/api/pending`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, last_message: lastMessage || "" }),
    });
    if (!resp.ok) {
      const txt = await resp.text();
      console.warn(`notifyPending → ${resp.status}: ${truncate(txt, 200)}`);
    }
  } catch (e) {
    console.warn("notifyPending failed:", e.message);
  }
}


function replyForError(err, chatId) {
  if (err.errorKind === "not_onboarded") {
    // Echo the chat ID back so the customer can forward it to their admin in
    // one tap — no need for the admin to dig through the bot terminal logs.
    return (
      "👋 You're not set up yet.\n\n" +
      "Send this WhatsApp ID to your admin so they can activate your account:\n\n" +
      "```\n" + chatId + "\n```"
    );
  }
  if (err.errorKind === "quota_exceeded") {
    return "⚠️ You've used up this period's quota. Reach out to your admin to top up.";
  }
  return "❌ Generation failed:\n" + truncate(String(err.message), 500);
}

// ---------------------------------------------------------------------------
// Run the Python CLI
// ---------------------------------------------------------------------------
function runPipeline(chatId, phoneHint) {
  return new Promise((resolve, reject) => {
    const args = ["-m", "imgbot", "generate", "--chat-id", chatId];
    if (phoneHint) args.push("--phone", phoneHint);
    const child = spawn(PYTHON, args, { cwd: REPO_ROOT });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", reject);
    child.on("close", (code) => {
      // The CLI surfaces structured errors on stderr as a JSON line + non-zero
      // exit codes 2 (not onboarded) / 3 (quota exceeded). Pick up the kind so
      // the user gets a clean message rather than a stack trace.
      const errLine = lastJsonLine(stderr);
      if (errLine && errLine.error) {
        const e = new Error(errLine.message || errLine.error);
        e.errorKind = errLine.error;
        return reject(e);
      }
      if (code !== 0) {
        return reject(new Error(`imgbot generate exited ${code}: ${truncate(stderr || stdout, 800)}`));
      }

      // Success — find the JSON payload line and the legacy path line.
      const payload = lastJsonLine(stdout);
      if (payload && payload.image_path && fs.existsSync(payload.image_path)) {
        return resolve(payload);
      }
      // Fallback to the legacy `Final poster -> <path>` line.
      const m = /✓ Final poster -> (\S+)/.exec(stdout);
      if (m && fs.existsSync(m[1])) {
        return resolve({ image_path: m[1], idea_title: "" });
      }
      reject(new Error("no final poster path found in CLI output"));
    });
  });
}

function lastJsonLine(text) {
  const lines = text.split(/\r?\n/).reverse();
  for (const line of lines) {
    const t = line.trim();
    if (!t.startsWith("{")) continue;
    try {
      return JSON.parse(t);
    } catch (_) {
      // not valid JSON — keep scanning
    }
  }
  return null;
}

function cleanupRunFiles(result) {
  const paths = [result.image_path, result.raw_path].filter(Boolean);
  for (const p of paths) {
    fs.promises.unlink(p).catch(() => {});
  }
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

client.initialize();
