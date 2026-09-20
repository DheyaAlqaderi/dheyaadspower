import os
import re
import time
import random
import logging
import threading
from typing import Dict, Any, List, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from automations.base import BaseAutomationWorker

INSTA_DATABASE_FILE = "replied_users.txt"


class InstagramDatabaseManager:
    """Thread-safe persistent memory to ensure we don't message the same user twice for the same post."""
    def __init__(self, db_file: str = INSTA_DATABASE_FILE):
        self.db_file = db_file
        self._lock = threading.Lock()
        self.processed_records = self._load_data()

    def _load_data(self) -> set:
        if not os.path.exists(self.db_file):
            return set()
        try:
            with open(self.db_file, "r", encoding="utf-8") as f:
                return set(line.strip().lower() for line in f if line.strip())
        except Exception:
            return set()

    def _generate_key(self, username: str, post_url: str) -> str:
        """Creates a unique key combining the user and the specific post."""
        post_id = post_url.rstrip('/').split('/')[-1]
        return f"{username.lower()}|{post_id.lower()}"

    def is_processed(self, username: str, post_url: str) -> bool:
        with self._lock:
            key = self._generate_key(username, post_url)
            return key in self.processed_records or username.lower() in self.processed_records

    def save_record(self, username: str, post_url: str):
        with self._lock:
            key = self._generate_key(username, post_url)
            if key not in self.processed_records:
                self.processed_records.add(key)
                try:
                    with open(self.db_file, "a", encoding="utf-8") as f:
                        f.write(key + "\n")
                except Exception as e:
                    logging.getLogger("AutomationRunner").error(f"Error saving instagram record: {e}")


