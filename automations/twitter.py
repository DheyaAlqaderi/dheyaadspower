"""
TwitterWorker - Specialized in Automated X / Twitter Direct Message (DM) monitoring:
1. Only opens https://x.com/i/chat/requests/other for accepting requests, replying, and scrolling until finished.
2. Never opens https://x.com/i/chat/requests.
3. After finishing requests, returns to https://x.com/i/chat to automate replies for unread messages
   with scroll pagination to load all users' messages across the inbox.
"""

import os
import json
import re
import time
import random
from typing import Dict, Any, List, Optional, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from automations.base import BaseAutomationWorker

MESSAGES_URL = "https://x.com/i/chat"
REQUESTS_OTHER_URL = "https://x.com/i/chat/requests/other"

# --------------------------------------------------------------------------
# JAVASCRIPT EXTRACTORS & SCROLLERS
# --------------------------------------------------------------------------

# JS to extract conversation details from X's primary DM inbox (https://x.com/i/chat)
# Language-agnostic detection via:
# 1. Multi-lingual aria-description / aria-label keywords
# 2. [data-testid="unread-badge"]
# 3. Twitter's unread blue dot SVG (data-icon="icon-circle-fill" / circle)
# 4. Computed CSS font-weight (>= 700 / bold) on message/sender elements
EXTRACT_CONVERSATIONS_JS = r"""
const rows = Array.from(document.querySelectorAll('[data-testid^="dm-conversation-item-"], [data-testid="conversation"]'));
return rows.map(row => {
    const ariaDesc = (row.getAttribute('aria-description') || '').toLowerCase();
    const ariaLabel = (row.getAttribute('aria-label') || '').toLowerCase();

    // 1. Check international unread keywords in accessibility attributes
    const unreadKeywords = ['unread', 'غير مقروء', 'غير مقروءة', 'رسالة غير مقروءة', 'non lu', 'no leído', 'okunmamış', 'ungelesen', 'non letti', 'nieprzeczytane'];
    let isUnreadAria = false;
    for (const kw of unreadKeywords) {
        if (ariaDesc.includes(kw) || ariaLabel.includes(kw)) {
            isUnreadAria = true;
            break;
        }
    }

    // 2. Specific unread badges in child elements
    let hasUnreadBadge = false;
    if (row.querySelector('[data-testid*="unread" i], [data-testid*="Unread" i], [aria-label*="unread" i], [aria-label*="غير مقروء" i]')) {
        hasUnreadBadge = true;
    }

    // 3. Twitter blue unread circular dot indicator (small round element <= 16px with Twitter Blue background)
    let hasBlueDot = false;
    try {
        const dots = row.querySelectorAll('div, span');
        for (const d of dots) {
            if (d.children.length === 0 && d.offsetWidth > 0 && d.offsetWidth <= 16 && d.offsetHeight <= 16) {
                const style = window.getComputedStyle(d);
                const bg = style.backgroundColor || '';
                if (bg.includes('29, 155, 240') || bg.includes('26, 140, 216')) {
                    hasBlueDot = true;
                    break;
                }
            }
        }
    } catch(e) {}

    const isUnread = isUnreadAria || hasUnreadBadge || hasBlueDot;

    const summary = (row.getAttribute('aria-label') || row.getAttribute('aria-description') || row.innerText || '').slice(0, 100).replace(/\n+/g, ' ').trim();
    const link = row.querySelector('a[href^="/i/chat/"]') || row.closest('a') || row.querySelector('a');
    const href = link ? link.getAttribute('href') : null;

    let convNumId = '';
    if (href) {
        const m = href.match(/\/i\/chat\/([0-9a-zA-Z\-_]+)/);
        if (m) convNumId = m[1];
    }

    const handleMatch = (row.innerText || '').match(/@([a-zA-Z0-9_]{1,15})/);
    const handle = handleMatch ? ('@' + handleMatch[1].toLowerCase()) : '';

    const testId = row.getAttribute('data-testid') || '';

    return {
        id: convNumId || testId || href || summary.slice(0, 30),
        testId: testId,
        convNumId: convNumId,
        handle: handle,
        text: summary,
        unread: isUnread,
        url: href ? (href.startsWith('http') ? href : ('https://x.com' + href)) : null
    };
});
"""

# JS to inspect the active chat pane and determine if the last message was sent by us
CHECK_LAST_MESSAGE_JS = r"""
function inspectLastMessage() {
    // 1. Locate the active message thread container (right pane on desktop, or main pane on mobile)
    const thread = document.querySelector(
        '[data-testid="dm-conversation-thread"], ' +
        '[aria-label*="Timeline: Messages" i], ' +
        '[aria-label*="الجدول الزمني: الرسائل" i], ' +
        'section[role="region"], ' +
        'main[role="main"]'
    );
    const scope = thread || document;

    // 2. Find message entries only inside the active chat thread (EXCLUDE the left conversation list!)
    let entries = Array.from(scope.querySelectorAll('[data-testid="messageEntry"]'));
    if (!entries.length) {
        entries = Array.from(scope.querySelectorAll('[data-testid^="dm-message-item-"], [data-testid="dm-message-bubble"]'));
    }

    if (!entries.length) {
        return { hasMessages: false, isOutgoing: false, text: "" };
    }

    const lastEl = entries[entries.length - 1];
    const text = (lastEl.innerText || '').slice(0, 300).replace(/\n+/g, ' ').trim();
    const aria = (lastEl.getAttribute('aria-label') || '').toLowerCase();
    const testId = (lastEl.getAttribute('data-testid') || '').toLowerCase();

    let isOutgoing = false;
    if (testId.includes('outgoing') || aria.includes('you sent') || aria.includes('أرسلت') || aria.includes('you:')) {
        isOutgoing = true;
    } else {
        try {
            let cur = lastEl;
            for (let i = 0; i < 5 && cur && cur !== scope; i++) {
                const style = window.getComputedStyle(cur);
                const bg = style.backgroundColor || '';
                // Blue background (X brand color) indicates outgoing message
                if (bg.includes('29, 155, 240') || bg.includes('26, 140, 216') || bg.includes('var(--color-brand)')) {
                    isOutgoing = true;
                    break;
                }
                if (style.alignSelf === 'flex-end' || style.justifyContent === 'flex-end') {
                    isOutgoing = true;
                    break;
                }
                cur = cur.parentElement;
            }
        } catch(e) {}
    }

    return {
        hasMessages: true,
        isOutgoing: isOutgoing,
        text: text
    };
}
return inspectLastMessage();
"""

# JS to detect X rate-limit or restriction dialogs/toasts
CHECK_X_RESTRICTIONS_JS = r"""
function checkRestrictions() {
    const alerts = Array.from(document.querySelectorAll(
        '[data-testid="toast"], div[role="alert"], div[role="dialog"], [data-testid="sheetDialog"], div[data-testid="error-detail"]'
    ));

    const keywords = [
        'daily limit', 'الحد اليومي', 
        'can no longer send', 'لم يعد بإمكانك إرسال',
        'account is locked', 'تم قفل الحساب',
        'temporarily restricted', 'مقيد مؤقتاً',
        'unusual activity', 'نشاط غير معتاد'
    ];

    for (const a of alerts) {
        if (!a.offsetParent && a.offsetHeight === 0) continue;
        const txt = (a.innerText || '').toLowerCase();
        for (const kw of keywords) {
            if (txt.includes(kw.toLowerCase())) {
                return { detected: true, type: kw, message: txt.slice(0, 150) };
            }
        }
    }
    return { detected: false };
}
return checkRestrictions();
"""

