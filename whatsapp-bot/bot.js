/**
 * WhatsApp poster bot
 * ===================
 *
 * Flow (groups only):
 *   1. A user mentions the bot ("@91…") in a group with the words "generate poster".
 *   2. The bot replies "send prompt".
 *   3. The user *replies to that "send prompt" message* with the actual prompt text.
 *      (Only a reply to that exact message counts — all other chatter is ignored.)
 *   4. The bot runs `python3 main.py "<prompt>"` in the repo root and, when the
 *      pipeline finishes, sends the generated poster back as a reply to the
 *      user's prompt message.
 *
 * The bot never touches messages that aren't part of this flow.
 */

const path = require("path");
const { spawn } = require("child_process");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const REPO_ROOT = path.resolve(__dirname, "..");
const PYTHON = process.env.PYTHON_BIN || "python3";
const TRIGGER = "generate poster"; // case-insensitive substring of the mention msg
const ASK_PROMPT_REPLY = "send prompt"; // exactly what the bot replies with

// Message IDs of every "send prompt" message we've posted. A reply that quotes
// one of these is treated as the prompt. Bounded so it can't grow forever.
const askPromptIds = new Set();
const MAX_TRACKED = 500;

// Message IDs we've already handled (dedupes message + message_create events).
const seenIds = new Set();

function rememberAskId(id) {
  askPromptIds.add(id);
  if (askPromptIds.size > MAX_TRACKED) {
    askPromptIds.delete(askPromptIds.values().next().value);
  }
}

// ---------------------------------------------------------------------------
// WhatsApp client
// ---------------------------------------------------------------------------
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, ".wwebjs_auth") }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

client.on("qr", (qr) => {
  console.log("\nScan this QR code in WhatsApp (Linked devices):\n");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => console.log("✓ Authenticated."));
client.on("auth_failure", (m) => console.error("✗ Auth failure:", m));
client.on("disconnected", (r) => console.error("✗ Disconnected:", r));

client.on("ready", () => {
  console.log("✓ Bot is ready. WID:", client.info && client.info.wid._serialized);
});

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------
client.on("message", (message) => handleMessage(message, "message"));
// Some WhatsApp Web builds only deliver group messages via "message_create".
client.on("message_create", (message) => {
  if (message.fromMe) return; // ignore our own outgoing messages
  handleMessage(message, "message_create");
});

async function handleMessage(message, source) {
  try {
    // The same message can arrive via both "message" and "message_create".
    // Process each message id only once.
    const msgId = message.id && message.id._serialized;
    if (msgId) {
      if (seenIds.has(msgId)) return;
      seenIds.add(msgId);
      if (seenIds.size > MAX_TRACKED) seenIds.delete(seenIds.values().next().value);
    }

    const botId = client.info.wid._serialized;
    const botNumber = botId.split("@")[0]; // e.g. "918962109199"
    const chat = await message.getChat();

    // -- DEBUG: dump everything we know about this message ------------------
    console.log("──────────── incoming (" + source + ") ────────────");
    console.log("  from        :", message.from);
    console.log("  author      :", message.author);
    console.log("  fromMe      :", message.fromMe);
    console.log("  isGroup     :", chat.isGroup);
    console.log("  type        :", message.type);
    console.log("  body        :", JSON.stringify(message.body));
    console.log("  mentionedIds:", JSON.stringify(message.mentionedIds));
    console.log("  hasQuotedMsg:", message.hasQuotedMsg);
    console.log("  botId       :", botId, "| botNumber:", botNumber);

    if (!chat.isGroup) {
      console.log("  → skip: not a group");
      return;
    }

    // --- Case A: a reply that quotes one of our "send prompt" messages ----
    if (message.hasQuotedMsg) {
      const quoted = await message.getQuotedMessage();
      console.log("  quotedId    :", quoted.id._serialized);
      console.log("  tracked ids :", JSON.stringify([...askPromptIds]));
      if (askPromptIds.has(quoted.id._serialized)) {
        console.log("  → MATCH: reply to a 'send prompt' message → handling prompt");
        await handlePrompt(message, chat);
        return;
      }
      console.log("  → quoted msg is not one of our 'send prompt' messages");
    }

    // --- Case B: the start trigger — bot mentioned + "generate poster" ----
    // Mentions can be @c.us or @lid ids that don't match the bot's WID, so
    // resolve each mentioned contact and trust its `isMe` flag instead.
    let mentioned = false;
    try {
      const mentions = await message.getMentions();
      console.log(
        "  mentions    :",
        JSON.stringify(mentions.map((c) => ({ id: c.id._serialized, isMe: c.isMe })))
      );
      mentioned = mentions.some((c) => c.isMe);
    } catch (e) {
      console.log("  getMentions failed:", e.message);
    }
    const body = (message.body || "").toLowerCase();
    const hasTrigger = body.includes(TRIGGER);
    console.log("  mentioned   :", mentioned, "| hasTrigger:", hasTrigger);

    if (mentioned && hasTrigger) {
      console.log("  → MATCH: trigger → replying 'send prompt'");
      const reply = await message.reply(ASK_PROMPT_REPLY);
      rememberAskId(reply.id._serialized);
      console.log("  tracked reply id:", reply.id._serialized);
    } else {
      console.log("  → no action");
    }
  } catch (err) {
    console.error("message handler error:", err);
  }
}

// ---------------------------------------------------------------------------
// Prompt → poster
// ---------------------------------------------------------------------------
async function handlePrompt(message, chat) {
  const prompt = (message.body || "").trim();
  if (!prompt) {
    await message.reply("⚠️ Empty prompt. Reply to *send prompt* with your topic.");
    return;
  }

  await message.reply("⏳ Generating your poster… this may take a minute.");
  chat.sendStateTyping().catch(() => {});

  let finalPath;
  try {
    finalPath = await runPipeline(prompt);
  } catch (err) {
    console.error("pipeline error:", err);
    await message.reply("❌ Sorry, generation failed:\n" + truncate(String(err), 500));
    return;
  }

  try {
    const media = MessageMedia.fromFilePath(finalPath);
    await message.reply(media, undefined, { caption: "✅ Here's your poster." });
  } catch (err) {
    console.error("send error:", err);
    await message.reply("❌ Generated the poster but failed to send it: " + err.message);
  }
}

/**
 * Run `python3 main.py "<prompt>"` in the repo root and resolve with the path
 * of the generated final poster (parsed from the script's stdout).
 */
function runPipeline(prompt) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, ["main.py", prompt], { cwd: REPO_ROOT });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => {
      const s = d.toString();
      stdout += s;
      process.stdout.write("[py] " + s);
    });
    child.stderr.on("data", (d) => {
      const s = d.toString();
      stderr += s;
      process.stderr.write("[py:err] " + s);
    });

    child.on("error", (err) => reject(err));
    child.on("close", (code) => {
      if (code !== 0) {
        return reject(new Error(`main.py exited with code ${code}\n${stderr || stdout}`));
      }
      // main.py prints: "✓ Done. Final poster -> <path>"
      const match = stdout.match(/Final poster ->\s*(.+\.final\.png)\s*$/m);
      if (!match) {
        return reject(new Error("Could not find output path in main.py output."));
      }
      resolve(path.resolve(REPO_ROOT, match[1].trim()));
    });
  });
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

client.initialize();
