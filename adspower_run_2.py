import json
import logging
import os
import random
import re
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ============================ CONFIGURATION ============================
API_KEY = "27c516ec2235753ca6c82ad6b14b5767009b6140e511b08f"
PROFILE_ID = "k1gy6v0h"
ADSPOWER_API_URL = "http://127.0.0.1:50325"

POST_URL = "https://www.facebook.com/content/insights/?content_id=UzpfSTYxNTc2NjIwMzY2MTIxOjEyMjE5OTU3NTQ1MDg4NzM0NToxMjIxOTk1NzU0NTA4ODczNDU%3D&entry_point=CometFeedStoryProfilePlusViewInsightsButton"
PAGE_NAME = "DheyaStore"  # Skip self-comments

# Templates (emojis supported)
PUBLIC_REPLY_TEMPLATE = "Hello {name}! Thanks for reaching out. Please check your inbox 📩"
PRIVATE_DM_TEMPLATE = "Hi {name}, thank you for your comment! How can we assist you with our store today?"

PROCESSED_LOG_FILE = "processed_comments.json"
CHECK_INTERVAL_SECONDS = 45  # Wait time before checking for new comments
# =======================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("FB_Auto_DM")


# -------------------------- PERSISTENCE & UTILS --------------------------
def load_processed_ids() -> set:
    if os.path.exists(PROCESSED_LOG_FILE):
        try:
            with open(PROCESSED_LOG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def record_processed_id(comment_id: str, id_set: set):
    id_set.add(comment_id)
    with open(PROCESSED_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(list(id_set), f, indent=2)


def type_letter_by_letter(driver, element, text: str):
    """
    Types text letter by letter with randomized human pauses.
    Uses insertText to support all Unicode characters and emojis without BMP errors.
    """
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.3)
    driver.execute_script("arguments[0].focus();", element)
    time.sleep(0.2)

    for char in text:
        driver.execute_script(
            """
            const el = arguments[0];
            const ch = arguments[1];
            el.focus();
            document.execCommand('insertText', false, ch);
            """,
            element,
            char
        )
        # Random typing delay between 40ms and 110ms per letter
        time.sleep(random.uniform(0.04, 0.11))

    time.sleep(0.5)


def js_click(driver, element):
    """Scrolls element into center and performs a direct DOM click."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
    time.sleep(0.4)
    driver.execute_script("arguments[0].click();", element)


def close_flyouts(driver):
    """Dismisses open Notification, Profile, or Menu popovers."""
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.4)
    except Exception:
        pass


# -------------------------- ADSPOWER API --------------------------
def start_adspower_browser():
    url = f"{ADSPOWER_API_URL}/api/v1/browser/start"
    params = {"user_id": PROFILE_ID}
    headers = {"Authorization": f"Bearer {API_KEY}"}

    logger.info(f"Starting AdsPower browser for profile: {PROFILE_ID}...")
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            selenium_port = data["data"]["ws"]["selenium"]
            chromedriver_path = data["data"]["webdriver"]
            logger.info(f"[+] AdsPower running on port {selenium_port}")
            return selenium_port, chromedriver_path
        else:
            logger.error(f"[!] AdsPower API returned error: {data.get('msg')}")
            return None, None
    except requests.exceptions.RequestException as e:
        logger.error(f"[!] Unable to connect to AdsPower API: {e}")
        return None, None


def stop_adspower_browser():
    url = f"{ADSPOWER_API_URL}/api/v1/browser/stop"
    params = {"user_id": PROFILE_ID}
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        requests.get(url, params=params, headers=headers, timeout=5)
        logger.info("[*] AdsPower browser shut down cleanly.")
    except Exception:
        pass


# -------------------------- DOM PARSERS --------------------------
def extract_author_name(comment) -> str:
    """Extracts author name using comment aria-label or fallback anchor tags."""
    aria = comment.get_attribute("aria-label") or ""
    if aria.startswith("Comment by "):
        name_part = aria[len("Comment by "):]
        clean_name = re.split(
            r"\s+\d+\s*(?:second|minute|hour|day|week|month|year|m|h|d|w|s)s?\s*ago|\s+\d+[smhdwy]|\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|\s+just now",
            name_part,
            flags=re.IGNORECASE
        )[0].strip()
        if clean_name:
            return clean_name

    links = comment.find_elements(By.XPATH, './/a[@role="link"]')
    for a in links:
        if a.get_attribute("aria-hidden") == "true" or a.get_attribute("tabindex") == "-1":
            continue
        txt = (a.get_attribute("textContent") or "").strip()
        if txt and not any(skip in txt.lower() for skip in ["reply", "share", "like", "see response", "send message", "hide", "report"]):
            return txt

    return "Friend"


def extract_comment_id(comment_element) -> str:
    """Extracts unique comment_id from permalink URLs in the comment DOM."""
    try:
        links = comment_element.find_elements(By.XPATH, './/a[contains(@href, "comment_id=")]')
        for link in links:
            href = link.get_attribute("href")
            match = re.search(r"comment_id=([0-9a-zA-Z_=%-]+)", href)
            if match:
                return match.group(1)
    except Exception:
        pass
    return ""


def find_send_message_button(comment):
    btns = comment.find_elements(By.XPATH, './/div[@role="button"]')
    for b in btns:
        txt = (b.get_attribute("textContent") or "").strip()
        if txt.lower() == "send message":
            return b
    return None


def find_reply_button(comment):
    btns = comment.find_elements(By.XPATH, './/div[@role="button"] | .//li//div[@role="button"]')
    for b in btns:
        txt = (b.get_attribute("textContent") or "").strip()
        if txt.lower() == "reply":
            return b
    return None


def is_already_responded(comment) -> bool:
    links = comment.find_elements(By.XPATH, './/a')
    for l in links:
        txt = (l.get_attribute("textContent") or "").strip()
        if "see response" in txt.lower():
            return True
    return False


# -------------------------- PAGE ACTIONS --------------------------
def switch_to_all_comments(driver):
    """Switches the comment filter from 'Most relevant' to 'All comments'."""
    try:
        filter_btn = driver.find_elements(
            By.XPATH,
            '//div[@role="button" and (contains(., "Most relevant") or contains(., "All comments"))]'
        )
        if filter_btn:
            js_click(driver, filter_btn[0])
            time.sleep(1.5)

            all_comments_opt = driver.find_elements(
                By.XPATH,
                '//div[@role="menuitem" or @role="option" or @role="button"]//span[contains(., "All comments")]'
            )
            if all_comments_opt:
                js_click(driver, all_comments_opt[0])
                logger.info("[+] Switched comment filter to 'All comments'.")
                time.sleep(3)
    except Exception as e:
        logger.warning(f"Could not change comment filter: {e}")


def expand_all_comments(driver):
    """Scrolls down and clicks buttons that expand hidden/collapsed comments."""
    for _ in range(2):
        driver.execute_script("window.scrollBy(0, 600);")
        time.sleep(1)
        more_btns = driver.find_elements(
            By.XPATH,
            '//span[contains(., "View more comments") or contains(., "previous comments") or contains(., "View all") or contains(., "more comment")]'
        )
        for mb in more_btns:
            try:
                js_click(driver, mb)
                time.sleep(1.2)
            except Exception:
                pass


def post_public_reply(driver, comment_elem, author_name: str) -> bool:
    """Types reply letter-by-letter and submits."""
    try:
        reply_btn = find_reply_button(comment_elem)
        if not reply_btn:
            return False

        js_click(driver, reply_btn)
        time.sleep(1.5)

        active = driver.switch_to.active_element
        if active and active.get_attribute("role") == "textbox":
            reply_box = active
        else:
            reply_box = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        '//div[@role="textbox" and @contenteditable="true" and not(contains(@aria-label, "Comment as"))]'
                    )
                )
            )

        message = PUBLIC_REPLY_TEMPLATE.format(name=author_name)
        logger.info(f"Typing public reply letter-by-letter to {author_name}...")
        type_letter_by_letter(driver, reply_box, message)

        # Submit public reply via Enter + DOM events
        reply_box.send_keys(Keys.ENTER)
        driver.execute_script(
            """
            const el = arguments[0];
            el.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13}));
            el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13}));
            """,
            reply_box
        )

        logger.info(f"[✓] Public reply posted for {author_name}")
        time.sleep(3)
        return True
    except Exception as e:
        logger.warning(f"[!] Could not post public reply for {author_name}: {e}")
        return False


def dispatch_private_dm(driver, author_name: str) -> bool:
    """Types private message letter-by-letter and triggers send."""
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    '//div[@role="dialog" and not(@aria-label="Notifications") and not(contains(@aria-label, "Menu"))] '
                    '| //div[contains(@class, "chat")] | //div[@role="textbox" and (@aria-label="Message" or @aria-label="Aa")]'
                )
            )
        )
        time.sleep(1)

        dm_boxes = driver.find_elements(
            By.XPATH,
            '//div[@role="dialog" and not(@aria-label="Notifications")]//div[@role="textbox" and @contenteditable="true"]'
        )

        if not dm_boxes:
            dm_boxes = driver.find_elements(
                By.XPATH,
                '//div[@role="textbox" and (@aria-label="Message" or @aria-label="Aa" or @data-lexical-editor="true") and not(contains(@aria-label, "Comment as"))]'
            )

        if not dm_boxes:
            logger.error(f"[!] Could not find DM textbox for {author_name}")
            return False

        active_box = dm_boxes[-1]
        dm_text = PRIVATE_DM_TEMPLATE.format(name=author_name)
        logger.info(f"Typing DM letter-by-letter to {author_name}...")
        type_letter_by_letter(driver, active_box, dm_text)

        # 1. Native Enter
        active_box.send_keys(Keys.ENTER)
        time.sleep(0.3)

        # 2. JavaScript Enter event
        driver.execute_script(
            """
            const el = arguments[0];
            el.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13}));
            el.dispatchEvent(new KeyboardEvent('keypress', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13}));
            el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13}));
            """,
            active_box
        )
        time.sleep(0.5)

        # 3. Look for explicit Send buttons / icons and click
        send_btns = driver.find_elements(
            By.XPATH,
            '//div[@aria-label="Press Enter to send" or @aria-label="Press enter to send" or @aria-label="Send" or @aria-label="Send message" or @aria-label="Send a message"] '
            '| //div[@role="button" and (normalize-space()="Send" or @aria-label="Send")]'
        )
        for sb in send_btns:
            try:
                js_click(driver, sb)
                break
            except Exception:
                pass

        logger.info(f"[✓] Private DM sent successfully to {author_name}")
        time.sleep(2)

        # Close chat dock
        close_btns = driver.find_elements(
            By.XPATH,
            '//div[@aria-label="Close chat" or @aria-label="Close" or @aria-label="close"]'
        )
        for cb in close_btns:
            try:
                js_click(driver, cb)
                break
            except Exception:
                pass

        return True
    except Exception as e:
        logger.error(f"[!] Failed to complete DM dispatch for {author_name}: {e}")
        return False


# -------------------------- DAEMON MONITORING ENGINE --------------------------
def run_continuous_monitor(driver):
    """Runs an ongoing loop listening for new incoming comments and sending DMs."""
    processed_ids = load_processed_ids()
    logger.info(f"Loaded {len(processed_ids)} already-processed comments from storage.")

    logger.info(f"Opening target post: {POST_URL}")
    driver.get(POST_URL)
    time.sleep(6)

    close_flyouts(driver)
    switch_to_all_comments(driver)
    expand_all_comments(driver)

    total_processed = 0

    try:
        while True:
            comments = driver.find_elements(By.XPATH, '//div[@role="article"]')
            logger.info(f"Scanning {len(comments)} visible comments on page...")

            action_taken_in_pass = False

            for idx, comment in enumerate(comments, start=1):
                try:
                    author_name = extract_author_name(comment)

                    # Skip Page comments
                    if not author_name or PAGE_NAME.lower() in author_name.lower():
                        continue

                    # Unique ID verification
                    c_id = extract_comment_id(comment)
                    if not c_id:
                        c_id = f"{author_name}_{comment.location.get('y', 0)}"

                    if c_id in processed_ids:
                        continue

                    # Skip if already replied to
                    if is_already_responded(comment):
                        record_processed_id(c_id, processed_ids)
                        continue

                    send_msg_btn = find_send_message_button(comment)
                    if not send_msg_btn:
                        continue

                    logger.info(f"[*] Processing new comment from: {author_name} (ID: {c_id})")
                    action_taken_in_pass = True

                    # Step 1: Public Reply
                    post_public_reply(driver, comment, author_name)

                    # Step 2: Open DM Dialog
                    close_flyouts(driver)
                    send_msg_btn = find_send_message_button(comment)
                    if send_msg_btn:
                        logger.info(f"Opening DM prompt for {author_name}...")
                        js_click(driver, send_msg_btn)
                        time.sleep(2)

                        # Step 3: Dispatch Private DM
                        success = dispatch_private_dm(driver, author_name)
                        if success:
                            record_processed_id(c_id, processed_ids)
                            total_processed += 1

                    cooldown = random.uniform(15, 25)
                    logger.info(f"Cooling down for {cooldown:.1f}s...\n")
                    time.sleep(cooldown)

                    # Break to re-evaluate fresh DOM after interaction
                    break

                except Exception as e:
                    logger.debug(f"Row skip error: {e}")
                    continue

            # If no comments processed on this pass, wait and refresh for new incoming comments
            if not action_taken_in_pass:
                logger.info(f"[*] No new comments. Waiting {CHECK_INTERVAL_SECONDS}s for new messages (Press Ctrl+C to stop)...")
                time.sleep(CHECK_INTERVAL_SECONDS)

                logger.info("[*] Checking for newly posted comments...")
                driver.refresh()
                time.sleep(6)
                close_flyouts(driver)
                switch_to_all_comments(driver)
                expand_all_comments(driver)

    except KeyboardInterrupt:
        logger.info(f"Monitor stopped by user. Total processed this session: {total_processed}")


# -------------------------- ENTRYPOINT --------------------------
if __name__ == "__main__":
    port, chromedriver = start_adspower_browser()

    if port and chromedriver:
        opts = Options()
        opts.debugger_address = port

        svc = Service(chromedriver)
        driver = webdriver.Chrome(service=svc, options=opts)

        try:
            run_continuous_monitor(driver)
        finally:
            time.sleep(2)
            stop_adspower_browser()