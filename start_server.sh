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
echo "  DheyaAdspowercBot Launcher  |  DISPLAY=$DISPLAY"
echo "==================================================="

# Clean stale Electron singleton lock files
rm -f /home/ukal/.config/adspower_global/Singleton* 2>/dev/null || true
rm -rf /tmp/scoped_dir* 2>/dev/null || true

# Function to locate AdsPower executable
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
    local icon_path="/home/ukal/py_workspace/ukal/static/img/dheya_adspower_bot.png"
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

ADSPOWER_BIN=$(find_adspower_bin)

# 1. Open AdsPower if not already running
if ! pgrep -x "adspower_global" > /dev/null 2>&1 && ! curl -s http://127.0.0.1:50325/status > /dev/null 2>&1; then
    if [ -z "$ADSPOWER_BIN" ]; then
        notify_adspower_missing
        exit 1
    fi
    echo "Starting AdsPower from: $ADSPOWER_BIN"
    setsid "$ADSPOWER_BIN" > /tmp/adspower.log 2>&1 &
    sleep 8
    (pgrep -x "adspower_global" > /dev/null 2>&1 || curl -s http://127.0.0.1:50325/status > /dev/null 2>&1) && echo "AdsPower started OK" || echo "AdsPower launch attempted - see /tmp/adspower.log"
else
    echo "AdsPower already running."
fi

# 2. Restart the Flask server to load fresh code
echo "Stopping any existing bot server..."
pkill -f "python.*app\.py" 2>/dev/null || true
sleep 1

echo "Starting DheyaAdspowercBot server..."
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
