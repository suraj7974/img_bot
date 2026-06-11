#!/usr/bin/env bash
# imgbot container entrypoint.
#
# 1. Sweep any stale Chromium SingletonLock files in the WhatsApp auth dir.
#    These are left behind when Chromium is killed ungracefully (e.g. the
#    container was OOM-killed or SIGKILLed). Their presence makes Chromium
#    refuse to start on the next boot with a "ProfileInUse" error.
#
# 2. Hand off to supervisord, which runs the dashboard + bot side-by-side.

set -euo pipefail

AUTH_DIR="/app/whatsapp-bot/.wwebjs_auth"
if [ -d "$AUTH_DIR" ]; then
  find "$AUTH_DIR" \
    \( -name 'SingletonLock' -o -name 'SingletonCookie' -o -name 'SingletonSocket' \) \
    -print -delete 2>/dev/null || true
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/imgbot.conf
