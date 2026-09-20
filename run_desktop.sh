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

# Function to locate AdsPower executable on the system
find_adspower_bin() {
    if [ -x "/opt/AdsPower Global/adspower_global" ]; then
        echo "/opt/AdsPower Global/adspower_global"
        return 0
    fi
    if command -v adspower_global >/dev/null 2>&1; then
        command -v adspower_global
        return 0
    fi
    if command -v adspower >/dev/null 2>&1; then
        command -v adspower
        return 0
    fi
    local opt_find
    opt_find=$(find /opt -maxdepth 3 -name "adspower_global" -executable 2>/dev/null | head -1)
    if [ -n "$opt_find" ]; then
        echo "$opt_find"
        return 0
    fi
    return 1
}

# Function to alert user when AdsPower is missing
notify_adspower_missing() {
    local icon_path="$SCRIPT_DIR/static/img/dheya_adspower_bot.png"
    local download_url="https://www.adspower.com/download"

    echo ""
    echo "========================================================================"
    echo "  ⚠️ تنبيه: تطبيق AdsPower غير مثبت على هذا الجهاز!"
    echo "  ⚠️ Warning: AdsPower is not installed on this computer!"
    echo "========================================================================"
    echo "  يتطلب تشغيل DheyaAdspowercBot تثبيت تطبيق AdsPower أولاً."
    echo "  يرجى تحميل وتثبيت برنامج AdsPower من الرابط الرسمي:"
    echo "  👉 $download_url"
    echo "========================================================================"
    echo ""

    if [ -n "$DISPLAY" ]; then
        if command -v zenity >/dev/null 2>&1; then
            if zenity --question \
                --title="DheyaAdspowercBot - AdsPower غير مثبت" \
                --window-icon="$icon_path" \
                --text="⚠️ <b>لم يتم العثور على تطبيق AdsPower على جهازك!</b>\n\nيتطلب تشغيل <b>DheyaAdspowercBot</b> تثبيت تطبيق AdsPower أولاً لإدارة الملفات والبروكسيات.\n\nهل ترغب في فتح صفحة التحميل الرسمية الآن لتنزيل البرنامج؟\n\n<a href=\"$download_url\">$download_url</a>" \
                --ok-label="تحميل AdsPower الآن 🌐" \
                --cancel-label="إلغاء ❌" \
                --width=480 2>/dev/null; then
                xdg-open "$download_url" 2>/dev/null || google-chrome "$download_url" 2>/dev/null &
            fi
        elif command -v notify-send >/dev/null 2>&1; then
            notify-send -u critical -i "$icon_path" \
                "AdsPower غير مثبت!" \
                "يتطلب تشغيل DheyaAdspowercBot تحميل وتثبيت تطبيق AdsPower: $download_url"
        fi
    fi
}

# Check if AdsPower is running or installed before launching
ADSPOWER_RUNNING=false
if curl -s http://127.0.0.1:50325/status >/dev/null 2>&1 || pgrep -x "adspower_global" >/dev/null 2>&1; then
    ADSPOWER_RUNNING=true
fi

ADSPOWER_BIN=$(find_adspower_bin)

if [ "$ADSPOWER_RUNNING" = false ] && [ -z "$ADSPOWER_BIN" ]; then
    notify_adspower_missing
    exit 1
fi

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
