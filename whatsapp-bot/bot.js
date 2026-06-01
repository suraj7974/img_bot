/**
 * WhatsApp poster bot
 * ===================
 *
 * Flow (groups only):
 *   1. A user mentions the bot in a group with the words "generate poster".
 *   2. The bot replies "send prompt".
 *   3. The user replies to that "send prompt" message with the actual prompt.
 *   4. The bot runs `python3 main.py "<prompt>"`, sends each generated poster
 *      back as a reply, then deletes the local output files for that run.
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
const PYTHON = process.env.PYTHON_BIN || "python3";
const TRIGGER = "generate poster";
const ASK_PROMPT_REPLY = "send prompt";
const MAX_TRACKED = 500;

// IDs of "send prompt" messages we've sent — a reply quoting one is treated
// as the actual prompt.
const askPromptIds = new Set();
// IDs of messages we've already handled (dedupes message + message_create).
const seenIds = new Set();

function rememberId(set, id) {
  set.add(id);
  if (set.size > MAX_TRACKED) set.delete(set.values().next().value);
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

let botId = null;

client.on("qr", (qr) => {
  console.log("\nScan this QR in WhatsApp → Linked devices:\n");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => console.log("authenticated"));
client.on("auth_failure", (m) => console.error("auth failure:", m));
client.on("disconnected", (r) => console.error("disconnected:", r));

client.on("ready", () => {
  botId = client.info && client.info.wid && client.info.wid._serialized;
  console.log("ready — bot wid:", botId);
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

    // We only care about text messages — skip stickers, audio, media, etc.
    if (message.type !== "chat") return;

    const chat = await message.getChat();
    if (!chat.isGroup) return;

    // Case A: reply quoting one of our "send prompt" messages → the prompt.
    if (message.hasQuotedMsg) {
      const quoted = await message.getQuotedMessage();
      if (askPromptIds.has(quoted.id._serialized)) {
        await handlePrompt(message, chat);
        return;
      }
    }

    // Case B: start trigger — bot mentioned + "generate poster".
    if (!(message.body || "").toLowerCase().includes(TRIGGER)) return;
    const mentions = await message.getMentions();
    if (!mentions.some((c) => c.isMe)) return;

    const reply = await message.reply(ASK_PROMPT_REPLY);
    rememberId(askPromptIds, reply.id._serialized);
    console.log("trigger →", chat.name || chat.id._serialized);
  } catch (err) {
    console.error("handler error:", err.message);
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
  console.log("prompt:", truncate(prompt, 120));

  await message.reply("⏳ Generating your posters…");
  chat.sendStateTyping().catch(() => {});

  let finalPaths;
  try {
    finalPaths = await runPipeline(prompt);
  } catch (err) {
    console.error("pipeline failed:", err.message);
    await message.reply("❌ Generation failed:\n" + truncate(String(err.message), 500));
    return;
  }

  const total = finalPaths.length;
  const sent = [];
  for (let i = 0; i < total; i++) {
    const p = finalPaths[i];
    try {
      const media = MessageMedia.fromFilePath(p);
      const caption = total === 1 ? "✅ Here's your poster." : `✅ Variant ${i + 1}/${total}`;
      await message.reply(media, undefined, { caption });
      sent.push(p);
    } catch (err) {
      console.error("send error", p, err.message);
      await message.reply(`❌ Failed to send variant ${i + 1}: ${err.message}`);
    }
  }
  cleanupRunFiles(sent);
  console.log(`sent ${sent.length}/${total} posters, files cleaned`);
}

/**
 * Run `python3 main.py "<prompt>"` and return the list of generated `.final.png`
 * paths scraped from stdout (filesystem-verified).
 */
function runPipeline(prompt) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, ["main.py", prompt], { cwd: REPO_ROOT });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        return reject(new Error(`main.py exited ${code}: ${truncate(stderr || stdout, 800)}`));
      }
      const seen = new Set();
      const paths = [];
      const re = /(\S+\.final\.png)/g;
      let m;
      while ((m = re.exec(stdout)) !== null) {
        const abs = path.resolve(REPO_ROOT, m[1]);
        if (seen.has(abs) || !fs.existsSync(abs)) continue;
        seen.add(abs);
        paths.push(abs);
      }
      if (paths.length === 0) {
        return reject(new Error("no .final.png paths found in main.py output"));
      }
      resolve(paths);
    });
  });
}

/**
 * After WhatsApp confirms the send, drop the local copies for that run:
 * the .final.png, its .raw.png twin, and the .prompt.txt sibling. Best-effort.
 */
function cleanupRunFiles(finalPaths) {
  for (const p of finalPaths) {
    const siblings = [p, p.replace(/\.final\.png$/, ".raw.png"), p.replace(/\.final\.png$/, ".prompt.txt")];
    for (const s of siblings) {
      fs.promises.unlink(s).catch(() => {});
    }
  }
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

client.initialize();
