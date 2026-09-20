import os
import re
import json
import time
import random
import logging
import threading
from typing import Dict, Any, List, Optional
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROCESSED_LOG_FILE = "processed_comments.json"


class BaseAutomationWorker:
    """Base worker managing browser session lifecycle, multi-window coordination, and human interactions."""
    def __init__(self, profile_id: str, profile_name: str, platform: str, config: Dict[str, Any], runner_hub):
        self.profile_id = profile_id
        self.profile_name = profile_name or profile_id
        self.platform = platform  # 'facebook', 'instagram', 'twitter', 'tiktok'
        self.worker_key = f"{profile_id}_{platform}"
        self.config = config
        self.runner_hub = runner_hub
        self.stop_requested = False
        self.driver = None
        self.window_handle: Optional[str] = None
        self.thread: Optional[threading.Thread] = None
        self.status = "قيد التهيئة..."
        self.stats = {
            "comments_scanned": 0,
            "replies_sent": 0,
            "dms_sent": 0,
            "errors": 0,
            "skipped_author": 0,
            "skipped_restricted": 0
        }

    def log(self, level: str, message: str):
        self.runner_hub.add_log(self.profile_id, self.profile_name, self.platform, level, message)

    def sleep(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end and not self.stop_requested:
            time.sleep(min(0.2, end - time.time()))

    def _ensure_valid_window(self) -> bool:
        """Verifies driver is attached to this worker's active window."""
        try:
            if self.window_handle and self.window_handle in self.driver.window_handles:
                self.driver.switch_to.window(self.window_handle)
                _ = self.driver.title
                return True
            _ = self.driver.current_window_handle
            _ = self.driver.title
            return True
        except Exception:
            try:
                handles = self.driver.window_handles
                if handles:
                    self.driver.switch_to.window(handles[-1])
                    self.window_handle = handles[-1]
                    self.log("INFO", "🔄 تم التبديل واستعادة التحكم في نافذة المتصفح النشطة تلقائياً.")
                    return True
                else:
                    self.log("ERROR", "❌ تم إغلاق جميع نوافذ المتصفح بالكامل.")
                    return False
            except Exception as e:
                self.log("ERROR", f"❌ تعذر العثور على نافذة متصفح نشطة: {e}")
                return False

    def js_click(self, element):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
            self.sleep(0.3)
            self.driver.execute_script("arguments[0].click();", element)
        except Exception:
            try:
                element.click()
            except Exception:
                pass

    def type_letter_by_letter(self, element, text: str):
        """Types text with human pauses, proper cursor positioning, and unicode emoji safety."""
        try:
            self.driver.execute_script("""
                const el = arguments[0];
                el.scrollIntoView({block: 'center'});
                el.focus();
                if (el.setSelectionRange) {
                    const len = el.value.length;
                    el.setSelectionRange(len, len);
                } else {
                    try {
                        const range = document.createRange();
                        range.selectNodeContents(el);
                        range.collapse(false);
                        const sel = window.getSelection();
                        sel.removeAllRanges();
                        sel.addRange(range);
                    } catch(e) {}
                }
            """, element)
            self.sleep(0.3)

            for char in text:
                if self.stop_requested:
                    break
                success = False
                try:
                    success = self.driver.execute_script(
                        "arguments[0].focus(); return document.execCommand('insertText', false, arguments[1]);",
                        element, char
                    )
                except Exception:
                    pass

                if not success:
                    try:
                        element.send_keys(char)
                    except Exception:
                        pass

                time.sleep(random.uniform(0.04, 0.10))
                if random.random() < 0.04:
                    self.sleep(random.uniform(0.3, 0.8))
            self.sleep(0.5)
        except Exception as e:
            try:
                element.send_keys(text)
            except Exception:
                pass

    def run(self):
        self.status = "في طابور التشغيل المنظم..."
        self.log("INFO", f"⏳ جدولة تشغيل المتصفح للملف [{self.profile_name}] على منصة [{self.platform.upper()}]...")

        start_res = self.runner_hub.adspower_client.start_browser(self.profile_id)
        if not start_res.get("success"):
            self.status = "فشل تشغيل المتصفح"
            self.log("ERROR", f"❌ فشل تشغيل متصفح AdsPower للملف [{self.profile_name}]: {start_res.get('message')}")
            return

        selenium_port = start_res.get("selenium_port")
        chromedriver_path = start_res.get("chromedriver_path")
        self.log("SUCCESS", f"✅ تم فتح المتصفح بنجاح للملف [{self.profile_name}] على المنفذ: {selenium_port}")
        self.status = "جاري الاتصال بسيلينيوم..."

        opts = Options()
        opts.debugger_address = selenium_port
        svc = Service(chromedriver_path) if chromedriver_path else Service()

        try:
            self.driver = webdriver.Chrome(service=svc, options=opts)
            self.log("SUCCESS", f"تم الاتصال بسيلينيوم للمنصة [{self.platform.upper()}]")

            # Check if other platform automations are already running in this profile
            other_active_workers = [
                w for w in self.runner_hub.workers.values()
                if w.profile_id == self.profile_id and getattr(w, 'worker_key', '') != self.worker_key and w.thread and w.thread.is_alive()
            ]

            if other_active_workers:
                # Open a separate window for this platform automation
                try:
                    self.driver.switch_to.new_window('window')
                except Exception:
                    self.driver.execute_script("window.open('about:blank', '_blank');")
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                self.window_handle = self.driver.current_window_handle
                self.log("INFO", f"🪟 تم فتح نافذة متصفح مخصصة لأتمتة [{self.platform.upper()}] بجانب المنصات النشطة الأخرى.")
            else:
                # First active worker: clean up leftover tabs if necessary
                try:
                    handles = self.driver.window_handles
                    if len(handles) > 1:
                        primary = handles[-1]
                        for h in handles:
                            if h != primary:
                                try:
                                    self.driver.switch_to.window(h)
                                    self.driver.close()
                                except Exception:
                                    pass
                        self.driver.switch_to.window(primary)
                    elif handles:
                        self.driver.switch_to.window(handles[0])
                except Exception:
                    pass
                self.window_handle = self.driver.current_window_handle

            self.execute()

        except Exception as e:
            self.stats["errors"] += 1
            self.log("ERROR", f"حدث استثناء غير متوقع: {str(e)[:150]}")
        finally:
            self.log("INFO", f"إنهاء جلسة أتمتة [{self.platform.upper()}] للملف [{self.profile_name}]...")
            try:
                # Close only this worker's window if other windows exist
                if self.driver and self.window_handle and self.window_handle in self.driver.window_handles:
                    if len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.window_handle)
                        self.driver.close()
            except Exception:
                pass

            # Only stop AdsPower browser if NO other platform workers are active on this profile
            other_active = any(
                w.profile_id == self.profile_id and getattr(w, 'worker_key', '') != self.worker_key and w.thread and w.thread.is_alive()
                for w in self.runner_hub.workers.values()
            )
            if not other_active:
                try:
                    if self.driver:
                        self.driver.quit()
                except Exception:
                    pass
                try:
                    self.runner_hub.adspower_client.stop_browser(self.profile_id)
                except Exception:
                    pass
                self.log("INFO", f"تم إغلاق متصفح AdsPower للملف [{self.profile_name}] بعد انتهاء كافة المهام.")
            else:
                self.log("INFO", f"يبقى متصفح الملف [{self.profile_name}] مفتوحاً لاستمرار أتمتة المنصات الأخرى.")

            self.status = "متوقف"

    def execute(self):
        """Platform-specific automation entrypoint to be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement execute()")


class AutomationWorker(BaseAutomationWorker):
    """Dispatcher class maintaining backward compatibility with existing AutomationWorker calls."""
    def __new__(cls, profile_id: str, profile_name: str, platform: str, config: Dict[str, Any], runner_hub):
        if cls is AutomationWorker:
            from automations.hub import get_worker_class
            target_cls = get_worker_class(platform)
            return super().__new__(target_cls)
        return super().__new__(cls)
