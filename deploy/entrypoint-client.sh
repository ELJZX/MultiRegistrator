#!/bin/sh
# Start a virtual X display, a window manager, VNC and noVNC, then the client.
set -e

GEOMETRY="${SCREEN_GEOMETRY:-1600x1000x24}"
SERVER="${MULTIREGISTRATOR_SERVER:-server:8120}"

# Start Xvfb and wait until it accepts connections.
Xvfb :99 -screen 0 "$GEOMETRY" -nolisten tcp &
XVFB_PID=$!
for _ in $(seq 1 50); do
    if xdpyinfo -display :99 >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

fluxbox >/dev/null 2>&1 &

# VNC server on localhost only; noVNC bridges it to the browser on port 6080.
x11vnc -display :99 -forever -shared -nopw -listen 127.0.0.1 -rfbport 5900 >/dev/null 2>&1 &
websockify --web=/usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

# The client auto-connects to the server container and opens maximised.
exec python -m multiregistrator.client.app --server "$SERVER" --autoconnect