class InstagramWorker(BaseAutomationWorker):
    """Worker specialized in automated Instagram Reels/Posts threaded replies and direct messaging."""

    def execute(self):
        self._run_instagram()

    def _open_instagram_comments_drawer(self):
        """Ensures the comment section is open on Reels."""
        if not self._ensure_valid_window():
            return
        try:
            # If reply buttons, comment input textarea, or comments container exist, drawer is already open
            if self.driver.find_elements(By.XPATH, "//span[text()='Reply'] | //button[contains(., 'Reply')] | //span[contains(text(), 'رد')] | //textarea[contains(@aria-label, 'comment') or contains(@placeholder, 'comment') or contains(@aria-label, 'تعليق')] | //div[contains(@class, 'x5yr21d') and contains(@class, 'xw2csxc')]"):
                return
            icons = self.driver.find_elements(
                By.XPATH,
                "//*[local-name()='svg' and (@aria-label='Comment' or @aria-label='Commentaires' or @aria-label='تعليق')]/ancestor::div[@role='button']"
            )
            if icons:
                self.log("INFO", "📂 جاري فتح درج التعليقات (Reels Comments Drawer)...")
                self.driver.execute_script("arguments[0].click();", icons[0])
                self.sleep(random.uniform(2.0, 3.5))
        except Exception as e:
            self.log("WARNING", f"تعذر فتح درج التعليقات: {e}")

    def _switch_to_newest_comments_if_available(self):
        """Switches comment sorting to 'Newest' if an option dropdown is available."""
        try:
            sort_xpath = (
                "//span[text()='Top comments' or text()='Most relevant' or text()='أبرز التعليقات' or text()='الأكثر صلة']/ancestor::div[@role='button'] | "
                "//div[@role='button' and (contains(., 'Top comments') or contains(., 'أبرز التعليقات'))]"
            )
            sort_btns = self.driver.find_elements(By.XPATH, sort_xpath)
            if sort_btns and sort_btns[0].is_displayed():
                self.driver.execute_script("arguments[0].click();", sort_btns[0])
                self.sleep(1.0)
                newest_xpath = (
                    "//span[text()='Newest' or text()='Newest first' or text()='الأحدث' or contains(text(), 'Newest')]/ancestor::div[@role='button'] | "
                    "//div[@role='button' and (contains(., 'Newest') or contains(., 'الأحدث'))]"
                )
                newest_btns = self.driver.find_elements(By.XPATH, newest_xpath)
                if newest_btns and newest_btns[0].is_displayed():
                    self.driver.execute_script("arguments[0].click();", newest_btns[0])
                    self.sleep(1.5)
        except Exception:
            pass

    def _extract_instagram_author(self) -> str:
        """Finds the author of the current post so we don't reply to them."""
        try:
            meta_og = self.driver.find_elements(By.XPATH, "//meta[@property='og:url' or @name='twitter:image']")
            for m in meta_og:
                match = re.search(r'instagram\.com/([a-zA-Z0-9._]+)/(?:reel|p)/', m.get_attribute("content") or "")
                if match:
                    return match.group(1).lower()
        except Exception:
            pass
        return ""

    def _get_instagram_commenter_info(self, reply_button) -> str:
        """Extracts username associated with a specific reply button."""
        js_extract = """
        let curr = arguments[0];
        for (let i = 0; i < 12; i++) {
            if (!curr) break;
            curr = curr.parentElement;
            if (!curr) break;
            const links = curr.querySelectorAll('a[href^="/"]');
            for (const a of links) {
                const clean = (a.getAttribute('href') || '').split('?')[0].replace(/^\\/|\\/$/g, '');
                if (clean && !clean.includes('/') && !['explore', 'reels', 'p', 'direct'].includes(clean)) {
                    return clean;
                }
            }
        } return null;
        """
        try:
            result = self.driver.execute_script(js_extract, reply_button)
            if result:
                return result
        except Exception:
            pass
        return ""

    def _scroll_instagram_comments_drawer(self) -> bool:
        """Scrolls down the nested Instagram comments box to paginate and load more comments."""
        if not self._ensure_valid_window():
            return False

        # 1. Click any visible "Load more comments" / "View more comments" / "+" buttons via Selenium first
        load_more_xpath = (
            "//button[contains(., 'View more comments') or contains(., 'Load more comments') or contains(., 'عرض المزيد من التعليقات') or contains(., 'View all')] | "
            "//*[local-name()='svg' and (@aria-label='Load more comments' or @aria-label='تحميل المزيد من التعليقات' or @aria-label='Load more')]/ancestor::div[@role='button'] | "
            "//div[@role='button' and (contains(., 'View more comments') or contains(., 'عرض المزيد من التعليقات') or contains(., 'Load more'))]"
        )
        try:
            more_btns = self.driver.find_elements(By.XPATH, load_more_xpath)
            for btn in more_btns:
                if btn.is_displayed():
                    self.log("INFO", "   ↳ النقر على زر 'تحميل المزيد من التعليقات'...")
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    self.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", btn)
                    self.sleep(random.uniform(2.0, 3.5))
                    return True
        except Exception:
            pass

        # Also expand any hidden reply threads (View replies / عرض الردود)
        try:
            expand_replies_xpath = (
                "//span[contains(text(), 'View replies') or contains(text(), 'عرض الردود') or contains(text(), 'View 1 reply') or (contains(text(), 'View') and contains(text(), 'repl'))]/ancestor::div[@role='button']"
            )
            expand_btns = self.driver.find_elements(By.XPATH, expand_replies_xpath)
            for e_btn in expand_btns[:3]:
                if e_btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", e_btn)
                    self.sleep(random.uniform(1.0, 1.8))
        except Exception:
            pass

        # 2. Execute scroll strictly inside the nested comments container (never scroll outer window)
        js_scroll = """
        return (() => {
            // Locate the exact nested comments scroll container
            let container = null;

            // Priority A: Right pane on Reels/Posts (div.x4h1yfo / div.xvbhtw8)
            const rightPane = document.querySelector('div.x4h1yfo') || document.querySelector('div.xvbhtw8');
            if (rightPane) {
                container = rightPane.querySelector('div.x5yr21d.xw2csxc.x1odjw0f.x1n2onr6')
                         || rightPane.querySelector('div.x5yr21d.xw2csxc.x1odjw0f')
                         || rightPane.querySelector('div.xw2csxc.x1odjw0f')
                         || rightPane.querySelector('div.x1odjw0f')
                         || rightPane.querySelector('div.xw2csxc');
            }

            // Priority B: Exact class combinations on the comments container
            if (!container) {
                const candidates = document.querySelectorAll(
                    'div.x5yr21d.xw2csxc.x1odjw0f.x1n2onr6, ' +
                    'div.x5yr21d.xw2csxc.x1odjw0f, ' +
                    'div.x1odjw0f.xw2csxc, ' +
                    'div.xw2csxc.x1odjw0f'
                );
                for (const c of candidates) {
                    if (c.clientHeight > 80) {
                        container = c;
                        break;
                    }
                }
            }

            // Priority C: Find ancestor container from any visible Reply button or comment avatar
            if (!container) {
                const replyElements = Array.from(document.querySelectorAll('span, div[role="button"]')).filter(el => {
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    return t === 'reply' || t === 'رد' || t === 'répondre' || t.startsWith('reply to') || t.startsWith('رد على');
                });
                for (const el of replyElements) {
                    const ancestor = el.closest('div.x5yr21d.xw2csxc')
                                  || el.closest('div.x1odjw0f')
                                  || el.closest('div.xw2csxc');
                    if (ancestor && ancestor.clientHeight > 80) {
                        container = ancestor;
                        break;
                    }
                    let p = el.parentElement;
                    while (p && p !== document.body) {
                        const style = window.getComputedStyle(p);
                        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && p.clientHeight > 80) {
                            container = p;
                            break;
                        }
                        p = p.parentElement;
                    }
                    if (container) break;
                }
            }

            // Priority D: Relative to comment input textarea column
            if (!container) {
                const textarea = document.querySelector('textarea[aria-label*="comment" i], textarea[placeholder*="comment" i], textarea[aria-label*="تعليق" i]');
                if (textarea) {
                    const col = textarea.closest('div.x4h1yfo') || textarea.closest('article') || textarea.closest('div[role="dialog"]');
                    if (col) {
                        container = col.querySelector('div.x5yr21d.xw2csxc.x1odjw0f')
                                 || col.querySelector('div.x1odjw0f')
                                 || col.querySelector('div.xw2csxc')
                                 || col.querySelector('ul.x78zum5.xdt5ytf');
                    }
                }
            }

            if (!container) {
                // DO NOT fallback to window.scrollBy!
                return {
                    found: false,
                    scrolled: false,
                    reason: "container_not_found"
                };
            }

            const prevTop = container.scrollTop;
            const scrollHeightBefore = container.scrollHeight;
            const clientHeight = container.clientHeight;

            // Scroll container down by 85% of visible height (min 550px)
            const delta = Math.max(550, Math.floor(clientHeight * 0.85));
            container.scrollTop = Math.min(container.scrollTop + delta, container.scrollHeight);

            // Dispatch scroll & wheel events for React listeners
            container.dispatchEvent(new Event('scroll', { bubbles: true }));
            container.dispatchEvent(new WheelEvent('wheel', { deltaY: delta, bubbles: true, cancelable: true }));

            // Scroll the last comment item into view (triggers virtualized pagination)
            const commentItems = container.querySelectorAll(
                'div.x9f619.x78zum5.xdt5ytf.x5yr21d > div, ' +
                'div.html-div, ' +
                'ul > li, ' +
                'div[role="button"] span'
            );
            if (commentItems.length > 0) {
                const lastItem = commentItems[commentItems.length - 1];
                lastItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }

            // Also check for click on any "View more comments" or "+" button inside container or parent
            let clickedMore = false;
            const buttons = (container.parentElement || container).querySelectorAll('div[role="button"], button');
            for (const b of buttons) {
                const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                if (t.includes('view more comments') || t.includes('load more comments') ||
                    t.includes('عرض المزيد من التعليقات') || aria.includes('load more') || aria.includes('تحميل المزيد')) {
                    b.scrollIntoView({ block: 'center' });
                    b.click();
                    clickedMore = true;
                    break;
                }
            }

            const isSpinner = (container.parentElement || container).querySelector(
                'svg[aria-label*="Loading" i], svg[aria-label*="جاري التحميل" i], div[role="progressbar"]'
            ) !== null;

            const actuallyScrolled = container.scrollTop > prevTop;
            const heightIncreased = container.scrollHeight > scrollHeightBefore;

            return {
                found: true,
                scrolled: actuallyScrolled || clickedMore || heightIncreased || isSpinner,
                prevTop: prevTop,
                newTop: container.scrollTop,
                maxTop: Math.max(0, container.scrollHeight - clientHeight),
                isSpinner: isSpinner,
                itemsCount: commentItems.length
            };
        })();
        """
        try:
            res = self.driver.execute_script(js_scroll)
            if res and res.get("found"):
                if res.get("scrolled"):
                    self.log("INFO", f"   ↳ تم تمرير صندوق التعليقات الداخلي بنجاح (الموضع: {res.get('newTop')}/{res.get('maxTop')}).")
                    self.sleep(random.uniform(2.2, 3.5))
                    return True
                else:
                    self.log("INFO", "   ↳ وصل التمرير إلى أسفل صندوق التعليقات الحالي.")
                    self.sleep(random.uniform(1.5, 2.5))
                    return False
            else:
                self.log("WARNING", "   ⚠️ لم يتم العثور على الصندوق الداخلي للتعليقات للتمرير.")
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء تمرير التعليقات: {e}")

        return False

    def _send_instagram_dm(self, username: str, message: str):
        """Navigates directly to Instagram user DM via short link https://ig.me/m/<username> in a new tab and sends message."""
        if not self._ensure_valid_window():
            raise RuntimeError("نافذة المتصفح غير متوفرة لإرسال الرسالة الخاصة")

        clean_username = username.strip().lstrip("@")
        if not clean_username:
            raise RuntimeError("اسم المستخدم غير صالح لإرسال الرسالة الخاصة")

        main_window = self.driver.current_window_handle
        opened_new_tab = False
        try:
            # Open a new tab so the post page and comments scroll position are preserved
            try:
                self.driver.switch_to.new_window('tab')
                opened_new_tab = True
            except Exception:
                try:
                    self.driver.execute_script("window.open('about:blank', '_blank');")
                    handles = self.driver.window_handles
                    self.driver.switch_to.window(handles[-1])
                    opened_new_tab = True
                except Exception:
                    pass

            ig_dm_url = f"https://ig.me/m/{clean_username}"
            self.log("INFO", f"   ↳ التوجيه المباشر لمحادثة @{clean_username} عبر الرابط المختصر: {ig_dm_url}...")
            self.driver.get(ig_dm_url)
            self.sleep(random.uniform(3.5, 5.0))
            if self.stop_requested:
                return

            # 1. Dismiss any "Turn on Notifications" or "Not Now" dialog if present
            try:
                not_now_xpath = "//button[text()='Not Now' or text()='ليس الآن' or contains(text(), 'Not Now') or contains(text(), 'ليس الآن')]"
                not_now_btns = self.driver.find_elements(By.XPATH, not_now_xpath)
                for btn in not_now_btns:
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        self.sleep(random.uniform(1.0, 1.5))
                        break
            except Exception:
                pass

            dm_box_xpath = (
                "//div[@role='textbox' and (@aria-label='Message' or @aria-label='Message...' or @aria-label='رسالة...' or @contenteditable='true')] | "
                "//div[@contenteditable='true' and (@role='textbox' or contains(@aria-label, 'Message') or contains(@aria-label, 'رسالة'))] | "
                "//textarea[contains(@placeholder, 'Message') or contains(@placeholder, 'رسالة')] | "
                "//div[@contenteditable='true']"
            )

            # 2. Check if page landed on profile with a "Message" button
            dm_box = None
            try:
                boxes = self.driver.find_elements(By.XPATH, dm_box_xpath)
                for b in boxes:
                    if b.is_displayed():
                        dm_box = b
                        break
            except Exception:
                pass

            if not dm_box:
                # Look for "Message" / "إرسال رسالة" button if redirected to profile
                msg_btn_xpath = (
                    "//div[@role='button' and (text()='Message' or text()='إرسال رسالة' or text()='Send message' or contains(., 'Message'))] | "
                    "//button[contains(., 'Message') or contains(., 'إرسال رسالة') or contains(., 'Send message')]"
                )
                try:
                    msg_btns = self.driver.find_elements(By.XPATH, msg_btn_xpath)
                    for btn in msg_btns:
                        if btn.is_displayed():
                            self.log("INFO", f"   ↳ النقر على زر 'رسالة' للمستخدم @{clean_username}...")
                            self.driver.execute_script("arguments[0].click();", btn)
                            self.sleep(random.uniform(2.5, 4.0))
                            break
                except Exception:
                    pass

            # 3. Locate the message input box
            self.log("INFO", f"   ↳ تحديد مربع كتابة الرسالة لمحادثة @{clean_username}...")
            for attempt in range(4):
                if self.stop_requested:
                    return
                try:
                    boxes = self.driver.find_elements(By.XPATH, dm_box_xpath)
                    for b in boxes:
                        if b.is_displayed():
                            dm_box = b
                            break
                    if dm_box:
                        break
                    self.sleep(random.uniform(1.0, 2.0))
                except Exception:
                    self.sleep(random.uniform(1.0, 2.0))

            if not dm_box:
                raise RuntimeError(f"تعذر العثور على مربع إدخال الرسالة في محادثة @{clean_username}.")

            self.log("INFO", f"   ↳ كتابة الرسالة الخاصة للمستخدم @{clean_username}...")
            self.type_letter_by_letter(dm_box, message)
            self.sleep(random.uniform(1.0, 1.5))

            # 4. Send via ENTER
            try:
                dm_box.send_keys(Keys.ENTER)
            except Exception:
                try:
                    b = self.driver.find_element(By.XPATH, dm_box_xpath)
                    b.send_keys(Keys.ENTER)
                except Exception:
                    pass

            self.sleep(random.uniform(1.5, 3.0))

            # 5. Fallback click Send button if message didn't send on ENTER
            try:
                send_btns = self.driver.find_elements(
                    By.XPATH,
                    "//div[@role='button' and (text()='Send' or contains(., 'Send') or text()='إرسال')] | //button[text()='Send' or text()='إرسال']"
                )
                for btn in send_btns:
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        break
            except Exception:
                pass

        finally:
            if opened_new_tab:
                try:
                    self.driver.close()
                except Exception:
                    pass
                try:
                    self.driver.switch_to.window(main_window)
                except Exception:
                    if self.driver.window_handles:
                        self.driver.switch_to.window(self.driver.window_handles[0])

    def _process_instagram_target_post(self, post_url: str, reply_txt: str, dm_txt: str, db: InstagramDatabaseManager) -> bool:
        """Processes an Instagram Reel/Post: loads post, opens drawer, scrolls through ALL comments to completion, and replies.
        Returns True if the entire scroll of comments has finished to the bottom.
        """
        if not self._ensure_valid_window():
            raise RuntimeError("نافذة المتصفح غير متوفرة (قد تم إغلاق المتصفح)")

        current_url = self.driver.current_url or ""
        post_id = post_url.rstrip('/').split('/')[-1].split('?')[0]
        is_already_on_post = post_id in current_url

        # Load post URL if not already on the post (DO NOT refresh here; refresh happens ONLY after scroll finishes)
        if not is_already_on_post:
            self.log("INFO", f"🎯 تحميل رابط المنشور المستهدف: {post_url}")
            self.status = f"فحص ريلز/منشور: {post_id}"
            self.driver.get(post_url)
            self.sleep(random.uniform(4.0, 5.5))
        else:
            self.status = f"فحص وتمرير: {post_id}"

        if self.stop_requested:
            return False

        if not self._ensure_valid_window():
            raise RuntimeError("فقد الاتصال بالمتصفح بعد تحميل رابط المنشور")

        self._open_instagram_comments_drawer()
        self._switch_to_newest_comments_if_available()
        post_author = self._extract_instagram_author()
        if post_author:
            self.log("INFO", f"👤 ناشر المنشور: @{post_author} (سيتم تخطيه)")

        wait = WebDriverWait(self.driver, 8)
        try:
            wait.until(EC.presence_of_element_located((
                By.XPATH, "//span[text()='Reply'] | //div[@role='button' and text()='Reply'] | //button[contains(., 'Reply')] | //span[contains(text(), 'رد')] | //textarea[contains(@aria-label, 'comment')]"
            )))
        except Exception:
            pass

        consecutive_no_new = 0
        total_replied_this_post = 0
        max_scroll_cycles = 150
        scroll_completed_to_bottom = False

        for scroll_cycle in range(max_scroll_cycles):
            if self.stop_requested:
                break
            if consecutive_no_new >= 4:
                scroll_completed_to_bottom = True
                break

            # 1. Gather all current reply buttons in the DOM
            reply_spans = self.driver.find_elements(
                By.XPATH,
                "//span[text()='Reply' or text()='رد' or text()='Répondre' or contains(text(), 'Reply') or contains(text(), 'رد')]"
            )

            batch_unprocessed = []
            for span in reply_spans:
                try:
                    btn = span.find_element(By.XPATH, "ancestor::div[@role='button']")
                except Exception:
                    btn = span

                username = self._get_instagram_commenter_info(btn) or self._get_instagram_commenter_info(span)
                if not username:
                    continue

                u_lower = username.lower()
                if post_author and u_lower == post_author:
                    self.stats["skipped_author"] = self.stats.get("skipped_author", 0) + 1
                    continue

                if db.is_processed(u_lower, post_url):
                    continue

                if u_lower not in [u for u, _, _ in batch_unprocessed]:
                    batch_unprocessed.append((u_lower, btn, span))

            # 2. If unprocessed comments are found in current view, process them
            if batch_unprocessed:
                consecutive_no_new = 0
                self.log("INFO", f"✨ تم اكتشاف {len(batch_unprocessed)} تعليق جديد غير مكرر...")

                for target_username, btn, span in batch_unprocessed:
                    if self.stop_requested:
                        break

                    if db.is_processed(target_username, post_url):
                        continue

                    self.status = f"الرد التفرعي على @{target_username}"
                    self.log("INFO", f"💬 [إجراء] تفعيل الرد التفرعي على تعليق @{target_username}...")

                    # 1. Click Reply and ensure reply mode is active
                    reply_activated = False
                    for click_target in [btn, span]:
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", click_target)
                            self.sleep(random.uniform(0.8, 1.4))
                            try:
                                click_target.click()
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", click_target)
                            self.sleep(random.uniform(1.2, 2.0))

                            comment_boxes = self.driver.find_elements(
                                By.XPATH,
                                "//textarea | //div[@role='textbox' and @contenteditable='true']"
                            )
                            for cb in comment_boxes:
                                val = (cb.get_attribute("value") or cb.text or "").strip()
                                if target_username.lower() in val.lower():
                                    reply_activated = True
                                    break
                            if reply_activated:
                                break
                        except Exception:
                            pass

                    if not reply_activated:
                        self.log("WARNING", f"⚠️ لم يتم تأكيد وضع الرد التفرعي لـ @{target_username}، جاري المتابعة بحذر...")

                    # 2. Type Public Reply (threaded under target comment)
                    try:
                        try:
                            formatted_reply = reply_txt.format(name=target_username)
                        except Exception:
                            formatted_reply = reply_txt

                        clean_reply = formatted_reply.strip()
                        for prefix in [f"@{target_username}", f"@{target_username.lower()}", f"{target_username}:"]:
                            if clean_reply.lower().startswith(prefix.lower()):
                                clean_reply = clean_reply[len(prefix):].lstrip(" :,!-")

                        comment_box = wait.until(EC.presence_of_element_located((
                            By.XPATH, "//textarea | //div[@role='textbox' and @contenteditable='true']"
                        )))

                        self.type_letter_by_letter(comment_box, clean_reply)
                        self.sleep(random.uniform(1.0, 2.0))

                        # Send Reply
                        post_btns = self.driver.find_elements(
                            By.XPATH,
                            "//div[@role='button' and (text()='Post' or text()='Publier' or text()='نشر') and not(@aria-disabled='true')]"
                        )
                        if post_btns:
                            self.driver.execute_script("arguments[0].click();", post_btns[0])
                        else:
                            comment_box.send_keys(Keys.ENTER)

                        self.stats["replies_sent"] += 1
                        total_replied_this_post += 1
                        self.log("SUCCESS", f"✅ تم نشر الرد التفرعي بنجاح تحت تعليق @{target_username}")
                    except Exception as e:
                        self.stats["errors"] += 1
                        self.log("ERROR", f"❌ فشل نشر الرد التفرعي لـ @{target_username}: {e}")
                        db.save_record(target_username, post_url)
                        continue

                    # 3. Send DM if dm_txt configured
                    dm_sent = False
                    if dm_txt and dm_txt.strip():
                        try:
                            try:
                                formatted_dm = dm_txt.format(name=target_username)
                            except Exception:
                                formatted_dm = dm_txt

                            self._send_instagram_dm(target_username, formatted_dm)
                            self.stats["dms_sent"] += 1
                            self.log("SUCCESS", f"💌 [نجاح] تم إرسال رسالة الخاص بنجاح إلى @{target_username}")
                            dm_sent = True
                        except Exception as e:
                            self.stats["skipped_restricted"] = self.stats.get("skipped_restricted", 0) + 1
                            self.log("WARNING", f"⚠️ [تخطي الخاص] قيود أو خطأ مع @{target_username}: {str(e).splitlines()[0]}")

                    # Always save to database to prevent duplicate attempts
                    db.save_record(target_username, post_url)

                    # Return to post URL only if navigation occurred in the same tab
                    if dm_sent and not self.stop_requested and post_url not in (self.driver.current_url or ""):
                        self.driver.get(post_url)
                        self.sleep(random.uniform(3.5, 5.0))
                        self._open_instagram_comments_drawer()

                    cooldown = random.randint(10, 20)
                    self.status = f"تبريد أمان ({cooldown}ث)"
                    self.log("INFO", f"⏳ فترة تبريد أمان {cooldown} ثانية...")
                    self.sleep(cooldown)

                    # If page had to be reloaded in same tab, break inner loop to re-scan
                    if dm_sent and post_url not in (self.driver.current_url or ""):
                        break

            else:
                # 3. No unprocessed comments in current view -> Scroll comments drawer down to load more!
                self.log("INFO", "📜 تمرير قائمة التعليقات لتحميل المزيد (Scroll Pagination)...")
                has_scrolled = self._scroll_instagram_comments_drawer()
                if not has_scrolled:
                    consecutive_no_new += 1
                else:
                    consecutive_no_new = 0
                self.sleep(random.uniform(2.0, 3.5))

        if total_replied_this_post > 0:
            self.log("SUCCESS", f"🎉 تم الانتهاء من تمرير التعليقات والرد على {total_replied_this_post} تعليق.")
        else:
            self.log("INFO", "✅ اكتمل تمرير كافة تعليقات المنشور بالكامل (تم الوصول لنهاية التعليقات).")

        return scroll_completed_to_bottom

    def _run_instagram(self):
        target_raw = self.config.get("post_url") or "https://www.instagram.com"
        reply_txt = self.config.get("public_reply_template") or "Appreciate your thoughts on this! Check your DMs 💬"
        dm_txt = self.config.get("private_dm_template") or "Hey! Reached out regarding your comment on the post. Hope you're having a great day! 😊"
        check_interval = max(10, int(self.config.get("check_interval_seconds", 30)))

        # Split multiple URLs if user entered multiple links (newline or comma separated)
        target_urls = [u.strip() for u in re.split(r'[\n,]+', target_raw) if u.strip().startswith("http")]
        if not target_urls:
            target_urls = [target_raw.strip()] if target_raw.strip() else ["https://www.instagram.com"]

        db = InstagramDatabaseManager(INSTA_DATABASE_FILE)
        self.log("INFO", f"🚀 بدء أتمتة إنستغرام الاحترافية على {len(target_urls)} منشور/ريلز...")

        while not self.stop_requested:
            for url in target_urls:
                if self.stop_requested:
                    break

                if not self._ensure_valid_window():
                    self.log("ERROR", "❌ تم إنهاء أتمتة إنستغرام لعدم توفر نافذة متصفح نشطة (تم إغلاق المتصفح).")
                    self.status = "المتصفح مغلق"
                    return

                # 1. Scroll through all comments of the post until the scroll completely finishes
                scroll_finished = False
                try:
                    scroll_finished = self._process_instagram_target_post(url, reply_txt, dm_txt, db)
                except Exception as e:
                    self.stats["errors"] += 1
                    self.log("ERROR", f"خطأ أثناء معالجة المنشور {url}: {e}")
                    scroll_finished = True

                # 2. REFRESH ONLY IF THE SCROLL OF COMMENTS FINISHED!
                if scroll_finished and not self.stop_requested:
                    wait_seconds = max(10, min(check_interval, 35))
                    self.log("INFO", f"📡 [مراقبة حية] اكتمل تمرير التعليقات بالكامل. بانتظار تعليقات جديدة (سيتم التحديث وإعادة التمرير بعد {wait_seconds}ث)...")
                    for remaining in range(wait_seconds, 0, -5):
                        if self.stop_requested:
                            break
                        self.status = f"اكتمل التمرير - انتظار ({remaining}ث)"
                        self.sleep(min(5, remaining))

                    if not self.stop_requested:
                        self.log("INFO", "🔄 اكتمل التمرير السابق بالكامل: جاري تحديث الصفحة الآن لإعادة فحص وتمرير التعليقات...")
                        self.status = f"تحديث الصفحة..."
                        self.driver.refresh()
                        self.sleep(random.uniform(3.5, 5.0))

            if self.stop_requested:
                break