# JS to smoothly scroll down the primary DM inbox to load all users' messages (Pagination)
SCROLL_MAIN_INBOX_JS = r"""
function scrollMainInbox() {
    // 1. Try finding conversation row parent container that is scrollable
    const item = document.querySelector('[data-testid^="dm-conversation-item-"], [data-testid="conversation"]');
    let el = item ? item.parentElement : null;
    while (el && el !== document.body) {
        const style = window.getComputedStyle(el);
        const overflowY = style.overflowY;
        if ((overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
            const prev = el.scrollTop;
            el.scrollBy({ top: 650, behavior: 'smooth' });
            return { scrolled: true, mode: 'parent', prev: prev, current: el.scrollTop, max: el.scrollHeight };
        }
        el = el.parentElement;
    }

    // 2. Specific selectors
    const selectors = [
        '[data-testid="dm-conversation-list"]',
        '[aria-label*="Messages" i]',
        '[aria-label*="الرسائل" i]',
        '[aria-label*="Timeline" i]',
        'section[role="region"]',
        'div[data-viewport-type="element"]'
    ];
    for (const sel of selectors) {
        const c = document.querySelector(sel);
        if (c && c.scrollHeight > c.clientHeight) {
            const prev = c.scrollTop;
            c.scrollBy({ top: 650, behavior: 'smooth' });
            return { scrolled: true, mode: sel, prev: prev, current: c.scrollTop, max: c.scrollHeight };
        }
    }

    // 3. Fallback: window scroll
    window.scrollBy({ top: 650, behavior: 'smooth' });
    document.documentElement.scrollBy({ top: 650, behavior: 'smooth' });
    return { scrolled: true, mode: 'window' };
}
return scrollMainInbox();
"""

# JS to scroll the primary DM inbox back to the top
SCROLL_TOP_MAIN_INBOX_JS = r"""
function scrollTopMainInbox() {
    const item = document.querySelector('[data-testid^="dm-conversation-item-"], [data-testid="conversation"]');
    let el = item ? item.parentElement : null;
    while (el && el !== document.body) {
        const style = window.getComputedStyle(el);
        const overflowY = style.overflowY;
        if ((overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
            el.scrollTo({ top: 0, behavior: 'smooth' });
            return true;
        }
        el = el.parentElement;
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
    document.documentElement.scrollTo({ top: 0, behavior: 'smooth' });
    return true;
}
return scrollTopMainInbox();
"""

# JS to extract request items ONLY from https://x.com/i/chat/requests/other
EXTRACT_REQUESTS_JS = r"""
const scroller = document.querySelector('[data-testid="dm-message-requests-scroller"]') || 
                 document.getElementById('x-chat-message-requests-Hidden') || 
                 document;

const rows = Array.from(scroller.querySelectorAll(
    '[data-testid^="dm-message-request-item-"], ' +
    '[id^="dm-conversation-option-"], ' +
    'a[role="option"][href*="/i/chat/requests/other/"], ' +
    'a[href*="/i/chat/requests/other/"], ' +
    'a[role="option"], ' +
    'li[data-index] a'
));

const unique = [];
const seen = new Set();

for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const testId = row.getAttribute('data-testid') || '';
    const elemId = row.getAttribute('id') || '';
    const link = row.tagName.toLowerCase() === 'a' ? row : (row.querySelector('a') || row.closest('a'));
    const href = link ? link.getAttribute('href') : null;
    const text = (row.innerText || '').slice(0, 120).replace(/\n+/g, ' ').trim();

    let key = testId || elemId;
    if (!key && href) key = href;
    if (!key) key = `req_item_${i}_${text.slice(0, 30)}`;

    let convNumId = '';
    if (href) {
        const m = href.match(/\/i\/chat\/(?:requests\/other\/)?([0-9a-zA-Z\-_]+)/);
        if (m) convNumId = m[1];
    }
    const handleMatch = text.match(/@([a-zA-Z0-9_]{1,15})/);
    const handle = handleMatch ? ('@' + handleMatch[1].toLowerCase()) : '';

    if (key && !seen.has(key)) {
        seen.add(key);
        unique.push({
            id: key,
            testId: testId,
            elementId: elemId,
            convNumId: convNumId,
            handle: handle,
            text: text,
            url: href ? (href.startsWith('http') ? href : ('https://x.com' + href)) : null
        });
    }
}
return unique;
"""

# JS to smoothly scroll the requests container on requests/other for infinite scroll pagination
SCROLL_REQUESTS_CONTAINER_JS = r"""
function scrollReq() {
    const scroller = document.querySelector('[data-testid="dm-message-requests-scroller"]') ||
                     document.getElementById('x-chat-message-requests-Hidden');
    if (scroller && (scroller.scrollHeight > scroller.clientHeight || scroller.offsetHeight > 0)) {
        const prev = scroller.scrollTop;
        scroller.scrollBy({ top: 600, behavior: 'smooth' });
        return { scrolled: true, mode: 'dm-message-requests-scroller', prev: prev, current: scroller.scrollTop };
    }

    const item = document.querySelector('[data-testid^="dm-message-request-item-"], [id^="dm-conversation-option-"], a[href*="/i/chat/requests/other/"]');
    let el = item ? item.parentElement : null;
    while (el && el !== document.body) {
        const style = window.getComputedStyle(el);
        const overflowY = style.overflowY;
        if ((overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
            const prev = el.scrollTop;
            el.scrollBy({ top: 600, behavior: 'smooth' });
            return { scrolled: true, mode: 'parent', prev: prev, current: el.scrollTop };
        }
        el = el.parentElement;
    }

    window.scrollBy({ top: 600, behavior: 'smooth' });
    document.documentElement.scrollBy({ top: 600, behavior: 'smooth' });
    return { scrolled: true, mode: 'window' };
}
return scrollReq();
"""

# --------------------------------------------------------------------------
# XPATHS
# --------------------------------------------------------------------------

ACCEPT_BUTTON_XPATHS = [
    '//button[contains(translate(., "ACCEPT", "accept"), "accept")]',
    '//button[contains(., "قبول")]',
    '//button[@data-testid="acceptButton"]',
    '//button[@data-testid="dm-request-accept"]',
    '//button[@data-testid="dm-accept-button"]',
    '//button[@data-testid="dmRequestAcceptButton"]',
    '//button[@data-testid="dm-message-request-accept"]',
    '//button[@aria-label="Accept" or @aria-label="قبول"]',
    '//button[contains(@aria-label, "Accept") or contains(@aria-label, "قبول")]',
    '//div[@data-testid="dm-container"]//button[contains(translate(., "ACCEPT", "accept"), "accept") or contains(., "قبول")]',
    '//div[@data-testid="dm-conversation-panel"]//button[contains(translate(., "ACCEPT", "accept"), "accept") or contains(., "قبول")]',
    '//aside//button[contains(translate(., "ACCEPT", "accept"), "accept") or contains(., "قبول")]',
    '//button[contains(., "Accept message request") or contains(., "قبول طلب المراسلة")]',
]

CONFIRMATION_ACCEPT_XPATHS = [
    '//div[@role="dialog"]//button[contains(translate(., "ACCEPT", "accept"), "accept") or contains(., "قبول")]',
    '//div[@data-testid="sheetDialog"]//button[contains(translate(., "ACCEPT", "accept"), "accept") or contains(., "قبول")]',
    '//div[@data-testid="confirmationSheetConfirm"]',
    '//button[@data-testid="confirmationSheetConfirm"]',
    '//div[@role="dialog"]//button[contains(@data-testid, "confirm") or contains(@data-testid, "Confirm")]',
]

BACK_BUTTON_XPATHS = [
    '//button[@data-testid="dm-message-requests-back"]',
    '//button[@data-testid="app-bar-back"]',
    '//*[@data-testid="dm-message-requests-back"]',
    '//*[@data-testid="app-bar-back"]',
    '//button[@aria-label="Back" or @aria-label="رجوع"]',
    '//button[contains(@aria-label, "Back") or contains(@aria-label, "رجوع")]',
]

COMPOSER_XPATHS = [
    '//*[@data-testid="dm-composer-textarea"]',
    '//div[@data-testid="dm-composer-textarea"]',
    '//div[@role="textbox" and @data-testid="dm-composer-textarea"]',
    '//div[@role="textbox" and contains(@class, "public-DraftEditor-content")]',
    '//*[@data-testid="dm-conversation-panel"]//*[@role="textbox"]',
    '//*[@data-testid="dm-container"]//*[@role="textbox"]',
    '//aside[@aria-label]//*[@role="textbox"]',
]

SEND_BUTTON_XPATHS = [
    '//button[@data-testid="dm-composer-send-button"]',
    '//*[@data-testid="dm-composer-send-button"]',
    '//button[@aria-label="Send" or @aria-label="إرسال" or @aria-label="Send message"]',
    '//button[contains(@data-testid, "send") and not(@disabled)]',
    '//*[@data-testid="dmComposerSendButton"]',
]


