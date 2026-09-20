#!/bin/bash

# Auto-detect DISPLAY from gnome-session process
GNOME_PID=$(pgrep -u ukal gnome-session 2>/dev/null | head -1)
if [ -n "$GNOME_PID" ]; then
    eval $(grep -z "^DISPLAY=" /proc/$GNOME_PID/environ 2>/dev/null | tr '\0' '\n' | grep DISPLAY)
    eval $(grep -z "^DBUS_SESSION_BUS_ADDRESS=" /proc/$GNOME_PID/environ 2>/dev/null | tr '\0' '\n' | grep DBUS_SESSION_BUS_ADDRESS)
    eval $(grep -z "^XDG_RUNTIME_DIR=" /proc/$GNOME_PID/environ 2>/dev/null | tr '\0' '\n' | grep XDG_RUNTIME_DIR)
fi
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"

echo "==================================================="
echo "  DheyaStore Bot Launcher  |  DISPLAY=$DISPLAY"
echo "==================================================="

# Clean stale Electron singleton lock files
rm -f /home/ukal/.config/adspower_global/Singleton* 2>/dev/null || true
rm -rf /tmp/scoped_dir* 2>/dev/null || true

# 1. Open AdsPower if not already running
if ! pgrep -x "adspower_global" > /dev/null 2>&1 && ! curl -s http://127.0.0.1:50325/status > /dev/null 2>&1; then
    echo "Starting AdsPower..."
    setsid "/opt/AdsPower Global/adspower_global" > /tmp/adspower.log 2>&1 &
    sleep 8
    (pgrep -x "adspower_global" > /dev/null 2>&1 || curl -s http://127.0.0.1:50325/status > /dev/null 2>&1) && echo "AdsPower started OK" || echo "AdsPower launch attempted - see /tmp/adspower.log"
else
    echo "AdsPower already running."
fi

# 2. Restart the Flask server to load fresh code
echo "Stopping any existing bot server..."
pkill -f "python.*app\.py" 2>/dev/null || true
sleep 1

echo "Starting DheyaStore Bot server..."
cd /home/ukal/py_workspace/ukal
setsid /home/ukal/py_workspace/ukal/venv/bin/python3 /home/ukal/py_workspace/ukal/app.py > /tmp/dheyabot.log 2>&1 &
SERVER_PID=$!

echo "Waiting for server..."
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    sleep 1
    curl -s http://127.0.0.1:5000/api/status > /dev/null 2>&1 && echo "Server ready!" && break
    echo "  ... $i/15"
done

# 3. Open Chrome
echo "Opening Chrome..."
nohup google-chrome --new-window "http://127.0.0.1:5000" > /dev/null 2>&1 &
sleep 2

echo "==================================================="
echo "  Done! Server log: /tmp/dheyabot.log"
echo "==================================================="

tail -f /tmp/dheyabot.log
