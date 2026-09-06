#!/bin/bash
set -e

# CLI / one-off usage: run it directly, no GUI stack.
if [ "$1" != "serve" ]; then
    exec "$@"
fi

export DISPLAY=:99
mkdir -p /root
touch /root/.Xauthority

Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
sleep 2
fluxbox &
sleep 1
x11vnc -display :99 -forever -shared -rfbport 5900 -nopw &
sleep 1
websockify --web=/usr/share/novnc 6080 localhost:5900 &
sleep 1
chromium --no-sandbox --disable-dev-shm-usage --disable-gpu \
    --window-size=1280,720 --window-position=0,0 https://web.whatsapp.com &

# Flask runs in the foreground - the container lives as long as the web UI does.
exec python /app/web_ui/app.py
