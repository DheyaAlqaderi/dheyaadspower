import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from automations.base import BaseAutomationWorker


class TikTokWorker(BaseAutomationWorker):
    """Worker specialized in automated TikTok viewing and comment engagement."""

    def execute(self):
        self._run_tiktok()

    def _run_tiktok(self):
        target_url = self.config.get("post_url") or "https://www.tiktok.com"
        comment_tpl = self.config.get("public_reply_template") or "Great video! 🔥"
        check_interval = int(self.config.get("check_interval_seconds", 25))

        self.log("INFO", f"فتح تيك توك: {target_url[:60]}...")
        self.driver.get(target_url)
        self.sleep(6)

        while not self.stop_requested:
            self.status = "مشاهدة الفيديو ومحاكاة السلوك..."
            watch_time = random.uniform(8, 15)
            self.log("INFO", f"مشاهدة الفيديو الحالي لمدة {watch_time:.1f} ثانية...")
            self.sleep(watch_time)

            # Scroll to next video
            self.driver.execute_script("window.scrollBy(0, 600);")
            self.sleep(2)

            # Try to like or comment
            try:
                comment_input = self.driver.find_elements(By.XPATH, '//div[@contenteditable="true" and contains(@class, "comment")]')
                if comment_input and not self.stop_requested:
                    self.js_click(comment_input[0])
                    self.sleep(1)
                    self.type_letter_by_letter(comment_input[0], comment_tpl.format(name="Creator"))
                    comment_input[0].send_keys(Keys.ENTER)
                    self.stats["replies_sent"] += 1
                    self.log("SUCCESS", "✓ تم التفاعل والتعليق على تيك توك")
                    self.sleep(4)
            except Exception:
                pass

            self.sleep(check_interval)
