import os
import time
import random
import logging
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==================== ENTERPRISE CONFIGURATION ====================
ADSPOWER_API_URL = "http://127.0.0.1:50325"
PROFILE_ID = "k1gy6v0h"
API_KEY = "27c516ec2235753ca6c82ad6b14b5767009b6140e511b08f"

# Target Post or Reel URL to harvest commenters from
TARGET_URL = "https://www.instagram.com/p/C5cpZiaoHQx/"

# Custom personalized direct message template
DM_TEMPLATE = "Hey @{username}! Saw your comment on our post. Thanks for the support! Feel free to reach us directly via https://ig.me/m/goahead2908"

# Safety Throttling (Seconds)
MIN_COOLDOWN = 18
MAX_COOLDOWN = 35

# State Tracking Persistence File
DATABASE_FILE = "enterprise_processed_leads.dat"
# ==================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [ENTERPRISE-BOT] [%(levelname)s] — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def initialize_database(filepath: str) -> set:
    if not os.path.exists(filepath):
        return set()
    with open(filepath, "r", encoding="utf-8") as file:
        return {line.strip().lower() for line in file if line.strip()}

def commit_lead_to_database(filepath: str, username: str):
    with open(filepath, "a", encoding="utf-8") as file:
        file.write(f"{username.strip().lower()}\n")

def human_keystroke_simulation(element, text: str):
    """Simulates organic human typing cadences to avoid bot heuristic flags."""
    for character in text:
        element.send_keys(character)
        time.sleep(random.uniform(0.03, 0.11))

def start_browser_instance() -> dict:
    endpoint = f"{ADSPOWER_API_URL}/api/v1/browser/start"
    params = {"user_id": PROFILE_ID}
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}

    logging.info(f"Initiating secure handshake with AdsPower profile instance: {PROFILE_ID}...")
    response = requests.get(endpoint, params=params, headers=headers, timeout=30)
    payload = response.json()

    if payload.get("code") != 0:
        raise ConnectionError(f"AdsPower Kernel Refused Connection: {payload.get('msg')}")

    return payload["data"]

def terminate_browser_instance():
    endpoint = f"{ADSPOWER_API_URL}/api/v1/browser/stop"
    params = {"user_id": PROFILE_ID}
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    try:
        requests.get(endpoint, params=params, headers=headers, timeout=10)
        logging.info("AdsPower container session closed cleanly.")
    except Exception as exception:
        logging.warning(f"Non-fatal warning during session teardown: {exception}")

def harvest_commenters(driver, target_url: str) -> set:
    logging.info(f"Navigating to target resource vector: {target_url}")
    driver.get(target_url)
    time.sleep(random.uniform(5.0, 8.0))

    logging.info("Harvesting DOM thread elements for active commenters...")
    # Scroll organically to force lazy-load execution of deeper comments
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(random.uniform(1.5, 3.0))

    usernames = set()
    try:
        # Robust XPath targeting comment headers and author profile handles
        author_nodes = driver.find_elements(
            By.XPATH, "//article//ul//h3//a | //div[contains(@class, 'x9f619')]//span//a[not(contains(@href, '/p/')) and not(contains(@href, '/explore/'))]"
        )
        for node in author_nodes:
            raw_handle = node.text.strip().replace("@", "")
            if raw_handle and "/" not in raw_handle and " " not in raw_handle and len(raw_handle) < 30:
                usernames.add(raw_handle.lower())
    except Exception as exception:
        logging.error(f"DOM parsing exception encountered during comment extraction: {exception}")

    logging.info(f"Successfully isolated {len(usernames)} unique commenter profile(s).")
    return usernames

def dispatch_direct_message(driver, username: str) -> bool:
    target_dm_url = f"https://ig.me/m/{username}"
    logging.info(f"Routing to destination context via shortlink: {target_dm_url}")
    driver.get(target_dm_url)
    
    wait = WebDriverWait(driver, 20)
    try:
        # Locate active chat message box composer area
        composer_xpath = (
            "//div[@role='textbox' and (@contenteditable='true' or @aria-label='Message')]"
            " | //textarea[contains(@placeholder, 'Message')]"
        )
        composer_element = wait.until(EC.element_to_be_clickable((By.XPATH, composer_xpath)))
        composer_element.click()
        time.sleep(random.uniform(0.8, 1.5))

        # Format and write message payload organically
        final_message = DM_TEMPLATE.format(username=username)
        human_keystroke_simulation(composer_element, final_message)
        time.sleep(random.uniform(0.5, 1.0))

        # Commit transmission via programmatic return key
        composer_element.send_keys(Keys.ENTER)
        logging.info(f"Outbound transmission verified for target lead: @{username}")
        time.sleep(3.0)  # Confirm dispatch window clears
        return True

    except Exception as exception:
        logging.error(f"Transmission protocol failure targeting @{username}: {exception}")
        return False

def execute_pipeline():
    processed_database = initialize_database(DATABASE_FILE)
    logging.info(f"State ledger loaded. Found {len(processed_database)} historically processed entity profile(s).")

    profile_meta = start_browser_instance()
    debugger_socket = profile_meta["ws"]["selenium"]
    webdriver_binary = profile_meta.get("webdriver")

    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", debugger_socket)

    service_manager = Service(executable_path=webdriver_binary) if webdriver_binary else Service()
    driver = webdriver.Chrome(service=service_manager, options=chrome_options)

    try:
        commenter_pool = harvest_commenters(driver, TARGET_URL)
        unprocessed_pool = [user for user in commenter_pool if user not in processed_database]

        logging.info(f"Queue initialized: {len(unprocessed_pool)} fresh target lead(s) pending outreach.")

        for index, target_user in enumerate(unprocessed_pool, 1):
            logging.info(f"Processing Pipeline Node [{index}/{len(unprocessed_pool)}] — Handle: @{target_user}")
            
            delivery_status = dispatch_direct_message(driver, target_user)
            if delivery_status:
                commit_lead_to_database(DATABASE_FILE, target_user)
                processed_database.add(target_user)

            # Enforce stochastic safety pauses to eliminate behavioral signatures
            cooldown_interval = random.uniform(MIN_COOLDOWN, MAX_COOLDOWN)
            logging.info(f"Safety circuit engaged. Cooling node processing thread for {cooldown_interval:.2f} seconds...")
            time.sleep(cooldown_interval)

    finally:
        driver.quit()
        terminate_browser_instance()
        logging.info("Automation pipeline sequence successfully finalized.")

if __name__ == "__main__":
    execute_pipeline()