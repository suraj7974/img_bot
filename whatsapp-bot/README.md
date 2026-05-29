# WhatsApp Poster Bot

Drives the poster pipeline (`../main.py`) from a WhatsApp group using
[whatsapp-web.js](https://wwebjs.dev/).

## How it works (groups only)

1. Add the bot's WhatsApp number to a group.
2. A user **mentions the bot and writes `generate poster`**, e.g.
   `@91XXXXXXXXXX generate poster`.
3. The bot replies **`send prompt`**.
4. The user **replies to that `send prompt` message** with the actual prompt
   text. Only a reply quoting that message is treated as the prompt — all other
   messages are ignored.
5. The bot runs `python3 main.py "<prompt>"` and, when the poster is ready,
   sends the final image as a reply to the user's prompt message.

## Setup

### 1. Python pipeline (one level up)
```bash
cd ..
pip install -r requirements.txt
cp .env.example .env        # then put your real GEMINI_API_KEY in .env
```

### 2. Bot
```bash
cd whatsapp-bot
npm install
npm start
```

On first run, scan the QR code printed in the terminal from
**WhatsApp → Settings → Linked devices → Link a device**. The session is saved
in `.wwebjs_auth/`, so you only scan once.

## Configuration

Environment variables (optional):

| Var          | Default   | Purpose                                  |
| ------------ | --------- | ---------------------------------------- |
| `PYTHON_BIN` | `python3` | Python interpreter used to run `main.py` |

Edit `bot.js` to change the trigger phrase (`generate poster`) or the bot's
reply (`send prompt`).

## Notes

- The poster takes a while to generate; the bot posts a "Generating…" message
  immediately and sends the image when done.
- Output images are written to `../output/` by `main.py`. The bot parses the
  final path from `main.py`'s stdout (`Final poster -> …`).
- Keep `npm start` running on a machine that stays online; whatsapp-web.js
  drives a real WhatsApp Web session.
