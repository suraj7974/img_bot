# imgbot — single-container image running:
#   - FastAPI dashboard (uvicorn :8000)
#   - WhatsApp bot (node bot.js)
# under supervisord so a crash in either restarts cleanly.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    NODE_MAJOR=20 \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    PYTHON_BIN=python3

# System deps:
#   * chromium + ffmpeg + the dbus shim → whatsapp-web.js / puppeteer
#   * libraqm + noto fonts → Pillow renders Devanagari (Hindi) correctly
#   * supervisor → run both processes in one container
#   * curl, gnupg, ca-certificates → adding the NodeSource repo
#   * tini → proper PID 1 / signal handling
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        ffmpeg \
        libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libraqm0 \
        fonts-noto fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji \
        fontconfig \
        supervisor \
        tini \
        curl gnupg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

WORKDIR /app

# Two-step copy so that `pip install -e .` can find a `src/imgbot` package
# WITHOUT us having to invalidate the layer cache every time Python source
# changes. The stub __init__.py satisfies setuptools' package discovery;
# real source is layered on top in the next step.
COPY pyproject.toml ./
RUN mkdir -p src/imgbot && touch src/imgbot/__init__.py
RUN pip install -e .

# Real Python source — replaces the stub.
COPY src/ ./src/

# Bot source + npm deps. Puppeteer skip is set in ENV above so the npm install
# doesn't try to download its own 200MB Chromium.
COPY whatsapp-bot/package*.json ./whatsapp-bot/
RUN cd whatsapp-bot && npm install --omit=dev --no-audit --no-fund
COPY whatsapp-bot/ ./whatsapp-bot/

# Process supervisor + container entrypoint.
COPY docker/supervisord.conf /etc/supervisor/conf.d/imgbot.conf
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Persistent state mount points — declared so `docker run` shows them, but
# real persistence comes from the host bind mount in docker-compose.
RUN mkdir -p /app/data /app/whatsapp-bot/.wwebjs_auth /app/whatsapp-bot/.wwebjs_cache

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
