#!/usr/bin/env bash
# Script to launch the AdsPower & Facebook Automation Dashboard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================="
echo "   تشغيل DheyaAdspowercBot - أتمتة AdsPower والمنصات المتعددة"
echo "================================================================="

# Activate virtualenv if present
if [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

python3 app.py
