#!/bin/bash
# =================================================================
#  DheyaAdspowercBot Desktop Launcher
# =================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Auto-detect DISPLAY and session variables from gnome-session if not set
if [ -z "$DISPLAY" ] || [ "$DISPLAY" = "" ]; then
    GNOME_PID=$(pgrep -u "$USER" gnome-session 2>/dev/null | head -1)
    if [ -n "$GNOME_PID" ]; then
        eval $(grep -z "^DISPLAY=" /proc/$GNOME_PID/environ 2>/dev/null | tr '\0' '\n' | grep DISPLAY)
        eval $(grep -z "^DBUS_SESSION_BUS_ADDRESS=" /proc/$GNOME_PID/environ 2>/dev/null | tr '\0' '\n' | grep DBUS_SESSION_BUS_ADDRESS)
        eval $(grep -z "^XDG_RUNTIME_DIR=" /proc/$GNOME_PID/environ 2>/dev/null | tr '\0' '\n' | grep XDG_RUNTIME_DIR)
    fi
fi
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"

# If launched from Desktop UI without a terminal, spawn a visible terminal window
if [ ! -t 1 ]; then
    if command -v ptyxis >/dev/null 2>&1; then
        exec ptyxis -T "DheyaAdspowercBot" -- "$SCRIPT_DIR/start_server.sh"
    elif command -v gnome-terminal >/dev/null 2>&1; then
        exec gnome-terminal --title="DheyaAdspowercBot" -- "$SCRIPT_DIR/start_server.sh"
    elif command -v x-terminal-emulator >/dev/null 2>&1; then
        exec x-terminal-emulator -T "DheyaAdspowercBot" -e "$SCRIPT_DIR/start_server.sh"
    fi
fi

# Fallback or already in terminal
exec "$SCRIPT_DIR/start_server.sh"