class TwitterWorker(BaseAutomationWorker):
    """Worker specialized in automated X / Twitter DM monitoring, requests acceptance, and replies."""

    def _get_history_filepath(self) -> str:
        """Returns the persistent JSON file path for DM reply history for this profile."""
        clean_id = "".join(c for c in str(self.profile_id) if c.isalnum() or c in ("-", "_"))
        workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(workspace_dir, f"twitter_dm_history_{clean_id}.json")

    def _load_history(self) -> Dict[str, float]:
        """Loads previous reply timestamps for users/conversations from persistent JSON file."""
        path = self._get_history_filepath()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return {str(k): float(v) for k, v in data.items()}
            except Exception as e:
                self.log("WARNING", f"خطأ أثناء قراءة سجل الردود السابق: {e}")
        return {}

    def _save_history(self, history: Dict[str, float]) -> None:
        """Flushes reply timestamps to disk, pruning entries older than 60 days."""
        path = self._get_history_filepath()
        try:
            cutoff = time.time() - (60 * 86400)
            cleaned = {str(k): float(v) for k, v in history.items() if float(v) >= cutoff}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cleaned, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء حفظ سجل الردود: {e}")

    def _check_cooldown(self, item: Dict[str, Any], history: Dict[str, float], cooldown_hours: float) -> Tuple[bool, float]:
        """
        Checks if this conversation or user has already received a reply within cooldown_hours.
        Returns (is_in_cooldown, remaining_seconds).
        """
        if cooldown_hours <= 0:
            return False, 0.0

        cooldown_seconds = cooldown_hours * 3600.0
        now = time.time()

        keys_to_check = []
        if item.get("convNumId"):
            keys_to_check.append(str(item["convNumId"]))
        if item.get("handle"):
            keys_to_check.append(str(item["handle"]).lower())
        if item.get("testId"):
            keys_to_check.append(str(item["testId"]))
        if item.get("id"):
            keys_to_check.append(str(item["id"]))
        if item.get("url"):
            clean_url = str(item["url"]).replace("https://x.com", "")
            keys_to_check.append(clean_url)
            keys_to_check.append(str(item["url"]))

        for k in keys_to_check:
            if k and k in history:
                last_reply = history[k]
                elapsed = now - last_reply
                if elapsed < cooldown_seconds:
                    return True, (cooldown_seconds - elapsed)

        return False, 0.0

    def _record_reply_history(self, item: Dict[str, Any], history: Dict[str, float]) -> None:
        """Records the timestamp of reply for all associated identifiers into history and flushes to disk."""
        now = time.time()
        keys_to_record = []
        if item.get("convNumId"):
            keys_to_record.append(str(item["convNumId"]))
        if item.get("handle"):
            keys_to_record.append(str(item["handle"]).lower())
        if item.get("testId"):
            keys_to_record.append(str(item["testId"]))
        if item.get("id"):
            keys_to_record.append(str(item["id"]))
        if item.get("url"):
            clean_url = str(item["url"]).replace("https://x.com", "")
            keys_to_record.append(clean_url)
            keys_to_record.append(str(item["url"]))

        # Inspect current driver URL to see if it has conversation ID
        try:
            curr_url = self.driver.current_url or ""
            m = re.search(r"/i/chat/([0-9a-zA-Z\-_]+)", curr_url)
            if m:
                keys_to_record.append(m.group(1))
        except Exception:
            pass

        for k in keys_to_record:
            if k:
                history[k] = now

        # Immediately flush history to disk to persist across loops and restarts
        try:
            self._save_history(history)
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء حفظ سجل الردود: {e}")

    def _check_x_rate_limit_or_restrictions(self) -> Tuple[bool, str]:
        """
        Detects if X has displayed a daily DM limit dialog, account lock, or restriction toast.
        Returns (is_restricted, error_message).
        """
        try:
            res = self.driver.execute_script(CHECK_X_RESTRICTIONS_JS)
            if isinstance(res, dict) and res.get("detected"):
                msg = res.get("message") or res.get("type") or "تقييد غير محدد"
                self.log("ERROR", f"🛑 تنبيه أمان من تويتر: تم اكتشاف تقييد أو حد إرسال: \"{msg}\"")
                return True, msg
        except Exception:
            pass
        return False, ""

    def _format_message(self, template: str, item: Optional[Dict[str, Any]]) -> str:
        """Interpolates {name} and {handle} variables into the message template."""
        if not template or not item:
            return template or ""

        handle = (item.get("handle") or "").strip()
        clean_handle = handle.replace("@", "").strip()

        # Extract name from item text if available (usually "Display Name, @handle, ...")
        name = ""
        txt = item.get("text") or ""
        if "," in txt:
            parts = [p.strip() for p in txt.split(",")]
            if parts and parts[0] and not parts[0].startswith("@"):
                name = parts[0]
        if not name:
            name = clean_handle or "صديقنا"

        formatted = template
        if "{name}" in formatted:
            formatted = formatted.replace("{name}", name)
        if "{handle}" in formatted:
            formatted = formatted.replace("{handle}", handle or (f"@{clean_handle}" if clean_handle else ""))

        return formatted

    def _is_last_message_from_us(self, our_message_template: str = "") -> Tuple[bool, str]:
        """
        Inspects message bubbles in the active conversation panel.
        Returns (is_outgoing, last_message_text).
        """
        try:
            res = self.driver.execute_script(CHECK_LAST_MESSAGE_JS)
            if isinstance(res, dict) and res.get("hasMessages"):
                is_outgoing = bool(res.get("isOutgoing"))
                txt = str(res.get("text") or "").strip()
                if not is_outgoing and our_message_template:
                    # Strip variables to get the core message prefix for verification
                    clean_tpl = re.sub(r"\{[a-zA-Z0-9_]+\}", "", our_message_template).strip()[:25]
                    if clean_tpl and len(clean_tpl) >= 6 and clean_tpl in txt:
                        is_outgoing = True
                return is_outgoing, txt
        except Exception:
            pass
        return False, ""

    def _type_and_send_message(self, composer, message: str) -> bool:
        """
        Types message into X's Draft.js composer, dispatches React events,
        clicks the send button (or sends Return), and verifies delivery and restrictions.
        """
        try:
            self.js_click(composer)
            self.sleep(random.uniform(0.3, 0.6))
        except Exception:
            pass

        try:
            self.log("INFO", f"✍️ كتابة الرد التلقائي: \"{message[:40]}...\"")
            self.type_letter_by_letter(composer, message)
            self.sleep(random.uniform(0.6, 1.2))
        except Exception as e:
            self.log("ERROR", f"فشل أثناء كتابة الرسالة: {e}")
            return False

        # Dispatch synthetic input and change events so React/Draft.js recognizes input & enables send button
        try:
            self.driver.execute_script("""
                const el = arguments[0];
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            """, composer)
            self.sleep(0.4)
        except Exception:
            pass

        sent = False
        # 1. Try send button
        for xp in SEND_BUTTON_XPATHS:
            try:
                send_btns = self.driver.find_elements(By.XPATH, xp)
                for sbtn in send_btns:
                    if sbtn.is_displayed() and sbtn.is_enabled() and sbtn.get_attribute("aria-disabled") != "true":
                        self.log("INFO", "🚀 النقر على زر الإرسال...")
                        self.js_click(sbtn)
                        sent = True
                        self.sleep(random.uniform(1.2, 2.0))
                        break
                if sent:
                    break
            except Exception:
                pass

        # 2. Fallback to Enter key
        if not sent:
            try:
                self.log("INFO", "⌨️ الضغط على مفتاح Enter/Return للإرسال...")
                composer.send_keys(Keys.RETURN)
                sent = True
                self.sleep(random.uniform(1.2, 2.0))
            except Exception as e:
                self.log("WARNING", f"تعذر الضغط على Enter: {e}")

        # 3. Post-send rate-limit / restriction check
        is_restricted, rest_msg = self._check_x_rate_limit_or_restrictions()
        if is_restricted:
            self.log("ERROR", f"🛑 توقف الإرسال فوراً بسبب قيود تويتر: {rest_msg}")
            return False

        return sent

    def execute(self):
        self._run_twitter_dm_auto_reply()

    def _run_twitter_dm_auto_reply(self):
        inbox_url = (self.config.get("post_url") or "").strip()
        if not inbox_url or not inbox_url.startswith("http") or "x.com" not in inbox_url:
            inbox_url = MESSAGES_URL

        # Auto-reply message template
        message = (
            self.config.get("private_dm_template") or
            self.config.get("dm_template") or
            self.config.get("public_reply_template") or
            "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨"
        ).strip()

        interval = float(self.config.get("check_interval_seconds") or 12.0)
        max_replies_per_hour = int(self.config.get("max_replies_per_hour") or 25)
        check_requests_enabled = bool(self.config.get("check_requests", True))
        cd_val = self.config.get("cooldown_hours")
        cooldown_hours = float(cd_val if cd_val is not None else 24.0)
        batch_limit = int(self.config.get("batch_limit") or 6)
        skip_if_last_outgoing = bool(self.config.get("skip_if_last_outgoing", True))

        # Load reply history from disk
        history = self._load_history()
        self._save_history(history)

        self.log("INFO", f"🚀 بدء تشغيل أتمتة الرد التلقائي على رسائل X (تويتر) الخاصة: {inbox_url}")
        self.log("INFO", f"💬 رسالة الرد: \"{message[:60]}...\" (الحد الأقصى: {max_replies_per_hour}/ساعة)")
        if cooldown_hours <= 0:
            self.log("INFO", "⏳ فترة الانتظار لإعادة الرد لنفس المستخدم (Cooldown): معطلة (0 ساعة - الرد على جميع الرسائل الواردة فوراً)")
        else:
            self.log("INFO", f"⏳ فترة الانتظار لإعادة الرد لنفس المستخدم (Cooldown): {cooldown_hours} ساعة")
        if history:
            self.log("INFO", f"💾 تم تحميل سجل الردود السابق: {len(history)} معرف محادثة/مستخدم مسجل")

        replied_text_by_id: Dict[str, str] = {}
        reply_timestamps: List[float] = []
        last_requests_check_time = 0.0

        if not self._ensure_valid_window():
            self.log("ERROR", "تعذر الاتصال بنافذة المتصفح")
            return

        # ------------------------------------------------------------------
        # 1. PROCESS INITIAL BATCH OF REQUESTS AT https://x.com/i/chat/requests/other
        # (NEVER open https://x.com/i/chat/requests)
        # ------------------------------------------------------------------
        if check_requests_enabled or "requests/other" in inbox_url:
            self.log("INFO", f"📥 فحص دفعة أولية من طلبات المراسلة: {REQUESTS_OTHER_URL}")
            self._process_requests_other_pipeline(
                message=message,
                reply_timestamps=reply_timestamps,
                max_replies_per_hour=max_replies_per_hour,
                history=history,
                cooldown_hours=cooldown_hours,
                batch_limit=batch_limit
            )
            last_requests_check_time = time.time()

            self.log("INFO", f"🏠 الانتقال إلى صندوق الرسائل الرئيسي: {MESSAGES_URL}")
            self._return_to_main_chat()

        # Check for login redirection
        curr_url = (self.driver.current_url or "").lower()
        if "login" in curr_url or "flow/login" in curr_url:
            self.log("WARNING", "⚠️ يبدو أن الحساب غير مسجل الدخول في X. يرجى تسجيل الدخول في نافذة المتصفح أولاً.")

        # Wait for DM container to settle in main chat
        self._wait_for_inbox(timeout=15)

        # ------------------------------------------------------------------
        # 2. MAIN INBOX MONITORING WITH DYNAMIC PAGINATION (https://x.com/i/chat)
        # Exhaustively scans users' messages across the inbox, replies to unreads
        # (Only replies to each user once a day / per cooldown_hours)
        # Interleaves periodic checks of requests/other so neither stream is delayed
        # ------------------------------------------------------------------
        while not self.stop_requested:
            if not self._ensure_valid_window():
                self.sleep(5)
                continue

            now = time.time()
            reply_timestamps = [t for t in reply_timestamps if now - t < 3600]

            # Dynamic config reload from profile metadata
            try:
                if hasattr(self.runner_hub, "adspower_client"):
                    all_meta = self.runner_hub.adspower_client._load_profiles_metadata()
                    tw_cfg = all_meta.get(self.profile_id, {}).get("platforms", {}).get("twitter", {})
                    if tw_cfg:
                        new_msg = (
                            tw_cfg.get("dm_template") or
                            tw_cfg.get("private_dm_template") or
                            tw_cfg.get("public_reply_template") or
                            message
                        ).strip()
                        if new_msg and new_msg != message:
                            self.log("INFO", f"📝 تم تحديث قالب الرد ديناميكياً: \"{new_msg[:50]}...\"")
                            message = new_msg

                        if "cooldown_hours" in tw_cfg and tw_cfg["cooldown_hours"] is not None:
                            new_cd = float(tw_cfg["cooldown_hours"])
                            if new_cd != cooldown_hours:
                                if new_cd <= 0:
                                    self.log("INFO", "⚙️ تم تحديث فترة الانتظار (Cooldown) ديناميكياً: معطلة (0 ساعة - الرد على جميع الرسائل الواردة فوراً)")
                                    replied_text_by_id.clear()
                                else:
                                    self.log("INFO", f"⚙️ تم تحديث فترة الانتظار (Cooldown) ديناميكياً: {new_cd} ساعة")
                                cooldown_hours = new_cd

                        if "max_replies_per_hour" in tw_cfg:
                            new_max = int(tw_cfg.get("max_replies_per_hour", max_replies_per_hour))
                            if new_max != max_replies_per_hour:
                                self.log("INFO", f"⚙️ تم تحديث الحد الأقصى للردود بالساعة ديناميكياً: {new_max}")
                                max_replies_per_hour = new_max

                        if "check_interval_seconds" in tw_cfg:
                            new_interval = float(tw_cfg.get("check_interval_seconds", interval))
                            if new_interval != interval:
                                self.log("INFO", f"⚙️ تم تحديث الفاصل الزمني ديناميكياً: {new_interval}ث")
                                interval = new_interval

                        if "check_requests" in tw_cfg:
                            new_req = bool(tw_cfg.get("check_requests"))
                            if new_req != check_requests_enabled:
                                self.log("INFO", f"⚙️ تم تحديث فحص الطلبات ديناميكياً: {'مفعّل' if new_req else 'معطّل'}")
                                check_requests_enabled = new_req

                        if "batch_limit" in tw_cfg:
                            new_batch = int(tw_cfg.get("batch_limit", batch_limit))
                            if new_batch != batch_limit:
                                batch_limit = new_batch

                        if "skip_if_last_outgoing" in tw_cfg:
                            self.config["skip_if_last_outgoing"] = bool(tw_cfg.get("skip_if_last_outgoing"))
            except Exception:
                pass

            # Sync in-memory history if file was updated externally (e.g. cleared via API)
            history_path = self._get_history_filepath()
            try:
                if os.path.exists(history_path):
                    disk_hist = self._load_history()
                    if len(disk_hist) < len(history):
                        history.clear()
                        history.update(disk_hist)
                        replied_text_by_id.clear()
                        self.log("INFO", f"🔄 تم تحديث ذاكرة سجل الردود من القرص ({len(history)} سجل)")
                else:
                    if history:
                        history.clear()
                        replied_text_by_id.clear()
                        self.log("INFO", "🔄 تم تصفير سجل الردود في الذاكرة لتطابق تصفير الملف من الواجهة.")
            except Exception:
                pass

            # Interleaved check of requests/other (every 180 seconds in configured batch_limit)
            if check_requests_enabled and (now - last_requests_check_time > 180):
                self.log("INFO", f"⏰ فحص دوري لطلبات المراسلة في {REQUESTS_OTHER_URL}...")
                self._process_requests_other_pipeline(
                    message=message,
                    reply_timestamps=reply_timestamps,
                    max_replies_per_hour=max_replies_per_hour,
                    history=history,
                    cooldown_hours=cooldown_hours,
                    batch_limit=batch_limit
                )
                last_requests_check_time = time.time()

                self._return_to_main_chat()

            # Ensure inbox list DOM is present
            inbox_present = self._is_inbox_present()
            if not inbox_present:
                self.log("INFO", f"🔄 إعادة التوجيه إلى صندوق الرسائل ({MESSAGES_URL})...")
                try:
                    self.driver.get(MESSAGES_URL)
                    self.sleep(random.uniform(2.5, 4.0))
                    self._wait_for_inbox(timeout=15)
                except Exception as e:
                    self.log("WARNING", f"تعذر تحميل صندوق الرسائل: {e}")
                    self.sleep(interval)
                    continue

            # Scan and reply to unread messages across main inbox with dynamic exhaustive pagination
            self._scan_and_reply_main_inbox_with_pagination(
                message=message,
                replied_text_by_id=replied_text_by_id,
                reply_timestamps=reply_timestamps,
                max_replies_per_hour=max_replies_per_hour,
                history=history,
                cooldown_hours=cooldown_hours
            )

            self.status = f"مراقبة الرسائل الواردة (~كل {int(interval)}ث)..."
            self._jittered_sleep(interval)

    # ----------------------------------------------------------------------
    # REQUESTS/OTHER PIPELINE (ONLY https://x.com/i/chat/requests/other)
    # ----------------------------------------------------------------------
    def _process_requests_other_pipeline(
        self,
        message: str,
        reply_timestamps: List[float],
        max_replies_per_hour: int,
        history: Optional[Dict[str, float]] = None,
        cooldown_hours: float = 24.0,
        batch_limit: int = 6
    ) -> int:
        """
        Navigates ONLY to https://x.com/i/chat/requests/other,
        clicks on user chat, accepts request, sends reply, returns to list,
        paginates via smooth scrolling. Processes up to batch_limit requests
        to allow interleaved switching between requests and primary inbox.
        """
        total_handled = 0
        processed_keys = set()
        req_url = REQUESTS_OTHER_URL

        self.log("INFO", f"🔍 فحص صفحة طلبات المراسلة: {req_url} (سقف الدفعة: {batch_limit})")
        self.status = "فحص طلبات المراسلة (requests/other)..."

        try:
            self.driver.get(req_url)
            self.sleep(random.uniform(3.5, 5.0))
        except Exception as e:
            self.log("WARNING", f"تعذر فتح صفحة الطلبات {req_url}: {e}")
            return 0

        consecutive_empty_scrolls = 0
        max_empty_scrolls = 2

        while not self.stop_requested:
            now = time.time()
            reply_timestamps[:] = [t for t in reply_timestamps if now - t < 3600]

            if len(reply_timestamps) >= max_replies_per_hour:
                self.log("WARNING", f"⚠️ تم الوصول للحد الأقصى للردود بالساعة ({max_replies_per_hour}). التوقف مؤقتاً لحماية الحساب...")
                break

            # Check if batch limit reached to return to main inbox quickly
            if total_handled >= batch_limit:
                self.log("INFO", f"⚡ تم معالجة دفعة كاملة من طلبات المراسلة ({total_handled} طلبات). الانتقال لمتابعة الصندوق الرئيسي لضمان الرد السريع...")
                break

            # Check for X rate-limit or account lock
            is_restricted, rest_msg = self._check_x_rate_limit_or_restrictions()
            if is_restricted:
                self.log("ERROR", f"🛑 توقف معالجة الطلبات بسبب قيود تويتر: {rest_msg}")
                break

            # Extract request items currently in DOM
            items = self._extract_requests()
            unprocessed = [item for item in items if item["id"] not in processed_keys]

            if unprocessed:
                consecutive_empty_scrolls = 0
                item = unprocessed[0]
                processed_keys.add(item["id"])

                # Check cooldown if already replied
                if history is not None and cooldown_hours > 0:
                    is_cooling, rem_sec = self._check_cooldown(item, history, cooldown_hours)
                    if is_cooling:
                        rem_h = rem_sec / 3600.0
                        rem_m = rem_sec / 60.0
                        t_str = f"{rem_h:.1f} ساعة" if rem_h >= 1.0 else f"{int(rem_m)} دقيقة"
                        self.log("INFO", f"⏳ تخطي طلب المراسلة ({item['text'][:35]}...): تم الرد عليه مسبقاً (متبقي {t_str}).")
                        continue

                stamp = time.strftime("%H:%M:%S")
                self.status = f"قبول والرد على طلب المراسلة ({total_handled + 1}/{batch_limit})..."

                success = self._handle_single_request(item, message, req_url)
                if success:
                    reply_timestamps.append(time.time())
                    self.stats["dms_sent"] += 1
                    self.stats["replies_sent"] += 1
                    total_handled += 1
                    if history is not None:
                        self._record_reply_history(item, history)
                    self.log("SUCCESS", f"✓ [{stamp}] تم قبول الطلب والرد بنجاح على: ({item['text'][:35]}...)")
                    self.sleep(random.uniform(3.0, 5.5))
                else:
                    self.sleep(random.uniform(1.5, 2.5))
            else:
                consecutive_empty_scrolls += 1
                if consecutive_empty_scrolls >= max_empty_scrolls:
                    self.log("INFO", f"✨ لا توجد طلبات مراسلة إضافية في {req_url}")
                    break

                # No unprocessed items visible in DOM -> Scroll down scroller (Pagination)
                self.status = "تمرير قائمة الطلبات لتحميل الدفعة التالية..."
                self.log("INFO", "📜 تمرير قائمة طلبات المراسلة لتحميل المزيد...")

                self._scroll_requests_container()
                self.sleep(random.uniform(2.0, 3.2))

                # Re-check after scroll
                new_items = self._extract_requests()
                new_unprocessed = [item for item in new_items if item["id"] not in processed_keys]

                if not new_unprocessed:
                    consecutive_empty_scrolls += 1
                    if consecutive_empty_scrolls >= max_empty_scrolls:
                        self.log("INFO", f"✨ تم الانتهاء من فحص قائمة الطلبات في {req_url}")
                        break
                else:
                    consecutive_empty_scrolls = 0

        self.log("SUCCESS", f"🎉 إجمالي طلبات المراسلة التي تم قبولها والرد عليها في هذه الدورة: {total_handled}")
        return total_handled

    def _extract_requests(self) -> List[Dict[str, Any]]:
        """Extracts message request items from DOM via JS and XPath fallbacks."""
        try:
            res = self.driver.execute_script(EXTRACT_REQUESTS_JS)
            if isinstance(res, list) and len(res) > 0:
                return res
        except Exception:
            pass

        items = []
        try:
            rows = self.driver.find_elements(
                By.XPATH,
                '//*[starts-with(@data-testid, "dm-message-request-item-") or '
                'starts-with(@id, "dm-conversation-option-") or '
                '@role="option"]'
            )
            for i, row in enumerate(rows):
                tid = row.get_attribute("data-testid") or ""
                eid = row.get_attribute("id") or ""
                desc = row.get_attribute("aria-description") or row.get_attribute("aria-label") or ""
                text = (row.text or "").replace("\n", " ")
                href = None
                links = row.find_elements(By.XPATH, './/a[contains(@href, "/i/chat/requests/other/")]')
                if links:
                    href = links[0].get_attribute("href")
                elif row.tag_name.lower() == "a":
                    href = row.get_attribute("href")

                key = tid or eid or href or f"req_fb_{i}_{text[:30]}"
                conv_num_id = ""
                if href:
                    m = re.search(r"/i/chat/(?:requests/other/)?([0-9a-zA-Z\-_]+)", href)
                    if m:
                        conv_num_id = m.group(1)

                handle = ""
                hm = re.search(r"@([a-zA-Z0-9_]{1,15})", text)
                if hm:
                    handle = "@" + hm.group(1).lower()

                items.append({
                    "id": key,
                    "testId": tid,
                    "elementId": eid,
                    "convNumId": conv_num_id,
                    "handle": handle,
                    "text": desc or text[:80],
                    "url": href
                })
        except Exception:
            pass

        return items

    def _scroll_requests_container(self) -> None:
        """Scrolls the message requests container down to trigger pagination."""
        try:
            self.driver.execute_script(SCROLL_REQUESTS_CONTAINER_JS)
            self.sleep(0.5)
        except Exception:
            pass

        try:
            scroller_els = self.driver.find_elements(By.XPATH, '//*[@data-testid="dm-message-requests-scroller"] | //*[@id="x-chat-message-requests-Hidden"]')
            if scroller_els and scroller_els[0].is_displayed():
                scroller_els[0].send_keys(Keys.PAGE_DOWN)
            else:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body.send_keys(Keys.PAGE_DOWN)
        except Exception:
            pass

    def _open_request_chat(self, item: Dict[str, Any]) -> bool:
        """Clicks the user request item in the list or navigates to its URL."""
        test_id = item.get("testId") or ""
        elem_id = item.get("elementId") or ""
        conv_url = item.get("url") or ""
        conv_text = item.get("text") or conv_url

        self.log("INFO", f"👆 النقر على شات المستخدم لطلب المراسلة: ({conv_text[:35]}...)...")

        clicked = False
        try:
            clicked = bool(self.driver.execute_script("""
                const testId = arguments[0];
                const elemId = arguments[1];
                const url = arguments[2];

                let el = null;
                if (testId) el = document.querySelector(`[data-testid="${testId}"]`);
                if (!el && elemId) el = document.getElementById(elemId);
                if (!el && url) {
                    const clean = url.replace('https://x.com', '');
                    el = document.querySelector(`a[href*="${clean}"]`);
                }
                if (!el) {
                    const scroller = document.querySelector('[data-testid="dm-message-requests-scroller"]') || 
                                     document.getElementById('x-chat-message-requests-Hidden');
                    if (scroller) el = scroller.querySelector('li a');
                }

                if (el) {
                    el.scrollIntoView({ block: 'center', behavior: 'instant' });
                    const opts = { bubbles: true, cancelable: true, view: window };
                    el.dispatchEvent(new MouseEvent('pointerdown', opts));
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new MouseEvent('pointerup', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                    el.dispatchEvent(new MouseEvent('click', opts));
                    el.click();

                    const inner = el.querySelector('.cursor-pointer') || el.firstElementChild;
                    if (inner) {
                        inner.dispatchEvent(new MouseEvent('click', opts));
                        inner.click();
                    }
                    return true;
                }
                return false;
            """, test_id, elem_id, conv_url))
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء النقر بـ JS: {e}")

        self.sleep(random.uniform(1.8, 2.6))

        # Fallback click via Selenium
        if not clicked:
            candidate_xpaths = []
            if test_id:
                candidate_xpaths.append(f'//*[@data-testid="{test_id}"]')
            if elem_id:
                candidate_xpaths.append(f'//*[@id="{elem_id}"]')
            if conv_url:
                clean_href = conv_url.replace("https://x.com", "")
                candidate_xpaths.append(f'//a[contains(@href, "{clean_href}")]')
            candidate_xpaths.append('//*[@data-testid="dm-message-requests-scroller"]//li//a')
            candidate_xpaths.append('//div[@id="x-chat-message-requests-Hidden"]//li//a')

            for xp in candidate_xpaths:
                try:
                    els = self.driver.find_elements(By.XPATH, xp)
                    if els and els[0].is_displayed():
                        self.js_click(els[0])
                        self.sleep(random.uniform(1.8, 2.6))
                        clicked = True
                        break
                except Exception:
                    pass

        # Fallback direct navigation if chat did not load
        if not self._is_accept_or_composer_visible() and conv_url:
            try:
                self.log("INFO", f"🔗 الانتقال المباشر لرابط الطلب: {conv_url}")
                self.driver.get(conv_url)
                self.sleep(random.uniform(2.5, 3.8))
                clicked = True
            except Exception as e:
                self.log("WARNING", f"تعذر الانتقال لرابط الطلب: {e}")

        return clicked

    def _is_accept_or_composer_visible(self) -> bool:
        """Checks if either the Accept button or DM composer is visible on screen."""
        for xp in ACCEPT_BUTTON_XPATHS + COMPOSER_XPATHS:
            try:
                els = self.driver.find_elements(By.XPATH, xp)
                if els and els[0].is_displayed():
                    return True
            except Exception:
                pass
        return False

    def _click_accept_request(self, timeout: int = 5) -> bool:
        """Finds and clicks the Accept button for a message request, including confirmation sheets."""
        end_time = time.time() + timeout
        clicked = False

        while time.time() < end_time and not self.stop_requested:
            for xp in ACCEPT_BUTTON_XPATHS:
                try:
                    btns = self.driver.find_elements(By.XPATH, xp)
                    for btn in btns:
                        if btn.is_displayed() and btn.is_enabled():
                            btn_text = (btn.text or "").strip()
                            self.log("INFO", f"👆 النقر على زر قبول الطلب ({btn_text or 'Accept'})...")
                            self.js_click(btn)
                            clicked = True
                            self.sleep(random.uniform(1.0, 1.8))
                            break
                    if clicked:
                        break
                except Exception:
                    pass

            if clicked:
                self.sleep(0.6)
                for cxp in CONFIRMATION_ACCEPT_XPATHS:
                    try:
                        cbtns = self.driver.find_elements(By.XPATH, cxp)
                        for cbtn in cbtns:
                            if cbtn.is_displayed() and cbtn.is_enabled():
                                self.log("INFO", "👆 تأكيد قبول الطلب في النافذة المنبثقة...")
                                self.js_click(cbtn)
                                self.sleep(random.uniform(0.8, 1.4))
                                break
                    except Exception:
                        pass
                return True

            self.sleep(0.4)

        return False

    def _return_to_requests_list(self, request_url: str = REQUESTS_OTHER_URL) -> None:
        """Returns to the requests list page after sending reply so the loop can scroll & find the next."""
        try:
            is_scroller_visible = bool(self.driver.execute_script("""
                const scroller = document.querySelector('[data-testid="dm-message-requests-scroller"]') || 
                                 document.getElementById('x-chat-message-requests-Hidden');
                return scroller !== null && scroller.offsetHeight > 0;
            """))
            if is_scroller_visible:
                return
        except Exception:
            pass

        self.log("INFO", "🔙 العودة إلى قائمة طلبات المراسلة...")
        for bxp in BACK_BUTTON_XPATHS:
            try:
                bbtns = self.driver.find_elements(By.XPATH, bxp)
                if bbtns and bbtns[0].is_displayed():
                    self.js_click(bbtns[0])
                    self.sleep(random.uniform(1.5, 2.5))
                    return
            except Exception:
                pass

        try:
            self.driver.get(request_url)
            self.sleep(random.uniform(2.0, 3.0))
        except Exception:
            pass

    def _handle_single_request(self, item: Dict[str, Any], message: str, request_url: str) -> bool:
        """Opens user chat, clicks Accept, focuses composer, humanly types reply, sends, and gets back."""
        # 1. Click on user chat
        self._open_request_chat(item)

        # 2. Click Accept
        accepted = self._click_accept_request(timeout=6)
        if accepted:
            self.log("SUCCESS", "✅ تم قبول طلب المراسلة بنجاح!")
            self.sleep(random.uniform(1.0, 2.0))
        else:
            if not self._is_composer_visible():
                self.log("INFO", "لم يظهر زر قبول، فحص ظهور صندوق الرسائل مباشرة...")

        # 3. Rate-limit & restriction shield check
        is_restricted, rest_msg = self._check_x_rate_limit_or_restrictions()
        if is_restricted:
            self.log("ERROR", f"🛑 توقف معالجة الطلب بسبب قيود تويتر: {rest_msg}")
            self._return_to_requests_list(request_url)
            return False

        formatted_message = self._format_message(message, item)

        # 4. Bubble verification: Was the last message sent by us?
        if self.config.get("skip_if_last_outgoing", True):
            is_outgoing, last_txt = self._is_last_message_from_us(our_message_template=formatted_message)
            if is_outgoing:
                self.log("INFO", f"⏭️ تخطي طلب المراسلة ({item.get('text', '')[:30]}...): آخر رسالة صادرة منا بالفعل: \"{last_txt[:40]}...\"")
                self._return_to_requests_list(request_url)
                return False

        # 5. Find composer
        composer = self._find_composer(timeout=8)
        if not composer:
            self.log("WARNING", "❌ تعذر العثور على صندوق الرسائل (dm-composer-textarea) بعد قبول الطلب")
            self._return_to_requests_list(request_url)
            return False

        # 6. Type reply & Send with React event dispatching and verification
        sent = self._type_and_send_message(composer, formatted_message)

        # 7. Get back to requests list to continue scrolling & finding the next
        self._return_to_requests_list(request_url)

        return sent

    # ----------------------------------------------------------------------
    # PRIMARY INBOX SCANNING WITH DYNAMIC EXHAUSTIVE PAGINATION (https://x.com/i/chat)
    # ----------------------------------------------------------------------
    def _scan_and_reply_main_inbox_with_pagination(
        self,
        message: str,
        replied_text_by_id: Dict[str, str],
        reply_timestamps: List[float],
        max_replies_per_hour: int,
        history: Optional[Dict[str, float]] = None,
        cooldown_hours: float = 24.0
    ) -> int:
        """
        Scans https://x.com/i/chat for unread messages, replies to them (respecting per-user cooldown),
        and dynamically scrolls down (pagination) to load all users' messages across the inbox.
        Finally scrolls back to top.
        """
        replies_sent_in_pass = 0
        inbox_empty_scrolls = 0
        max_inbox_scrolls = 40  # Generous safety ceiling for massive inboxes
        seen_conv_ids = set()

        self.status = "فحص رسائل الصندوق الرئيسي والتمرير الشامل لكافة المحادثات..."
        scroll_idx = 0

        while scroll_idx < max_inbox_scrolls and not self.stop_requested:
            scroll_idx += 1
            now = time.time()
            reply_timestamps[:] = [t for t in reply_timestamps if now - t < 3600]

            conversations = self._extract_conversations()
            for c in conversations:
                cid = c.get("id") or c.get("convNumId")
                if cid:
                    seen_conv_ids.add(cid)

            unreads = [
                c for c in conversations 
                if c.get("unread") and (cooldown_hours <= 0 or replied_text_by_id.get(c.get("id")) != c.get("text"))
            ]

            if unreads:
                self.log("INFO", f"📬 تم اكتشاف {len(unreads)} محادثة غير مقروءة في الصندوق الرئيسي (الدفعة {scroll_idx})")
                for c in unreads:
                    if self.stop_requested:
                        break

                    if len(reply_timestamps) >= max_replies_per_hour:
                        self.log("WARNING", f"⚠️ تم الوصول للحد الأقصى للردود بالساعة ({max_replies_per_hour}). التوقف مؤقتاً...")
                        break

                    conv_id = c.get("id") or ""
                    conv_text = c.get("text") or ""
                    conv_url = c.get("url")

                    # Per-User Cooldown Check: only reply once per day / configured cooldown
                    if history is not None and cooldown_hours > 0:
                        is_cooling, remaining_sec = self._check_cooldown(c, history, cooldown_hours)
                        if is_cooling:
                            rem_h = remaining_sec / 3600.0
                            rem_m = remaining_sec / 60.0
                            time_str = f"{rem_h:.1f} ساعة" if rem_h >= 1.0 else f"{int(rem_m)} دقيقة"
                            self.log("INFO", f"⏳ تخطي المحادثة ({conv_text[:35]}...): تم الرد على هذا المستخدم مسبقاً اليوم. متبقي {time_str} على انتهاء فترة الانتظار ({cooldown_hours}س). لن يتم الرد مجدداً في نفس اليوم.")
                            replied_text_by_id[conv_id] = conv_text
                            continue

                    stamp = time.strftime("%H:%M:%S")
                    self.log("INFO", f"[{stamp}] 📩 فحص والرد على رسالة غير مقروءة من: {conv_text[:60]}")

                    success = self._send_dm_reply(conv_id, conv_url, message, item=c, history=history, cooldown_hours=cooldown_hours)
                    if success:
                        replied_text_by_id[conv_id] = conv_text
                        if history is not None and cooldown_hours > 0:
                            self._record_reply_history(c, history)
                        reply_timestamps.append(time.time())
                        self.stats["dms_sent"] += 1
                        self.stats["replies_sent"] += 1
                        replies_sent_in_pass += 1
                        cd_info = f"فترة الانتظار القادمة: {cooldown_hours} ساعة" if cooldown_hours > 0 else "بدون فترة انتظار (Cooldown: 0)"
                        self.log("SUCCESS", f"✓ [{stamp}] تم إرسال الرد بنجاح إلى: ({conv_text[:30]}...) [{cd_info}]")
                        self.sleep(random.uniform(3.0, 5.5))
                    else:
                        replied_text_by_id[conv_id] = conv_text
                        self.sleep(random.uniform(1.5, 2.5))

            # Scroll down to load more user messages (Pagination)
            self.status = f"تمرير الصندوق الرئيسي لتحميل كافة المحادثات ({scroll_idx}/{max_inbox_scrolls})..."
            self._scroll_main_inbox()
            self.sleep(random.uniform(2.0, 3.0))

            post_conversations = self._extract_conversations()
            post_new_ids = 0
            for c in post_conversations:
                cid = c.get("id") or c.get("convNumId")
                if cid and cid not in seen_conv_ids:
                    seen_conv_ids.add(cid)
                    post_new_ids += 1

            post_unreads = [
                c for c in post_conversations 
                if c.get("unread") and (cooldown_hours <= 0 or replied_text_by_id.get(c.get("id")) != c.get("text"))
            ]

            if post_new_ids == 0 and not post_unreads:
                inbox_empty_scrolls += 1
                if inbox_empty_scrolls >= 3:
                    self.log("INFO", f"✨ تم الانتهاء من فحص كافة محادثات الصندوق الرئيسي بالكامل ({len(seen_conv_ids)} محادثة مفحوصة).")
                    break
            else:
                inbox_empty_scrolls = 0

        # Scroll back to the top so newly arrived messages appear at the top
        self._scroll_main_inbox_to_top()
        self.sleep(random.uniform(1.2, 2.0))

        return replies_sent_in_pass

    def _scroll_main_inbox(self) -> None:
        """Scrolls down the primary DM inbox container."""
        try:
            self.driver.execute_script(SCROLL_MAIN_INBOX_JS)
            self.sleep(0.4)
        except Exception:
            pass

        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.PAGE_DOWN)
        except Exception:
            pass

    def _scroll_main_inbox_to_top(self) -> None:
        """Scrolls the primary DM inbox back to the top."""
        try:
            self.driver.execute_script(SCROLL_TOP_MAIN_INBOX_JS)
            self.sleep(0.4)
        except Exception:
            pass

        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.HOME)
        except Exception:
            pass

    def _wait_for_inbox(self, timeout: int = 15) -> bool:
        """Waits until DM conversation rows appear in DOM."""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: len(d.find_elements(By.XPATH, '//*[starts-with(@data-testid, "dm-conversation-item-")]')) > 0
            )
            return True
        except TimeoutException:
            return False

    def _is_inbox_present(self) -> bool:
        """Checks if the DM conversation items are present in DOM."""
        try:
            return bool(self.driver.execute_script(
                'return document.querySelector(\'[data-testid^="dm-conversation-item-"]\') !== null;'
            ))
        except Exception:
            rows = self.driver.find_elements(By.XPATH, '//*[starts-with(@data-testid, "dm-conversation-item-")]')
            return len(rows) > 0

    def _extract_conversations(self) -> List[Dict[str, Any]]:
        """Extracts conversation items with unread status and links via JS and XPath fallbacks."""
        try:
            res = self.driver.execute_script(EXTRACT_CONVERSATIONS_JS)
            if isinstance(res, list) and len(res) > 0:
                return res
        except Exception:
            pass

        conversations = []
        try:
            rows = self.driver.find_elements(By.XPATH, '//*[starts-with(@data-testid, "dm-conversation-item-")]')
            for row in rows:
                tid = row.get_attribute("data-testid") or ""
                desc = row.get_attribute("aria-description") or row.get_attribute("aria-label") or ""
                text = (row.text or "").replace("\n", " ")
                is_unread = (
                    "unread" in desc.lower() or
                    "unread" in text.lower() or
                    "غير مقروء" in desc.lower() or
                    "غير مقروء" in text.lower() or
                    len(row.find_elements(By.XPATH, './/*[@data-testid="unread-badge"]')) > 0 or
                    len(row.find_elements(By.XPATH, './/*[local-name()="svg" and @data-icon="icon-circle-fill"]')) > 0
                )
                href = None
                links = row.find_elements(By.XPATH, './/a[starts-with(@href, "/i/chat/")]')
                if links:
                    href = links[0].get_attribute("href")

                conv_num_id = ""
                if href:
                    m = re.search(r"/i/chat/([0-9a-zA-Z\-_]+)", href)
                    if m:
                        conv_num_id = m.group(1)

                handle = ""
                hm = re.search(r"@([a-zA-Z0-9_]{1,15})", text)
                if hm:
                    handle = "@" + hm.group(1).lower()

                conversations.append({
                    "id": tid or conv_num_id or href or text[:30],
                    "testId": tid,
                    "convNumId": conv_num_id,
                    "handle": handle,
                    "text": desc or text[:80],
                    "unread": is_unread,
                    "url": href
                })
        except Exception:
            pass

        return conversations

    def _is_composer_visible(self) -> bool:
        """Checks if the message composer is visible."""
        for xp in COMPOSER_XPATHS:
            try:
                els = self.driver.find_elements(By.XPATH, xp)
                if els and els[0].is_displayed():
                    return True
            except Exception:
                pass
        return False

    def _find_composer(self, timeout: int = 12):
        """Finds the DM composer element using multiple fallback XPaths."""
        end_time = time.time() + timeout
        while time.time() < end_time and not self.stop_requested:
            for xp in COMPOSER_XPATHS:
                try:
                    els = self.driver.find_elements(By.XPATH, xp)
                    if els and els[0].is_displayed():
                        return els[0]
                except Exception:
                    pass
            self.sleep(0.5)
        return None

    def _open_conversation(self, conv_id: str, conv_url: Optional[str], item: Optional[Dict[str, Any]] = None) -> bool:
        """
        Opens a conversation in the main chat inbox, either by clicking its row in DOM or navigating to conv_url.
        Ensures the active browser window is switched to the target conversation.
        """
        conv_num_id = ""
        handle = ""
        if item:
            conv_num_id = item.get("convNumId") or ""
            handle = item.get("handle") or ""
        if not conv_num_id and conv_url:
            m = re.search(r"/i/chat/([0-9a-zA-Z\-_]+)", conv_url)
            if m:
                conv_num_id = m.group(1)
        if not conv_num_id and conv_id and ("-" in conv_id or conv_id.isdigit()):
            conv_num_id = conv_id

        # 1. Check if browser is ALREADY on this exact conversation
        curr_url = self.driver.current_url or ""
        if conv_num_id and conv_num_id in curr_url and self._is_composer_visible():
            return True

        # 2. Try clicking the conversation row in the inbox list via JavaScript
        clicked = False
        try:
            clicked_info = self.driver.execute_script("""
                const convNumId = arguments[0];
                const handle = (arguments[1] || '').replace('@', '').toLowerCase();
                
                // 1. Match by href link
                if (convNumId) {
                    const link = document.querySelector(`a[href*="/i/chat/${convNumId}"]`) || 
                                 document.querySelector(`a[href*="${convNumId}"]`);
                    if (link) {
                        const row = link.closest('[data-testid="conversation"]') || link;
                        row.scrollIntoView({ block: 'nearest' });
                        row.click();
                        return { clicked: true, method: 'href' };
                    }
                }
                
                // 2. Match by handle text
                if (handle) {
                    const rows = document.querySelectorAll('[data-testid="conversation"]');
                    for (const r of rows) {
                        const txt = (r.innerText || '').toLowerCase();
                        if (txt.includes(handle)) {
                            r.scrollIntoView({ block: 'nearest' });
                            r.click();
                            return { clicked: true, method: 'handle' };
                        }
                    }
                }
                return { clicked: false };
            """, conv_num_id, handle)

            if isinstance(clicked_info, dict) and clicked_info.get("clicked"):
                self.log("INFO", f"👆 النقر على المحادثة ({handle or conv_num_id or conv_id}) في القائمة...")
                clicked = True
                # Wait for URL to update
                end_w = time.time() + 2.5
                while time.time() < end_w:
                    if conv_num_id and conv_num_id in (self.driver.current_url or ""):
                        break
                    self.sleep(0.3)
        except Exception as e:
            self.log("WARNING", f"خطأ أثناء النقر على المحادثة: {e}")

        # 3. If clicking didn't switch to this conversation, navigate directly to conv_url
        curr_url = self.driver.current_url or ""
        if (not conv_num_id or conv_num_id not in curr_url) and conv_url:
            try:
                self.log("INFO", f"🔗 الانتقال المباشر لرابط المحادثة: {conv_url}")
                self.driver.get(conv_url)
                self.sleep(random.uniform(2.5, 3.5))
            except Exception as e:
                self.log("WARNING", f"خطأ أثناء الانتقال للرابط: {e}")

        # 4. Verify we are indeed in the target conversation
        curr_url = self.driver.current_url or ""
        if conv_num_id and conv_num_id not in curr_url:
            self.log("WARNING", f"⚠️ تعذر فتح المحادثة المطلوبة ({conv_num_id}). الرابط الحالي: {curr_url}")
            return False

        # Wait for composer to appear
        composer = self._find_composer(timeout=8)
        return composer is not None

    def _send_dm_reply(
        self, 
        conv_id: str, 
        conv_url: Optional[str], 
        message: str,
        item: Optional[Dict[str, Any]] = None,
        history: Optional[Dict[str, float]] = None,
        cooldown_hours: float = 24.0
    ) -> bool:
        """Opens a conversation in main inbox, verifies bubbles, and sends a reply message."""
        conv_num_id = (item.get("convNumId") if item else "") or conv_id

        # 1. Open and ensure we are in the target conversation
        opened = self._open_conversation(conv_id, conv_url, item)
        if not opened:
            self.log("WARNING", f"❌ تعذر فتح نافذة المحادثة للمستخدم ({conv_id})")
            self._return_to_main_chat()
            return False

        # Format message template variables ({name}, {handle})
        formatted_message = self._format_message(message, item)

        # 2. Check rate limits or restrictions
        is_restricted, rest_msg = self._check_x_rate_limit_or_restrictions()
        if is_restricted:
            self.log("ERROR", f"🛑 توقف الإرسال بسبب قيود تويتر: {rest_msg}")
            self._return_to_main_chat()
            return False

        # 3. Bubble verification: Was the last message sent by us?
        if self.config.get("skip_if_last_outgoing", True):
            is_outgoing, last_txt = self._is_last_message_from_us(our_message_template=formatted_message)
            if is_outgoing:
                self.log("INFO", f"⏭️ تخطي المحادثة ({conv_id}): تم التحقق من فقاعات الشات وآخر رسالة صادرة منا بالفعل: \"{last_txt[:40]}...\"")
                if item and history is not None and cooldown_hours > 0:
                    self._record_reply_history(item, history)
                self._return_to_main_chat()
                return False  # Return False: No reply sent!

        composer = self._find_composer(timeout=8)
        if not composer:
            self.log("WARNING", "❌ لم يظهر صندوق كتابة الرسالة (dm-composer-textarea)")
            self._return_to_main_chat()
            return False

        sent = self._type_and_send_message(composer, formatted_message)

        self.sleep(random.uniform(1.2, 2.0))
        self._return_to_main_chat()

        return sent

    def _return_to_main_chat(self) -> None:
        """Returns back to https://x.com/i/chat after replying in any chatbox, deselecting active conversation."""
        curr_url = (self.driver.current_url or "").rstrip("/")
        target_url = MESSAGES_URL.rstrip("/")

        if curr_url == target_url:
            return

        self.log("INFO", f"🔙 العودة من صندوق المحادثة إلى: {MESSAGES_URL}")

        backed = False
        # 1. Try back button (mobile / narrow layout)
        for bxp in BACK_BUTTON_XPATHS:
            try:
                btns = self.driver.find_elements(By.XPATH, bxp)
                for btn in btns:
                    if btn.is_displayed() and btn.is_enabled():
                        self.js_click(btn)
                        self.sleep(random.uniform(0.8, 1.4))
                        if (self.driver.current_url or "").rstrip("/") == target_url:
                            backed = True
                            break
                if backed:
                    break
            except Exception:
                pass

        # 2. Try clicking Messages link in sidebar to reset URL in SPA without full reload
        if not backed:
            try:
                msg_links = self.driver.find_elements(By.XPATH, '//a[@data-testid="AppTabBar_DirectMessage_Link" or @href="/i/chat"]')
                for ml in msg_links:
                    if ml.is_displayed():
                        self.js_click(ml)
                        self.sleep(random.uniform(0.8, 1.4))
                        if (self.driver.current_url or "").rstrip("/") == target_url:
                            backed = True
                            break
            except Exception:
                pass

        # 3. Direct navigation to https://x.com/i/chat if still on conversation sub-URL
        if not backed and (self.driver.current_url or "").rstrip("/") != target_url:
            try:
                self.driver.get(MESSAGES_URL)
                self.sleep(random.uniform(1.8, 2.8))
            except Exception as e:
                self.log("WARNING", f"تعذر الانتقال إلى {MESSAGES_URL}: {e}")

        self._wait_for_inbox(timeout=10)

    def _jittered_sleep(self, base: float, spread_ratio: float = 0.35) -> None:
        """Sleep for `base` seconds +/- spread_ratio with stop_requested check."""
        spread = base * spread_ratio
        actual = max(1.0, base + random.uniform(-spread, spread))
        self.sleep(actual)
