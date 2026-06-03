/**
 * WhatsApp poster bot (multi-tenant)
 * ==================================
 *
 * Flow (DMs only):
 *   1. A paying tenant DMs the bot with a message starting "new poster"
 *      (case-insensitive). Group messages are ignored.
 *   2. The bot resolves the sender's phone to E.164 and spawns
 *      `python -m imgbot generate --phone <e164>` against the repo root.
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
const TRIGGER = "new poster";
const MAX_TRACKED = 500;

// Dedupe message + message_create.
const seenIds = new Set();

function rememberId(set, id) {
  set.add(id);
  if (set.size > MAX_TRACKED) set.delete(set.values().next().value);
}

function senderPhone(message) {
  // whatsapp-web.js returns IDs like "917974387273@c.us". Strip suffix and
  // re-add the leading + for E.164.
  const raw = (message.from || "").split("@")[0].replace(/\D+/g, "");
  return raw ? `+${raw}` : null;
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
  if (!m.fromMe) handleMessage(m);
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
    if (chat.isGroup) return; // DMs only

    const body = (message.body || "").trim();
    if (!body.toLowerCase().startsWith(TRIGGER)) return;

    const phone = senderPhone(message);
    if (!phone) {
      await message.reply("⚠️ Could not read your phone number from this chat.");
      return;
    }

    console.log("trigger →", phone);
    await message.reply("⏳ Generating your poster…");
    chat.sendStateTyping().catch(() => {});

    let result;
    try {
      result = await runPipeline(phone);
    } catch (err) {
      console.error("pipeline failed:", err.message);
      await message.reply(replyForError(err));
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

function replyForError(err) {
  if (err.errorKind === "not_onboarded") {
    return "⚠️ You're not onboarded yet. Please contact your admin to set up your account.";
  }
  if (err.errorKind === "quota_exceeded") {
    return "⚠️ You've used up this period's quota. Reach out to your admin to top up.";
  }
  return "❌ Generation failed:\n" + truncate(String(err.message), 500);
}

// ---------------------------------------------------------------------------
// Run the Python CLI
// ---------------------------------------------------------------------------
function runPipeline(phone) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      PYTHON,
      ["-m", "imgbot", "generate", "--phone", phone],
      { cwd: REPO_ROOT }
    );
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
