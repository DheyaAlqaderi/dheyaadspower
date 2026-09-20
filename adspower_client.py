import os
import io
import json
import time
import tarfile
import logging
import threading
import requests
import shutil
import base64
import glob
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional

logger = logging.getLogger("AdsPowerClient")

LOCAL_CACHE_DIR = os.path.expanduser("~/.config/adspower_global/cwd_global/source/cache")
PROFILES_METADATA_FILE = "profiles_metadata.json"


class AdsPowerClient:
    def __init__(self, api_url: str = "http://127.0.0.1:50325", api_key: str = ""):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self._launch_lock = threading.Lock()
        self._last_launch_time = 0.0

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def check_connection(self) -> Dict[str, Any]:
        """Checks if AdsPower Local API is reachable."""
        try:
            resp = requests.get(f"{self.api_url}/status", headers=self._get_headers(), timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0 or "msg" in data:
                    return {
                        "connected": True,
                        "message": "متصل بنجاح مع تطبيق AdsPower",
                        "status_code": resp.status_code,
                        "data": data
                    }
        except Exception:
            pass

        return {
            "connected": False,
            "message": "تعذر الاتصال بـ AdsPower API. تأكد من فتح البرنامج وتفعيل الـ API من الإعدادات.",
            "error": "Connection Refused"
        }

    def _load_profiles_metadata(self) -> Dict[str, Any]:
        if os.path.exists(PROFILES_METADATA_FILE):
            try:
                with open(PROFILES_METADATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "k1gxxu4i": {"name": "حساب فيسبوك الرئيسي", "group_name": "Facebook", "domain_name": "facebook.com"},
            "k1gxxf7x": {"name": "بروفايل AdsPower 2", "group_name": "عام", "domain_name": ""},
            "k1gxw3m1": {"name": "بروفايل AdsPower 3", "group_name": "عام", "domain_name": ""},
            "k1gpsln4": {"name": "بروفايل AdsPower 4", "group_name": "عام", "domain_name": ""}
        }

    def _save_profiles_metadata(self, metadata: Dict[str, Any]):
        try:
            with open(PROFILES_METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving profiles metadata: {e}")

    def _discover_local_profiles(self) -> List[str]:
        """Discovers profile IDs directly from local AdsPower storage."""
        discovered = set()
        discovered.add("k1gxxu4i")

        if os.path.exists(LOCAL_CACHE_DIR):
            try:
                for entry in os.listdir(LOCAL_CACHE_DIR):
                    if "_" in entry:
                        p_id = entry.split("_")[0]
                        if len(p_id) >= 6:
                            discovered.add(p_id)
            except Exception as e:
                logger.warning(f"Error scanning local AdsPower cache: {e}")

        return sorted(list(discovered))

    def get_profiles(self, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
        """Fetches browser profiles from AdsPower API or local cache fallback."""
        url = f"{self.api_url}/api/v1/user/list"
        params = {"page": page, "page_size": page_size}

        # 1. Try official AdsPower API endpoint
        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=8)
            data = resp.json()

            # Handle rate-limit retry if AdsPower throttles
            if data.get("code") != 0 and ("too many" in str(data.get("msg", "")).lower() or data.get("code") == -1):
                logger.info("AdsPower user/list rate limit hit, waiting 1.2s to retry...")
                time.sleep(1.2)
                resp = requests.get(url, params=params, headers=self._get_headers(), timeout=8)
                data = resp.json()

            if data.get("code") == 0:
                raw_list = data.get("data", {}).get("list", [])
                
                # Check active status concurrently across profiles (takes ~10-20ms)
                p_ids = [item.get("user_id") for item in raw_list if item.get("user_id")]
                active_map = {}
                with ThreadPoolExecutor(max_workers=min(max(len(p_ids), 1), 8)) as ex:
                    active_results = list(ex.map(self.is_browser_active, p_ids))
                    for pid, is_act in zip(p_ids, active_results):
                        active_map[pid] = is_act

                metadata = self._load_profiles_metadata()
                profiles = []
                for item in raw_list:
                    proxy_cfg = item.get("user_proxy_config", {}) or {}
                    p_id = item.get("user_id")
                    meta_item = metadata.get(p_id, {})
                    name = item.get("name")
                    if not name or not name.strip():
                        sn = item.get("serial_number", "")
                        name = f"بروفايل {sn}" if sn else f"Profile_{p_id}"

                    profiles.append({
                        "user_id": p_id,
                        "name": name,
                        "group_name": item.get("group_name") or "الافتراضية",
                        "serial_number": item.get("serial_number", ""),
                        "username": item.get("username", ""),
                        "domain_name": item.get("domain_name", ""),
                        "country": item.get("ip_country") or item.get("country", ""),
                        "remark": item.get("remark", ""),
                        "proxy_soft": proxy_cfg.get("proxy_soft", "no_proxy"),
                        "proxy_type": proxy_cfg.get("proxy_type", ""),
                        "proxy_host": proxy_cfg.get("proxy_host", ""),
                        "proxy_port": proxy_cfg.get("proxy_port", ""),
                        "proxy_user": proxy_cfg.get("proxy_user", ""),
                        "proxy_password": proxy_cfg.get("proxy_password", ""),
                        "latest_ip": proxy_cfg.get("latest_ip", ""),
                        "is_active": active_map.get(p_id, False),
                        "created_time": item.get("created_time", ""),
                        "platforms": meta_item.get("platforms", {})
                    })
                return {
                    "success": True,
                    "profiles": profiles,
                    "total": data.get("data", {}).get("total", len(profiles)),
                    "source": "api"
                }
            else:
                logger.warning(f"AdsPower user/list API returned non-zero code: {data}")
        except Exception as e:
            logger.warning(f"AdsPower get_profiles error: {e}")

        # 2. Local Discovery Fallback (for Free Subscriptions)
        metadata = self._load_profiles_metadata()
        local_ids = self._discover_local_profiles()

        for p_id in local_ids:
            if p_id not in metadata:
                metadata[p_id] = {
                    "name": f"ملف AdsPower ({p_id})",
                    "group_name": "الافتراضية",
                    "domain_name": ""
                }
        self._save_profiles_metadata(metadata)

        profiles = []
        for p_id, meta in metadata.items():
            is_active = self.is_browser_active(p_id)
            profiles.append({
                "user_id": p_id,
                "name": meta.get("name") or f"Profile_{p_id}",
                "group_name": meta.get("group_name") or "الافتراضية",
                "serial_number": p_id,
                "username": meta.get("username", ""),
                "domain_name": meta.get("domain_name", ""),
                "country": "",
                "remark": meta.get("remark", ""),
                "proxy_soft": meta.get("proxy_soft", "no_proxy"),
                "proxy_type": meta.get("proxy_type", ""),
                "proxy_host": meta.get("proxy_host", ""),
                "proxy_port": meta.get("proxy_port", ""),
                "proxy_user": meta.get("proxy_user", ""),
                "is_active": is_active,
                "created_time": "",
                "platforms": meta.get("platforms", {})
            })

        return {
            "success": True,
            "profiles": profiles,
            "total": len(profiles),
            "source": "local_storage"
        }

    def fetch_all_adspower_proxies(self) -> List[Dict[str, Any]]:
        """
        Extracts all proxies saved inside AdsPower:
        1. Queries user profiles to build serial number and ID mapping.
        2. Queries the AdsPower proxy-list endpoint (/api/v2/proxy-list/list).
        3. Matches and resolves profile assignments with credential-level uniqueness.
        """
        proxies_found = []
        seen = set()

        # Step 1: Query profiles to map serial numbers to user_ids & profile names
        prof_res = self.get_profiles(page=1, page_size=200)
        profiles = prof_res.get("profiles", [])
        
        sn_to_profile = {}
        id_to_profile = {}
        for p in profiles:
            sn = str(p.get("serial_number") or "").strip()
            uid = p.get("user_id")
            if sn:
                sn_to_profile[sn] = p
            if uid:
                id_to_profile[uid] = p

        time.sleep(1.0)  # Respect AdsPower local API rate limits

        # Step 2: Query /api/v2/proxy-list/list
        try:
            resp = requests.post(
                f"{self.api_url}/api/v2/proxy-list/list",
                json={"page": 1, "page_size": 100},
                headers=self._get_headers(),
                timeout=8
            )
            data = resp.json()
            if data.get("code") == 0:
                p_list = data.get("data", {}).get("list", [])
                for item in p_list:
                    host = (item.get("host") or item.get("proxy_host") or "").strip()
                    port = str(item.get("port") or item.get("proxy_port") or "").strip()
                    user = (item.get("user") or item.get("proxy_user") or "").strip()
                    password = (item.get("password") or item.get("proxy_password") or "").strip()
                    if not host or not port:
                        continue

                    key = f"{host.lower()}:{port}:{user}"
                    if key not in seen:
                        seen.add(key)
                        assigned_id = None
                        assigned_name = None
                        related_sns = item.get("related_profile_no") or []
                        if related_sns:
                            first_sn = str(related_sns[0]).strip()
                            if first_sn in sn_to_profile:
                                matched_p = sn_to_profile[first_sn]
                                assigned_id = matched_p.get("user_id")
                                assigned_name = matched_p.get("name")

                        proxies_found.append({
                            "host": host,
                            "port": port,
                            "type": (item.get("type") or item.get("proxy_type") or "http").lower(),
                            "user": user,
                            "password": password,
                            "source": "قائمة بروكسي AdsPower",
                            "assigned_to": assigned_id,
                            "assigned_profile_name": assigned_name
                        })
        except Exception as e:
            logger.warning(f"Error fetching proxy-list from AdsPower: {e}")

        # Step 3: Extract and match proxies directly configured on profiles
        for p in profiles:
            host = (p.get("proxy_host") or "").strip()
            port = str(p.get("proxy_port") or "").strip()
            user = (p.get("proxy_user") or "").strip()
            password = (p.get("proxy_password") or "").strip()
            soft = p.get("proxy_soft")

            if host and port and soft != "no_proxy":
                key = f"{host.lower()}:{port}:{user}"
                if key not in seen:
                    seen.add(key)
                    proxies_found.append({
                        "host": host,
                        "port": port,
                        "type": (p.get("proxy_type") or "http").lower(),
                        "user": user,
                        "password": password,
                        "source": f"ملف: {p.get('name')}",
                        "assigned_to": p.get("user_id"),
                        "assigned_profile_name": p.get("name"),
                        "last_ip": p.get("latest_ip")
                    })
                else:
                    # Update existing proxy assignment and password if missing
                    for existing_item in proxies_found:
                        existing_key = f"{existing_item['host'].lower()}:{existing_item['port']}:{existing_item.get('user', '').strip()}"
                        if existing_key == key:
                            if not existing_item.get("assigned_to"):
                                existing_item["assigned_to"] = p.get("user_id")
                                existing_item["assigned_profile_name"] = p.get("name")
                            if not existing_item.get("password") and password:
                                existing_item["password"] = password
                            if p.get("latest_ip"):
                                existing_item["last_ip"] = p.get("latest_ip")

        return proxies_found

    def add_custom_profile(self, user_id: str, name: str, group_name: str = "عام") -> Dict[str, Any]:
        """Allows adding a profile ID manually."""
        user_id = user_id.strip()
        if not user_id:
            return {"success": False, "message": "معرف الملف غير صالح"}

        metadata = self._load_profiles_metadata()
        metadata[user_id] = {
            "name": name.strip() or f"Profile_{user_id}",
            "group_name": group_name.strip() or "عام",
            "domain_name": ""
        }
        self._save_profiles_metadata(metadata)
        return {"success": True, "message": f"تمت إضافة الملف {user_id} بنجاح"}

    def start_browser(self, user_id: str) -> Dict[str, Any]:
        """
        Starts browser profile in AdsPower with thread-safe rate-limit staggering
        and automatic exponential backoff retry.
        """
        url = f"{self.api_url}/api/v1/browser/start"
        params = {"user_id": user_id, "open_tabs": "1"}

        with self._launch_lock:
            # Enforce minimum 1.8 seconds between successive browser launches
            elapsed = time.time() - self._last_launch_time
            if elapsed < 1.8:
                time.sleep(1.8 - elapsed)

            max_retries = 3
            last_err = ""

            for attempt in range(max_retries):
                try:
                    self._last_launch_time = time.time()
                    resp = requests.get(url, params=params, headers=self._get_headers(), timeout=35)
                    data = resp.json()

                    if data.get("code") == 0:
                        ws_data = data.get("data", {}).get("ws", {})
                        selenium_port = ws_data.get("selenium")
                        chromedriver_path = data.get("data", {}).get("webdriver")
                        return {
                            "success": True,
                            "selenium_port": selenium_port,
                            "chromedriver_path": chromedriver_path,
                            "message": f"تم تشغيل المتصفح للملف {user_id} بنجاح"
                        }

                    msg = data.get("msg", "فشل تشغيل المتصفح")
                    last_err = msg

                    # Rate limit handling: if AdsPower asks to wait, back off and retry
                    if "too many request" in msg.lower() or "rate" in msg.lower():
                        logger.warning(f"AdsPower rate limit hit on {user_id}: {msg}. Retrying in {(attempt + 1) * 2}s...")
                        time.sleep((attempt + 1) * 2.0)
                        continue

                    return {
                        "success": False,
                        "message": msg
                    }
                except Exception as e:
                    last_err = str(e)
                    logger.warning(f"Error starting browser {user_id} (attempt {attempt + 1}): {e}")
                    time.sleep(1.5)

            return {
                "success": False,
                "message": f"فشل تشغيل المتصفح: {last_err}"
            }

    def stop_browser(self, user_id: str) -> Dict[str, Any]:
        """Stops browser profile in AdsPower."""
        url = f"{self.api_url}/api/v1/browser/stop"
        params = {"user_id": user_id}
        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=12)
            data = resp.json()
            if data.get("code") == 0:
                return {"success": True, "message": f"تم إغلاق المتصفح للملف {user_id}"}
            else:
                return {"success": False, "message": data.get("msg", "فشل إغلاق المتصفح")}
        except Exception as e:
            return {"success": False, "message": f"خطأ اتصال: {str(e)}"}

    def is_browser_active(self, user_id: str) -> bool:
        """Checks if browser is active."""
        url = f"{self.api_url}/api/v1/browser/active"
        params = {"user_id": user_id}
        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=2.5)
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("status") == "Active"
            return False
        except Exception:
            return False

    # ----------------- Bulk Operations -----------------
    def bulk_start_browsers(self, user_ids: List[str]) -> Dict[str, Any]:
        """
        Starts multiple browser profiles sequentially with orderly staggering.
        Avoids AdsPower Local API throttling and returns granular per-profile status.
        """
        results = {}
        for uid in user_ids:
            try:
                res = self.start_browser(uid)
                results[uid] = res
            except Exception as e:
                results[uid] = {"success": False, "message": str(e)}

        success_count = sum(1 for r in results.values() if r.get("success"))
        failed_count = len(user_ids) - success_count

        msg = f"تم تشغيل {success_count} من أصل {len(user_ids)} متصفح بنجاح"
        if failed_count > 0:
            first_fail = next((r.get("message") for r in results.values() if not r.get("success")), "")
            msg += f" (فشل {failed_count}: {first_fail})"

        return {
            "success": success_count > 0,
            "total": len(user_ids),
            "started_count": success_count,
            "failed_count": failed_count,
            "results": results,
            "message": msg
        }

    def bulk_stop_browsers(self, user_ids: List[str]) -> Dict[str, Any]:
        """Stops multiple browser profiles with smooth sequential execution."""
        results = {}
        for uid in user_ids:
            try:
                res = self.stop_browser(uid)
                results[uid] = res
                time.sleep(0.3)
            except Exception as e:
                results[uid] = {"success": False, "message": str(e)}

        success_count = sum(1 for r in results.values() if r.get("success"))
        return {
            "success": True,
            "total": len(user_ids),
            "stopped_count": success_count,
            "results": results,
            "message": f"تم إغلاق {success_count} متصفح بنجاح"
        }

    def update_profile_proxy(self, user_id: str, proxy: Dict[str, Any]) -> Dict[str, Any]:
        """Updates profile proxy in AdsPower and local metadata."""
        url = f"{self.api_url}/api/v1/user/update"
        proxy_config = {
            "proxy_soft": proxy.get("proxy_soft", "other"),
            "proxy_type": (proxy.get("type") or proxy.get("proxy_type") or "http").lower(),
            "proxy_host": proxy.get("host") or proxy.get("proxy_host", ""),
            "proxy_port": str(proxy.get("port") or proxy.get("proxy_port", "")),
            "proxy_user": proxy.get("user") or proxy.get("proxy_user", ""),
            "proxy_password": proxy.get("password") or proxy.get("proxy_password", "")
        }

        metadata = self._load_profiles_metadata()
        if user_id in metadata:
            metadata[user_id].update(proxy_config)
            self._save_profiles_metadata(metadata)

        payload = {
            "user_id": user_id,
            "user_proxy_config": proxy_config
        }

        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(), timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                return {"success": True, "message": f"تم تعيين البروكسي للملف {user_id} في AdsPower بنجاح"}
            else:
                return {"success": True, "message": f"تم ربط البروكسي بالملف {user_id} محلياً في لوحة التحكم"}
        except Exception:
            return {"success": True, "message": f"تم ربط البروكسي بالملف {user_id} محلياً"}

    def bulk_assign_proxy(self, user_ids: List[str], proxy: Dict[str, Any]) -> Dict[str, Any]:
        """Assigns proxy to multiple profiles at once."""
        count = 0
        for uid in user_ids:
            res = self.update_profile_proxy(uid, proxy)
            if res.get("success"):
                count += 1
        return {
            "success": count > 0,
            "assigned_count": count,
            "total": len(user_ids),
            "message": f"تم تعيين البروكسي لـ {count} من أصل {len(user_ids)} ملف"
        }

    def remove_profile_proxy(self, user_id: str) -> Dict[str, Any]:
        """Removes proxy from profile."""
        metadata = self._load_profiles_metadata()
        if user_id in metadata:
            metadata[user_id]["proxy_soft"] = "no_proxy"
            metadata[user_id]["proxy_host"] = ""
            metadata[user_id]["proxy_port"] = ""
            self._save_profiles_metadata(metadata)

        url = f"{self.api_url}/api/v1/user/update"
        payload = {
            "user_id": user_id,
            "user_proxy_config": {"proxy_soft": "no_proxy"}
        }
        try:
            requests.post(url, json=payload, headers=self._get_headers(), timeout=5)
        except Exception:
            pass

        return {"success": True, "message": f"تمت إزالة البروكسي من الملف {user_id} بنجاح"}

    def bulk_unlink_proxies(self, user_ids: List[str]) -> Dict[str, Any]:
        """Removes proxies from multiple profiles."""
        count = 0
        for uid in user_ids:
            try:
                self.remove_profile_proxy(uid)
                count += 1
            except Exception as e:
                logger.error(f"Error unlinking proxy from {uid}: {e}")
        return {"success": True, "message": f"تم فك ارتباط البروكسي عن {count} ملف بنجاح", "count": count}

    def bulk_change_group(self, user_ids: List[str], group_name: str) -> Dict[str, Any]:
        """Changes group name for multiple profiles."""
        group_name = group_name.strip() or "الافتراضية"
        metadata = self._load_profiles_metadata()
        count = 0
        for uid in user_ids:
            if uid in metadata:
                metadata[uid]["group_name"] = group_name
            else:
                metadata[uid] = {"name": f"Profile_{uid}", "group_name": group_name}

            try:
                requests.post(
                    f"{self.api_url}/api/v1/user/update",
                    json={"user_id": uid, "group_name": group_name},
                    headers=self._get_headers(),
                    timeout=5
                )
            except Exception:
                pass
            count += 1
        self._save_profiles_metadata(metadata)
        return {"success": True, "message": f"تم نقل {count} ملف إلى المجموعة '{group_name}' بنجاح", "count": count}

    # ----------------- Profile Session & Cookie Management -----------------
    def _find_cache_dir(self, user_id: str) -> Optional[str]:
        """Finds the local cache directory for a given AdsPower profile ID."""
        if not os.path.exists(LOCAL_CACHE_DIR):
            return None
        try:
            for entry in os.listdir(LOCAL_CACHE_DIR):
                if entry.startswith(f"{user_id}_"):
                    full_path = os.path.join(LOCAL_CACHE_DIR, entry)
                    if os.path.isdir(full_path):
                        return full_path
        except Exception as e:
            logger.warning(f"Error scanning cache dir for {user_id}: {e}")
        return None

    def _backup_file_b64(self, path: str) -> Optional[str]:
        """Reads a single file and returns its content as a base64 string. Returns None if not found."""
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Error backing up file {path}: {e}")
            return None

    def _backup_dir_b64(self, path: str) -> Optional[str]:
        """
        Tar-gzips a directory entirely in memory and returns the archive as a base64 string.
        Returns None if the directory does not exist or is empty.
        """
        if not path or not os.path.isdir(path):
            return None
        try:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.add(path, arcname=os.path.basename(path))
            buf.seek(0)
            data = buf.read()
            if not data:
                return None
            return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.warning(f"Error backing up directory {path}: {e}")
            return None

    def _restore_file_b64(self, b64_data: str, dest_path: str) -> bool:
        """Writes a base64-encoded file back to disk. Returns True on success."""
        if not b64_data:
            return False
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(base64.b64decode(b64_data))
            return True
        except Exception as e:
            logger.warning(f"Error restoring file to {dest_path}: {e}")
            return False

    def _restore_dir_b64(self, b64_data: str, parent_dir: str) -> bool:
        """
        Extracts a base64-encoded tar.gz archive back into parent_dir.
        The archive's top-level folder name is preserved as a subfolder of parent_dir.
        Returns True on success.
        """
        if not b64_data or not parent_dir:
            return False
        try:
            os.makedirs(parent_dir, exist_ok=True)
            raw = base64.b64decode(b64_data)
            buf = io.BytesIO(raw)
            with tarfile.open(fileobj=buf, mode="r:gz") as tar:
                try:
                    tar.extractall(path=parent_dir, filter="data")
                except TypeError:
                    tar.extractall(path=parent_dir)
            return True
        except Exception as e:
            logger.warning(f"Error restoring directory to {parent_dir}: {e}")
            return False

    def _get_active_cache_suffix(self) -> str:
        """Detects the active profile cache suffix from recent directories (e.g. i7edal or i7dl06)."""
        fallback_suffix = "i7edal"
        if not os.path.exists(LOCAL_CACHE_DIR):
            return fallback_suffix
        try:
            dirs = [d for d in os.listdir(LOCAL_CACHE_DIR) if os.path.isdir(os.path.join(LOCAL_CACHE_DIR, d)) and "_" in d]
            if dirs:
                dirs.sort(key=lambda d: os.path.getmtime(os.path.join(LOCAL_CACHE_DIR, d)), reverse=True)
                for d in dirs:
                    parts = d.split("_", 1)
                    if len(parts) == 2 and parts[1].strip():
                        return parts[1].strip()
        except Exception as e:
            logger.warning(f"Error detecting active cache suffix: {e}")
        return fallback_suffix

    def _restore_profile_cache_data(self, cdir: str, package_data: Dict[str, Any]) -> tuple:
        """
        Restores full profile cache data into cdir (Default/ and profile root):
        - Raw fingerprint files (WebGL, Canvas/Audio noise hashes, settings.dat)
        - Passwords (Login Data, Login Data For Account, journals)
        - History (History, History-journal, Top Sites, Favicons, Shortcuts)
        - Bookmarks (Bookmarks, Bookmarks.bak, Ordering)
        - Cookies (Cookies SQLite, Safe Browsing Cookies, sf_cookie.txt)
        - Web Data & Autofill (Web Data, Account Web Data, journals)
        - HTML5 Local Storage (Local Storage/ leveldb)
        - IndexedDB & WebStorage (IndexedDB/, WebStorage/)
        - Sessions & Session Storage (Session Storage/, Sessions/, sf_tabs.txt)
        - Extensions (Local Extension Settings/, Extension State/, Rules/, Scripts/, extensions_crx_cache)
        - Network & Security (Network Persistent State, TransportSecurity, Affiliation Database)
        - Preferences & Local State master encryption keys
        Returns (restored_count, skipped_count).
        """
        if not cdir or not package_data:
            return (0, 0)

        restored = 0
        skipped = 0

        try:
            os.makedirs(cdir, exist_ok=True)
            def_dir = os.path.join(cdir, "Default")
            os.makedirs(def_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create target cache directories: {e}")
            return (0, 0)

        raw_files = package_data.get("raw_fingerprint_files", {})
        chrome_data = package_data.get("chrome_data", {})

        # 1. Restore raw hardware fingerprint & core config files
        try:
            # Clean old WebGL files from all OS platforms (prevents Android / Windows contamination)
            for pat in ["*_MacOS*", "*_Windows*", "*_Linux*", "*_Android*", "*_IOS*"]:
                for old_wg in glob.glob(os.path.join(cdir, pat)):
                    try: os.remove(old_wg)
                    except Exception: pass

            pkg_os = package_data.get("os") or package_data.get("fingerprint", {}).get("os", "macOS")
            ua_str = package_data.get("user_agent") or package_data.get("fingerprint_config", {}).get("ua", "")
            if not pkg_os or pkg_os == "macOS":
                if "windows" in ua_str.lower():
                    pkg_os = "Windows"
                elif "linux" in ua_str.lower():
                    pkg_os = "Linux"
                else:
                    pkg_os = "macOS"

            is_mac = "mac" in str(pkg_os).lower()
            is_win = "win" in str(pkg_os).lower()
            is_linux = "linux" in str(pkg_os).lower()

            macos_restored = False
            for fname, b64_content in raw_files.items():
                # Filter out mismatched OS WebGL files
                if is_mac and any(x in fname for x in ["_Android", "_Windows", "_Linux", "_IOS"]):
                    continue
                if is_win and any(x in fname for x in ["_Android", "_MacOS", "_Linux", "_IOS"]):
                    continue
                if is_linux and any(x in fname for x in ["_Android", "_MacOS", "_Windows", "_IOS"]):
                    continue

                if "_MacOS" in fname:
                    macos_restored = True

                try:
                    raw_bytes = base64.b64decode(b64_content)
                    if fname in ["Preferences", "Secure Preferences"]:
                        out_path = os.path.join(def_dir, fname)
                    else:
                        out_path = os.path.join(cdir, fname)
                    with open(out_path, "wb") as f_out:
                        f_out.write(raw_bytes)
                    restored += 1
                except Exception as e:
                    logger.warning(f"Error restoring raw fingerprint file {fname}: {e}")
                    skipped += 1

            # If target is macOS and no MacOS WebGL file was restored, generate valid ANGLE Metal MacOS WebGL file
            if is_mac and not macos_restored and not glob.glob(os.path.join(cdir, "*_MacOS*")):
                wg_path = os.path.join(cdir, "c2ce9fe7b41d2cf6eecf2ec05353b6f3_MacOS")
                wg_data = {
                    "UNMASKED_VENDOR_WEBGL": "Google Inc. (Intel Inc.)",
                    "UNMASKED_RENDERER_WEBGL": "ANGLE (Intel, ANGLE Metal Renderer: Intel(R) Iris(TM) Plus Graphics OpenGL Engine, Unspecified Version)",
                    "GPUAdapterInfo": {"vendor": "intel", "architecture": "gen-9"},
                    "SUPPORTED_EXTENSIONS": []
                }
                try:
                    with open(wg_path, "w", encoding="utf-8") as f_out:
                        json.dump(wg_data, f_out)
                    restored += 1
                except Exception as e:
                    logger.warning(f"Failed to generate fallback macOS WebGL definition: {e}")
        except Exception as e:
            logger.warning(f"Error restoring raw fingerprint files: {e}")

        # 2. Restore individual binary and SQLite files in Default/ and profile root
        if chrome_data:
            _single_files = {
                # Saved passwords
                "login_data":                     os.path.join(def_dir, "Login Data"),
                "login_data_journal":             os.path.join(def_dir, "Login Data-journal"),
                "login_data_for_account":         os.path.join(def_dir, "Login Data For Account"),
                "login_data_for_account_journal": os.path.join(def_dir, "Login Data For Account-journal"),
                # Browsing history & visited pages
                "history":                        os.path.join(def_dir, "History"),
                "history_journal":                os.path.join(def_dir, "History-journal"),
                "top_sites":                      os.path.join(def_dir, "Top Sites"),
                "favicons":                       os.path.join(def_dir, "Favicons"),
                "shortcuts":                      os.path.join(def_dir, "Shortcuts"),
                # Bookmarks
                "bookmarks_raw":                  os.path.join(def_dir, "Bookmarks"),
                "bookmarks_bak":                  os.path.join(def_dir, "Bookmarks.bak"),
                "bookmark_ordering":              os.path.join(def_dir, "BookmarkMergedSurfaceOrdering"),
                # Autofill & Web Data
                "web_data":                       os.path.join(def_dir, "Web Data"),
                "web_data_journal":               os.path.join(def_dir, "Web Data-journal"),
                "account_web_data":               os.path.join(def_dir, "Account Web Data"),
                # Cookies & Session files
                "cookies_raw_file":               os.path.join(def_dir, "Cookies"),
                "cookies_journal":                os.path.join(def_dir, "Cookies-journal"),
                "safe_browsing_cookies":          os.path.join(def_dir, "Safe Browsing Cookies"),
                "sf_cookie":                      os.path.join(cdir, "sf_cookie.txt"),
                "sf_tabs":                        os.path.join(cdir, "sf_tabs.txt"),
                "cookie_updated_time":            os.path.join(cdir, "cookie_updated_time"),
                # Network & Security
                "network_persistent_state":       os.path.join(def_dir, "Network Persistent State"),
                "transport_security":             os.path.join(def_dir, "TransportSecurity"),
                "affiliation_database":           os.path.join(def_dir, "Affiliation Database"),
                # Encryption keys & AdsPower profile settings
                "local_state":                    os.path.join(cdir, "Local State"),
                "settings_dat":                   os.path.join(cdir, "settings.dat"),
            }

            for key, dest_path in _single_files.items():
                b64val = chrome_data.get(key)
                if b64val:
                    if self._restore_file_b64(b64val, dest_path):
                        restored += 1
                    else:
                        skipped += 1

            # 3. Restore directory archives (tar.gz) into parent directories
            _dir_archives = {
                "local_storage":         def_dir,  # restores to Default/Local Storage/
                "session_storage":       def_dir,  # restores to Default/Session Storage/
                "sessions_dir":          def_dir,  # restores to Default/Sessions/
                "indexeddb":             def_dir,  # restores to Default/IndexedDB/
                "web_storage":           def_dir,  # restores to Default/WebStorage/
                "local_ext_settings":    def_dir,  # restores to Default/Local Extension Settings/
                "extension_state":       def_dir,  # restores to Default/Extension State/
                "extension_rules":       def_dir,  # restores to Default/Extension Rules/
                "extension_scripts":     def_dir,  # restores to Default/Extension Scripts/
                "extensions_crx_cache":  cdir,     # restores to <cdir>/extensions_crx_cache/
            }

            for key, parent in _dir_archives.items():
                b64val = chrome_data.get(key)
                if b64val:
                    if self._restore_dir_b64(b64val, parent):
                        restored += 1
                    else:
                        skipped += 1

            # 4. Extensions metadata JSON file if provided separately
            ext_meta = chrome_data.get("extensions_metadata")
            if ext_meta and not os.path.exists(os.path.join(cdir, "extensions_crx_cache", "metadata.json")):
                try:
                    ext_meta_dir = os.path.join(cdir, "extensions_crx_cache")
                    os.makedirs(ext_meta_dir, exist_ok=True)
                    with open(os.path.join(ext_meta_dir, "metadata.json"), "w", encoding="utf-8") as _f:
                        json.dump(ext_meta, _f, ensure_ascii=False, indent=2)
                    restored += 1
                except Exception as e:
                    logger.warning(f"Error restoring extensions_metadata: {e}")

        # 5. Screen resolution & Window placement restoration in Preferences
        screen_data = package_data.get("screen") or package_data.get("fingerprint", {}).get("screen")
        if not screen_data and "screen_resolution" in package_data.get("fingerprint_config", {}):
            s_res = package_data["fingerprint_config"]["screen_resolution"]
            if "_" in str(s_res):
                parts = str(s_res).split("_")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    screen_data = {"width": int(parts[0]), "height": int(parts[1])}

        if screen_data and isinstance(screen_data, dict):
            pref_file = os.path.join(def_dir, "Preferences")
            if os.path.isfile(pref_file):
                try:
                    with open(pref_file, "r", encoding="utf-8", errors="ignore") as _f:
                        pref_obj = json.load(_f)
                    if isinstance(pref_obj, dict):
                        if "browser" not in pref_obj or not isinstance(pref_obj["browser"], dict):
                            pref_obj["browser"] = {}
                        if "window_placement" not in pref_obj["browser"] or not isinstance(pref_obj["browser"]["window_placement"], dict):
                            pref_obj["browser"]["window_placement"] = {}
                        w = screen_data.get("width", 1920)
                        h = screen_data.get("height", 1080)
                        pref_obj["browser"]["window_placement"]["work_area_right"] = w
                        pref_obj["browser"]["window_placement"]["work_area_bottom"] = h
                        pref_obj["browser"]["window_placement"]["right"] = w
                        pref_obj["browser"]["window_placement"]["bottom"] = h
                        with open(pref_file, "w", encoding="utf-8") as _f:
                            json.dump(pref_obj, _f)
                        restored += 1
                except Exception as e:
                    logger.warning(f"Error restoring window_placement screen resolution: {e}")

        logger.info(f"Restored profile cache at {cdir}: {restored} items restored, {skipped} skipped")
        return (restored, skipped)



    def get_profile_cookies(self, user_id: str) -> Dict[str, Any]:
        """
        Extracts decrypted session cookies for a profile:
        1. Queries AdsPower Local API GET /api/v2/browser-profile/cookies?profile_id={user_id}
        2. Fallback: Reads sf_cookie.txt from local profile cache
        """
        user_id = str(user_id).strip()
        # 1. Official AdsPower API
        url = f"{self.api_url}/api/v2/browser-profile/cookies"
        params = {"profile_id": user_id}
        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=8)
            data = resp.json()
            if data.get("code") == 0:
                c_data = data.get("data", {}).get("cookies")
                if isinstance(c_data, str) and c_data.strip():
                    try:
                        cookies_list = json.loads(c_data)
                        if isinstance(cookies_list, list):
                            return {
                                "success": True,
                                "cookies": cookies_list,
                                "cookies_raw": c_data,
                                "count": len(cookies_list),
                                "source": "api"
                            }
                    except Exception:
                        pass
                elif isinstance(c_data, list):
                    return {
                        "success": True,
                        "cookies": c_data,
                        "cookies_raw": json.dumps(c_data),
                        "count": len(c_data),
                        "source": "api"
                    }
        except Exception as e:
            logger.warning(f"Error fetching cookies via API for {user_id}: {e}")

        # 2. Local cache fallback
        cdir = self._find_cache_dir(user_id)
        if cdir:
            sf_path = os.path.join(cdir, "sf_cookie.txt")
            if os.path.exists(sf_path):
                try:
                    with open(sf_path, "r", encoding="utf-8") as f:
                        cookies_list = json.load(f)
                        if isinstance(cookies_list, list) and len(cookies_list) > 0:
                            return {
                                "success": True,
                                "cookies": cookies_list,
                                "cookies_raw": json.dumps(cookies_list),
                                "count": len(cookies_list),
                                "source": "local_cache"
                            }
                except Exception as e:
                    logger.warning(f"Error reading sf_cookie.txt for {user_id}: {e}")

        return {
            "success": False,
            "cookies": [],
            "cookies_raw": "[]",
            "count": 0,
            "message": "لم يتم العثور على كوكيز محفوظة لهذا الملف"
        }

    def _get_default_fonts(self, os_type: str) -> List[str]:
        """Loads AdsPower default font list for the given OS (darwin/win32/linux)."""
        config_path = os.path.expanduser("~/.config/adspower_global/config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    snapshot_raw = cdata.get("AI_AGENT_STORE_SNAPSHOT")
                    if snapshot_raw:
                        snap = json.loads(snapshot_raw)
                        flist = snap.get("state", {}).get("config", {}).get("defaultFontList", {})
                        key = "darwin" if os_type.lower() in ["mac", "macos", "darwin"] else ("win32" if os_type.lower() in ["win", "windows"] else "linux")
                        if key in flist and isinstance(flist[key], list) and flist[key]:
                            return list(flist[key])
            except Exception as e:
                logger.warning(f"Error loading fonts from AdsPower config: {e}")

        fallback_fonts = {
            "macos": [
                "Al Bayan", "American Typewriter", "Andale Mono", "Apple Color Emoji", "Apple SD Gothic Neo",
                "Arial", "Arial Black", "Arial Hebrew", "Arial Narrow", "Arial Rounded MT Bold",
                "Avenir", "Avenir Next", "Baskerville", "Chalkboard", "Comic Sans MS", "Copperplate",
                "Courier", "Courier New", "Didot", "Futura", "Geneva", "Georgia", "Gill Sans",
                "Heiti SC", "Helvetica", "Helvetica Neue", "Hiragino Sans GB", "Impact", "Lucida Grande",
                "Menlo", "Monaco", "Noteworthy", "Optima", "Palatino", "Papyrus", "PingFang SC",
                "Segoe UI", "Tahoma", "Times", "Times New Roman", "Trebuchet MS", "Verdana", "Zapfino"
            ],
            "windows": [
                "Arial", "Arial Black", "Bahnschrift", "Calibri", "Cambria", "Candara", "Comic Sans MS",
                "Consolas", "Constantia", "Corbel", "Courier New", "Ebrima", "Franklin Gothic", "Gabriola",
                "Georgia", "Impact", "Lucida Console", "Lucida Sans Unicode", "Malgun Gothic", "Marlett",
                "Microsoft Himalaya", "Microsoft JhengHei", "Microsoft Sans Serif", "Microsoft YaHei",
                "Palatino Linotype", "Segoe Print", "Segoe Script", "Segoe UI", "Segoe UI Emoji",
                "Segoe UI Symbol", "SimSun", "Sylfaen", "Tahoma", "Times New Roman", "Trebuchet MS",
                "Verdana", "Webdings", "Yu Gothic"
            ],
            "linux": [
                "Arial", "Courier 10 Pitch", "Courier New", "DejaVu Sans", "DejaVu Sans Mono",
                "DejaVu Serif", "FreeMono", "FreeSans", "FreeSerif", "Georgia", "Liberation Mono",
                "Liberation Sans", "Liberation Serif", "Nimbus Roman", "Nimbus Sans", "Noto Color Emoji",
                "Noto Sans", "Noto Serif", "Times New Roman", "Ubuntu", "Ubuntu Mono", "Verdana"
            ]
        }
        k = "macos" if os_type.lower() in ["mac", "macos", "darwin"] else ("windows" if os_type.lower() in ["win", "windows"] else "linux")
        return fallback_fonts.get(k, fallback_fonts["macos"])

    def _get_profile_user_agent(self, user_id: str, os_type: str = "macOS") -> str:
        """
        Retrieves User-Agent for profile:
        1. Official AdsPower Local API POST /api/v2/browser-profile/ua
        2. Inspect active SunBrowser / Chrome process command-line flags
        3. Realistic modern Chrome UA fallback based on OS
        """
        os_clean = os_type.lower()
        is_target_mac = any(x in os_clean for x in ["mac", "macos", "darwin"])
        is_target_win = "win" in os_clean
        is_target_lin = "linux" in os_clean and not "android" in os_clean

        try:
            resp = requests.post(
                f"{self.api_url}/api/v2/browser-profile/ua",
                json={"profile_id": [user_id]},
                headers=self._get_headers(),
                timeout=2
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    ua_val = data.get("data", {}).get(user_id)
                    if isinstance(ua_val, str) and ua_val.strip():
                        val = ua_val.strip()
                        # Strict validation: never let an Android UA pollute a macOS profile
                        if is_target_mac and "macintosh" in val.lower():
                            return val
                        elif is_target_win and "windows" in val.lower():
                            return val
                        elif is_target_lin and "linux" in val.lower() and "android" not in val.lower():
                            return val
        except Exception:
            pass

        try:
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    cmd_path = os.path.join("/proc", pid, "cmdline")
                    if os.path.exists(cmd_path):
                        with open(cmd_path, "rb") as f:
                            cmd = f.read().replace(b"\0", b" ").decode("utf-8", errors="ignore")
                            if user_id in cmd and ("sunbrowser" in cmd.lower() or "chrome" in cmd.lower()):
                                m = re.search(r"--user-agent=([^\s]+)", cmd)
                                if m:
                                    val = m.group(1).strip()
                                    if is_target_mac and "macintosh" in val.lower():
                                        return val
                                    elif is_target_win and "windows" in val.lower():
                                        return val
                                    elif is_target_lin and "linux" in val.lower() and "android" not in val.lower():
                                        return val
        except Exception:
            pass

        if is_target_win:
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        elif is_target_lin:
            return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"

    def _get_profile_screen(self, cdir: Optional[str]) -> Dict[str, Any]:
        """
        Extracts screen resolution for profile from Default/Preferences window_placement.
        Returns dict with width, height, and resolution string ('1920_1200').
        """
        if cdir and os.path.exists(cdir):
            pref_path = os.path.join(cdir, "Default", "Preferences")
            if os.path.isfile(pref_path):
                try:
                    with open(pref_path, "r", encoding="utf-8", errors="ignore") as f:
                        pref = json.load(f)
                        wp = pref.get("browser", {}).get("window_placement", {})
                        w = wp.get("work_area_right") or wp.get("right")
                        h = wp.get("work_area_bottom") or wp.get("bottom")
                        if w and h and int(w) > 0 and int(h) > 0:
                            return {
                                "width": int(w),
                                "height": int(h),
                                "resolution": f"{int(w)}_{int(h)}"
                            }
                except Exception:
                    pass
        return {"width": 1920, "height": 1080, "resolution": "1920_1080"}

    def _get_profile_hardware(self, user_id: str, cdir: Optional[str], webgl_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts CPU cores, Device Memory, and GPU info for profile:
        - Checks running process flags (--protected-hardwareconcurrency, --protected-devicememory)
        - Combines with WebGL vendor and renderer
        """
        cores = 8
        mem_gb = 8

        try:
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    cmd_path = os.path.join("/proc", pid, "cmdline")
                    if os.path.exists(cmd_path):
                        with open(cmd_path, "rb") as f:
                            cmd = f.read().replace(b"\0", b" ").decode("utf-8", errors="ignore")
                            if user_id in cmd and ("sunbrowser" in cmd.lower() or "chrome" in cmd.lower()):
                                c_m = re.search(r"--protected-hardwareconcurrency=(\d+)", cmd)
                                if c_m: cores = int(c_m.group(1))
                                m_m = re.search(r"--protected-devicememory=(\d+)", cmd)
                                if m_m: mem_gb = int(m_m.group(1))
                                break
        except Exception:
            pass

        return {
            "cpu_cores": cores,
            "device_memory_gb": mem_gb,
            "gpu_vendor": webgl_info.get("unmasked_vendor", "Google Inc. (Intel Inc.)"),
            "gpu_renderer": webgl_info.get("unmasked_renderer", "ANGLE (Intel, ANGLE Metal Renderer: Intel(R) Iris(TM) Plus Graphics OpenGL Engine, Unspecified Version)"),
            "gpu_adapter": webgl_info.get("gpu_adapter", {"vendor": "intel", "architecture": "gen-9"})
        }

    def get_profile_fingerprint(self, user_id: str) -> Dict[str, Any]:
        """
        Extracts the full hardware and browser fingerprint for a profile:
        - OS & Platform (macOS, Windows, Linux)
        - WebGL Vendor, Renderer, and GPU Hardware
        - Audio & Canvas noise flags
        - Timezone, Language, and Browser Preferences
        - Raw binary / encrypted fingerprint definition files (for exact cloning)
        - Pre-built fingerprint_config dict for AdsPower API calls
        """
        user_id = str(user_id).strip()
        cdir = self._find_cache_dir(user_id)

        fp = {
            "success": False,
            "os": "macOS",
            "languages": ["en-US"],
            "webgl": {
                "unmasked_vendor": "Google Inc. (Intel Inc.)",
                "unmasked_renderer": "ANGLE (Intel, ANGLE Metal Renderer: Intel(R) Iris(TM) Plus Graphics OpenGL Engine, Unspecified Version)",
                "gpu_adapter": {"vendor": "intel", "architecture": "gen-9"}
            },
            "noise": {
                "canvas": "1",
                "audio": "1",
                "webgl_image": "1",
                "client_rects": "1"
            },
            "raw_files": {},
            "fingerprint_config": {}
        }

        if cdir and os.path.exists(cdir):
            fp["success"] = True
            # 1. Search WebGL / GPU file (*_MacOS, *_Windows, *_Linux, *_Android, *_IOS)
            mac_files = glob.glob(os.path.join(cdir, "*_MacOS*"))
            win_files = glob.glob(os.path.join(cdir, "*_Windows*"))
            lin_files = glob.glob(os.path.join(cdir, "*_Linux*"))
            and_files = glob.glob(os.path.join(cdir, "*_Android*"))
            ios_files = glob.glob(os.path.join(cdir, "*_IOS*"))

            if mac_files:
                fp["os"] = "macOS"
                chosen_webgl = mac_files
            elif win_files:
                fp["os"] = "Windows"
                chosen_webgl = win_files
            elif lin_files:
                fp["os"] = "Linux"
                chosen_webgl = lin_files
            elif and_files:
                fp["os"] = "Android"
                chosen_webgl = and_files
            elif ios_files:
                fp["os"] = "iOS"
                chosen_webgl = ios_files
            else:
                chosen_webgl = []

            for wf in chosen_webgl:
                bn = os.path.basename(wf)
                try:
                    with open(wf, "r", encoding="utf-8", errors="ignore") as f:
                        wg_json = json.load(f)
                        if isinstance(wg_json, dict):
                            if "UNMASKED_VENDOR_WEBGL" in wg_json:
                                fp["webgl"]["unmasked_vendor"] = wg_json["UNMASKED_VENDOR_WEBGL"]
                            if "UNMASKED_RENDERER_WEBGL" in wg_json:
                                fp["webgl"]["unmasked_renderer"] = wg_json["UNMASKED_RENDERER_WEBGL"]
                            if "GPUAdapterInfo" in wg_json:
                                fp["webgl"]["gpu_adapter"] = wg_json["GPUAdapterInfo"]
                except Exception:
                    pass

                try:
                    with open(wf, "rb") as f:
                        fp["raw_files"][bn] = base64.b64encode(f.read()).decode("utf-8")
                except Exception:
                    pass

            # 2. Extract 32-char hex noise hash files
            try:
                for entry in os.listdir(cdir):
                    full = os.path.join(cdir, entry)
                    if os.path.isfile(full) and len(entry) == 32 and all(c in "0123456789abcdef" for c in entry.lower()):
                        with open(full, "rb") as f:
                            fp["raw_files"][entry] = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                logger.warning(f"Error reading noise hash files for {user_id}: {e}")

            # 3. settings.dat
            s_path = os.path.join(cdir, "settings.dat")
            if os.path.exists(s_path):
                try:
                    with open(s_path, "rb") as f:
                        fp["raw_files"]["settings.dat"] = base64.b64encode(f.read()).decode("utf-8")
                except Exception:
                    pass

            # 4. Local State
            ls_path = os.path.join(cdir, "Local State")
            if os.path.exists(ls_path):
                try:
                    with open(ls_path, "rb") as f:
                        fp["raw_files"]["Local State"] = base64.b64encode(f.read()).decode("utf-8")
                except Exception:
                    pass

            # 5. Default/Preferences
            pref_path = os.path.join(cdir, "Default", "Preferences")
            if os.path.exists(pref_path):
                try:
                    with open(pref_path, "r", encoding="utf-8", errors="ignore") as f:
                        pref_data = json.load(f)
                        langs = pref_data.get("intl", {}).get("selected_languages", "")
                        if langs:
                            fp["languages"] = [l.strip() for l in langs.split(",") if l.strip()]
                    with open(pref_path, "rb") as f:
                        fp["raw_files"]["Preferences"] = base64.b64encode(f.read()).decode("utf-8")
                except Exception:
                    pass

            # 6. Default/Secure Preferences
            sec_path = os.path.join(cdir, "Default", "Secure Preferences")
            if os.path.exists(sec_path):
                try:
                    with open(sec_path, "rb") as f:
                        fp["raw_files"]["Secure Preferences"] = base64.b64encode(f.read()).decode("utf-8")
                except Exception:
                    pass

        # 7. Hardware, Screen, User-Agent, and Fonts Extraction
        os_type = fp.get("os", "macOS")
        if os_type.lower() in ["mac", "macos", "darwin", "mac os x"]:
            canonical_os = "macOS"
            ua_system_versions = ["Mac OS X"]
        elif os_type.lower() in ["win", "windows"]:
            canonical_os = "Windows"
            ua_system_versions = ["Windows 10", "Windows 11"]
        elif os_type.lower() in ["linux"]:
            canonical_os = "Linux"
            ua_system_versions = ["Linux"]
        else:
            canonical_os = "macOS"
            ua_system_versions = ["Mac OS X"]

        fp["os"] = canonical_os
        screen_data = self._get_profile_screen(cdir)
        user_agent = self._get_profile_user_agent(user_id, canonical_os)
        hardware_data = self._get_profile_hardware(user_id, cdir, fp["webgl"])
        fonts_list = self._get_default_fonts(canonical_os)

        fp["user_agent"] = user_agent
        fp["screen"] = screen_data
        fp["hardware"] = hardware_data
        fp["fonts"] = fonts_list
        fp["fonts_count"] = len(fonts_list)

        # Pre-build AdsPower API fingerprint_config dict with mandatory OS & Kernel preservation
        fp["fingerprint_config"] = {
            "browser_kernel_config": {
                "version": "151",
                "type": "chrome"
            },
            "random_ua": {
                "ua_browser": ["chrome"],
                "ua_version": ["151"],
                "ua_system_version": ua_system_versions
            },
            "canvas": "1",
            "webgl_image": "1",
            "audio": "1",
            "client_rects": "1",
            "webgl": "2",
            "webgl_config": {
                "unmasked_vendor": fp["webgl"].get("unmasked_vendor", "Google Inc. (Intel Inc.)"),
                "unmasked_renderer": fp["webgl"].get("unmasked_renderer", "ANGLE (Intel, ANGLE Metal Renderer: Intel(R) Iris(TM) Plus Graphics OpenGL Engine, Unspecified Version)"),
                "webgpu": {"webgpu_switch": "1"}
            },
            "ua": user_agent,
            "screen_resolution": screen_data.get("resolution", "1920_1200"),
            "hardware_concurrency": str(hardware_data.get("cpu_cores", 8)),
            "device_memory": str(hardware_data.get("device_memory_gb", 8)),
            "fonts": fonts_list,
            "automatic_timezone": "1",
            "language_switch": "0" if fp.get("languages") else "1",
            "language": fp.get("languages", ["en-US"]),
            "scan_port_type": "1"
        }

        # Build human readable summary
        webgl_disp = fp["webgl"].get("unmasked_renderer", "")
        if "Intel" in webgl_disp:
            gpu_disp = "Intel Iris Graphics"
        elif "NVIDIA" in webgl_disp:
            gpu_disp = "NVIDIA GeForce"
        elif "AMD" in webgl_disp or "Radeon" in webgl_disp:
            gpu_disp = "AMD Radeon"
        elif "Apple" in webgl_disp:
            gpu_disp = "Apple M-Series GPU"
        else:
            gpu_disp = webgl_disp[:25] if webgl_disp else "Hardware GPU"

        res_disp = screen_data.get("resolution", "1920_1080").replace("_", "x")
        hw_disp = f"{hardware_data.get('cpu_cores', 8)} Cores / {hardware_data.get('device_memory_gb', 8)}GB RAM"
        fp["summary"] = f"{os_type} • {res_disp} • {hw_disp} • {gpu_disp} • {len(fonts_list)} Fonts"

        # ── Full Chrome profile data backup ──────────────────────────────────
        chrome_data: Dict[str, Any] = {}
        if cdir and os.path.exists(cdir):
            def_dir = os.path.join(cdir, "Default")

            # 1. Saved passwords (SQLite — encrypted by OS, restores on same machine)
            chrome_data["login_data"] = self._backup_file_b64(os.path.join(def_dir, "Login Data"))
            chrome_data["login_data_journal"] = self._backup_file_b64(os.path.join(def_dir, "Login Data-journal"))
            chrome_data["login_data_for_account"] = self._backup_file_b64(os.path.join(def_dir, "Login Data For Account"))
            chrome_data["login_data_for_account_journal"] = self._backup_file_b64(os.path.join(def_dir, "Login Data For Account-journal"))

            # 2. Browsing history & visited pages
            chrome_data["history"] = self._backup_file_b64(os.path.join(def_dir, "History"))
            chrome_data["history_journal"] = self._backup_file_b64(os.path.join(def_dir, "History-journal"))
            chrome_data["top_sites"] = self._backup_file_b64(os.path.join(def_dir, "Top Sites"))
            chrome_data["favicons"] = self._backup_file_b64(os.path.join(def_dir, "Favicons"))
            chrome_data["shortcuts"] = self._backup_file_b64(os.path.join(def_dir, "Shortcuts"))

            # 3. Bookmarks (raw + backup + ordering + parsed JSON)
            bm_path = os.path.join(def_dir, "Bookmarks")
            chrome_data["bookmarks_raw"] = self._backup_file_b64(bm_path)
            chrome_data["bookmarks_bak"] = self._backup_file_b64(os.path.join(def_dir, "Bookmarks.bak"))
            chrome_data["bookmark_ordering"] = self._backup_file_b64(os.path.join(def_dir, "BookmarkMergedSurfaceOrdering"))
            try:
                if bm_path and os.path.isfile(bm_path):
                    with open(bm_path, "r", encoding="utf-8", errors="ignore") as _f:
                        chrome_data["bookmarks"] = json.load(_f)
            except Exception:
                chrome_data["bookmarks"] = {}

            # 4. Autofill / Web forms
            chrome_data["web_data"] = self._backup_file_b64(os.path.join(def_dir, "Web Data"))
            chrome_data["web_data_journal"] = self._backup_file_b64(os.path.join(def_dir, "Web Data-journal"))
            chrome_data["account_web_data"] = self._backup_file_b64(os.path.join(def_dir, "Account Web Data"))

            # 5. Raw Cookies SQLite file & Safe Browsing
            chrome_data["cookies_raw_file"] = self._backup_file_b64(os.path.join(def_dir, "Cookies"))
            chrome_data["cookies_journal"] = self._backup_file_b64(os.path.join(def_dir, "Cookies-journal"))
            chrome_data["safe_browsing_cookies"] = self._backup_file_b64(os.path.join(def_dir, "Safe Browsing Cookies"))

            # 6. HTML5 Local Storage (tar.gz leveldb folder)
            chrome_data["local_storage"] = self._backup_dir_b64(os.path.join(def_dir, "Local Storage"))

            # 7. IndexedDB & WebStorage (tar.gz folders)
            chrome_data["indexeddb"] = self._backup_dir_b64(os.path.join(def_dir, "IndexedDB"))
            chrome_data["web_storage"] = self._backup_dir_b64(os.path.join(def_dir, "WebStorage"))

            # 8. Sessions & Session Storage (tar.gz folders)
            chrome_data["session_storage"] = self._backup_dir_b64(os.path.join(def_dir, "Session Storage"))
            chrome_data["sessions_dir"] = self._backup_dir_b64(os.path.join(def_dir, "Sessions"))

            # 9. Extensions: Local Settings, State, Rules, Scripts, CRX cache
            chrome_data["local_ext_settings"] = self._backup_dir_b64(os.path.join(def_dir, "Local Extension Settings"))
            chrome_data["extension_state"] = self._backup_dir_b64(os.path.join(def_dir, "Extension State"))
            chrome_data["extension_rules"] = self._backup_dir_b64(os.path.join(def_dir, "Extension Rules"))
            chrome_data["extension_scripts"] = self._backup_dir_b64(os.path.join(def_dir, "Extension Scripts"))
            chrome_data["extensions_crx_cache"] = self._backup_dir_b64(os.path.join(cdir, "extensions_crx_cache"))

            # 10. Extensions Metadata & Installed Extensions list (parsed from Preferences)
            ext_meta_path = os.path.join(cdir, "extensions_crx_cache", "metadata.json")
            try:
                if os.path.isfile(ext_meta_path):
                    with open(ext_meta_path, "r", encoding="utf-8", errors="ignore") as _f:
                        chrome_data["extensions_metadata"] = json.load(_f)
                else:
                    chrome_data["extensions_metadata"] = {}
            except Exception:
                chrome_data["extensions_metadata"] = {}

            installed_exts = []
            pref_path = os.path.join(def_dir, "Preferences")
            try:
                if os.path.isfile(pref_path):
                    with open(pref_path, "r", encoding="utf-8", errors="ignore") as _f:
                        pref_json = json.load(_f)
                        ext_settings = pref_json.get("extensions", {}).get("settings", {})
                        for eid, einst in ext_settings.items():
                            manifest = einst.get("manifest", {})
                            installed_exts.append({
                                "id": eid,
                                "name": manifest.get("name") or einst.get("name", "Unknown"),
                                "version": manifest.get("version", ""),
                                "description": manifest.get("description", ""),
                                "enabled": einst.get("state") == 1
                            })
            except Exception:
                pass
            chrome_data["installed_extensions"] = installed_exts

            # 11. Network & Security state
            chrome_data["network_persistent_state"] = self._backup_file_b64(os.path.join(def_dir, "Network Persistent State"))
            chrome_data["transport_security"] = self._backup_file_b64(os.path.join(def_dir, "TransportSecurity"))
            chrome_data["affiliation_database"] = self._backup_file_b64(os.path.join(def_dir, "Affiliation Database"))

            # 12. Local State (master encryption keys) & AdsPower sync files
            chrome_data["local_state"] = self._backup_file_b64(os.path.join(cdir, "Local State"))
            chrome_data["settings_dat"] = self._backup_file_b64(os.path.join(cdir, "settings.dat"))
            chrome_data["sf_cookie"] = self._backup_file_b64(os.path.join(cdir, "sf_cookie.txt"))
            chrome_data["sf_tabs"] = self._backup_file_b64(os.path.join(cdir, "sf_tabs.txt"))
            chrome_data["cookie_updated_time"] = self._backup_file_b64(os.path.join(cdir, "cookie_updated_time"))

            # Count collected items
            filled = sum(1 for v in chrome_data.values() if v)
            logger.info(f"Chrome data backup for {user_id}: {filled}/{len(chrome_data)} items collected")

        fp["chrome_data"] = chrome_data
        fp["chrome_data_summary"] = {
            "has_passwords": bool(chrome_data.get("login_data")),
            "has_history": bool(chrome_data.get("history")),
            "has_bookmarks": bool(chrome_data.get("bookmarks_raw") or chrome_data.get("bookmarks")),
            "has_local_storage": bool(chrome_data.get("local_storage")),
            "has_indexeddb": bool(chrome_data.get("indexeddb") or chrome_data.get("web_storage")),
            "has_extensions": bool(chrome_data.get("installed_extensions") or chrome_data.get("local_ext_settings")),
            "extensions_count": len(chrome_data.get("installed_extensions", [])),
            "has_cookies_db": bool(chrome_data.get("cookies_raw_file") or chrome_data.get("sf_cookie")),
            "has_session_storage": bool(chrome_data.get("session_storage") or chrome_data.get("sessions_dir")),
            "has_autofill": bool(chrome_data.get("web_data")),
            "items_count": len([v for v in chrome_data.values() if v]),
            "has_screen": bool(screen_data.get("resolution")),
            "screen_resolution": res_disp,
            "has_hardware": True,
            "hardware_summary": hw_disp,
            "has_fonts": bool(fonts_list),
            "fonts_count": len(fonts_list),
            "has_user_agent": bool(user_agent),
            "user_agent": user_agent
        }

        return fp



    def export_profile_package(self, user_id: str) -> Dict[str, Any]:
        """
        Creates a complete export package for a profile including:
        - Profile metadata
        - Session cookies
        - Full hardware & software fingerprint (WebGL, Canvas, Audio, OS, Screen)
        - Raw fingerprint files (base64 encoded for exact cross-machine restoration)
        - Proxy configuration
        - Social platform usernames
        - Automation settings
        """
        user_id = str(user_id).strip()
        metadata = self._load_profiles_metadata()
        meta = metadata.get(user_id, {})

        # Ensure we have profile name
        prof_name = meta.get("name")
        group_name = meta.get("group_name", "عام")
        domain_name = meta.get("domain_name", "")

        # Get proxy config
        proxy_config = {
            "proxy_soft": meta.get("proxy_soft", "no_proxy"),
            "proxy_type": meta.get("proxy_type", "http"),
            "proxy_host": meta.get("proxy_host", ""),
            "proxy_port": meta.get("proxy_port", ""),
            "proxy_user": meta.get("proxy_user", ""),
            "proxy_password": meta.get("proxy_password", "")
        }

        # If proxy is missing in metadata, attempt to find in active AdsPower profile list
        if not proxy_config.get("proxy_host"):
            try:
                prof_list = self.get_profiles(page=1, page_size=100).get("profiles", [])
                for p in prof_list:
                    if p.get("user_id") == user_id:
                        if not prof_name:
                            prof_name = p.get("name")
                        if p.get("proxy_host"):
                            proxy_config = {
                                "proxy_soft": p.get("proxy_soft", "other"),
                                "proxy_type": p.get("proxy_type", "http"),
                                "proxy_host": p.get("proxy_host", ""),
                                "proxy_port": p.get("proxy_port", ""),
                                "proxy_user": p.get("proxy_user", ""),
                                "proxy_password": p.get("proxy_password", "")
                            }
                        break
            except Exception:
                pass

        if not prof_name:
            prof_name = f"Profile_{user_id}"

        # Fetch cookies
        cookie_res = self.get_profile_cookies(user_id)
        cookies = cookie_res.get("cookies", [])

        # Fetch full fingerprint
        fingerprint_data = self.get_profile_fingerprint(user_id)

        # Extract usernames & platforms
        plat_configs = meta.get("platforms", {})
        usernames = {
            "instagram": meta.get("instagram_username") or plat_configs.get("instagram", {}).get("username", ""),
            "facebook": meta.get("facebook_username") or plat_configs.get("facebook", {}).get("username", meta.get("page_name", "")),
            "twitter": meta.get("twitter_username") or plat_configs.get("twitter", {}).get("username", "")
        }

        package = {
            "version": "3.0",
            "generator": "AdsPower Full Profile Backup Hub",
            "exported_at": datetime.now().isoformat(),
            "profile": {
                "user_id": user_id,
                "name": prof_name,
                "group_name": group_name,
                "domain_name": domain_name
            },
            "os": fingerprint_data.get("os", "macOS"),
            "user_agent": fingerprint_data.get("user_agent", ""),
            "screen": fingerprint_data.get("screen", {}),
            "hardware": fingerprint_data.get("hardware", {}),
            "fonts": fingerprint_data.get("fonts", []),
            "fonts_count": len(fingerprint_data.get("fonts", [])),
            "cookies": cookies,
            "cookies_count": len(cookies),
            "fingerprint": {
                "os": fingerprint_data.get("os", "macOS"),
                "summary": fingerprint_data.get("summary", ""),
                "user_agent": fingerprint_data.get("user_agent", ""),
                "screen": fingerprint_data.get("screen", {}),
                "hardware": fingerprint_data.get("hardware", {}),
                "fonts": fingerprint_data.get("fonts", []),
                "fonts_count": len(fingerprint_data.get("fonts", [])),
                "webgl": fingerprint_data.get("webgl", {}),
                "noise": fingerprint_data.get("noise", {}),
                "languages": fingerprint_data.get("languages", [])
            },
            "fingerprint_config": fingerprint_data.get("fingerprint_config", {}),
            "raw_fingerprint_files": fingerprint_data.get("raw_files", {}),
            "proxy": proxy_config,
            "usernames": usernames,
            "platforms": plat_configs,
            "chrome_data": fingerprint_data.get("chrome_data", {}),
            "chrome_data_summary": fingerprint_data.get("chrome_data_summary", {})
        }

        return package

    def export_bulk_profiles(self, user_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Creates a consolidated bulk export backup package for multiple or all profiles.
        Each profile contains full metadata, cookies, hardware fingerprint, raw binary files, proxy, and automations.
        """
        if not user_ids:
            prof_res = self.get_profiles(page=1, page_size=200)
            profiles = prof_res.get("profiles", [])
            user_ids = [p.get("user_id") for p in profiles if p.get("user_id")]
            if not user_ids:
                metadata = self._load_profiles_metadata()
                user_ids = list(metadata.keys())

        packages = []
        for uid in user_ids:
            try:
                pkg = self.export_profile_package(uid)
                packages.append(pkg)
            except Exception as e:
                logger.error(f"Error exporting profile {uid} in bulk: {e}")

        return {
            "version": "3.0",
            "backup_type": "adspower_bulk_backup",
            "exported_at": datetime.now().isoformat(),
            "total_profiles": len(packages),
            "packages": packages
        }

    def clone_profile(
        self,
        source_id: str,
        target_name: Optional[str] = None,
        target_profile_id: Optional[str] = None,
        copy_proxy: bool = True,
        copy_automations: bool = True,
        copy_fingerprint: bool = True
    ) -> Dict[str, Any]:
        """
        Clones a profile's session, fingerprint, and configuration.
        Can either:
        1. Clone/inject into an EXISTING profile (bypasses AdsPower 12-profile license limit)
        2. Create a NEW profile in AdsPower with cloned cookies, proxy, and fingerprint
        """
        source_id = str(source_id).strip()
        source_pkg = self.export_profile_package(source_id)
        cookies = source_pkg.get("cookies", [])
        cookies_raw = json.dumps(cookies) if cookies else "[]"
        cookies_count = len(cookies)
        proxy_cfg = source_pkg.get("proxy", {})
        usernames = source_pkg.get("usernames", {})
        plat_configs = source_pkg.get("platforms", {})
        source_name = source_pkg.get("profile", {}).get("name", source_id)
        fp_config = source_pkg.get("fingerprint_config", {})
        fp_summary = source_pkg.get("fingerprint", {}).get("summary", "")

        metadata = self._load_profiles_metadata()

        # MODE 1: Clone into an EXISTING profile
        if target_profile_id and target_profile_id.strip():
            target_profile_id = str(target_profile_id).strip()
            if target_profile_id == source_id:
                return {"success": False, "message": "لا يمكن استنساخ الملف إلى نفسه"}

            # 1. Update cookies & fingerprint in AdsPower API
            cookie_updated = False
            fingerprint_updated = False
            update_payload = {"user_id": target_profile_id}
            if cookies:
                update_payload["cookie"] = cookies_raw
            if copy_fingerprint and fp_config:
                update_payload["fingerprint_config"] = fp_config

            try:
                update_resp = requests.post(
                    f"{self.api_url}/api/v1/user/update",
                    json=update_payload,
                    headers=self._get_headers(),
                    timeout=10
                )
                up_data = update_resp.json()
                if up_data.get("code") == 0:
                    cookie_updated = bool(cookies)
                    fingerprint_updated = bool(fp_config)
                else:
                    logger.warning(f"AdsPower user/update returned: {up_data}")
            except Exception as e:
                logger.warning(f"Failed to update via API for {target_profile_id}: {e}")

            # 2. Deep File Clone: Restore all fingerprint files, cookies, storage, history & passwords
            storage_copied = False
            fingerprint_files_copied = False
            try:
                tgt_cache = self._find_cache_dir(target_profile_id)
                if not tgt_cache:
                    suffix = self._get_active_cache_suffix()
                    tgt_cache = os.path.join(LOCAL_CACHE_DIR, f"{target_profile_id}_{suffix}")
                
                restored_cnt, _ = self._restore_profile_cache_data(tgt_cache, source_pkg)
                storage_copied = restored_cnt > 0
                fingerprint_files_copied = restored_cnt > 0
            except Exception as e:
                logger.warning(f"Failed to copy files between cache directories during clone: {e}")

            # 3. Copy proxy if requested
            proxy_updated = False
            if copy_proxy and proxy_cfg.get("proxy_host"):
                proxy_res = self.update_profile_proxy(target_profile_id, proxy_cfg)
                proxy_updated = proxy_res.get("success", False)

            # 4. Copy automation configs and usernames if requested
            if copy_automations:
                if target_profile_id not in metadata:
                    metadata[target_profile_id] = {}
                tgt_meta = metadata[target_profile_id]
                tgt_meta["instagram_username"] = usernames.get("instagram", "")
                tgt_meta["facebook_username"] = usernames.get("facebook", "")
                tgt_meta["twitter_username"] = usernames.get("twitter", "")
                tgt_meta["platforms"] = plat_configs
                self._save_profiles_metadata(metadata)

            target_name_disp = metadata.get(target_profile_id, {}).get("name", target_profile_id)
            return {
                "success": True,
                "message": f"تم استنساخ البصمة الرقمية بالكامل والجلسة ({cookies_count} كوكيز) إلى: {target_name_disp}",
                "target_profile_id": target_profile_id,
                "target_name": target_name_disp,
                "cookies_count": cookies_count,
                "cookie_updated": cookie_updated,
                "fingerprint_updated": fingerprint_updated,
                "fingerprint_files_copied": fingerprint_files_copied,
                "fingerprint_summary": fp_summary,
                "storage_copied": storage_copied,
                "proxy_updated": proxy_updated
            }

        # MODE 2: Create a NEW profile in AdsPower
        new_name = (target_name or f"{source_name} (نسخة)").strip()
        payload = {
            "name": new_name,
            "group_id": "0",
            "domain_name": source_pkg.get("profile", {}).get("domain_name", "")
        }

        if cookies:
            payload["cookie"] = cookies_raw

        if copy_fingerprint and fp_config:
            src_os = source_pkg.get("os") or source_pkg.get("fingerprint", {}).get("os", "macOS")
            if "mac" in str(src_os).lower():
                ua_sys = ["Mac OS X"]
            elif "win" in str(src_os).lower():
                ua_sys = ["Windows 10", "Windows 11"]
            elif "linux" in str(src_os).lower():
                ua_sys = ["Linux"]
            else:
                ua_sys = ["Mac OS X"]
            if "random_ua" not in fp_config or not isinstance(fp_config["random_ua"], dict):
                fp_config["random_ua"] = {}
            fp_config["random_ua"]["ua_browser"] = ["chrome"]
            fp_config["random_ua"]["ua_version"] = ["151"]
            fp_config["random_ua"]["ua_system_version"] = ua_sys
            if "browser_kernel_config" not in fp_config or not isinstance(fp_config["browser_kernel_config"], dict):
                fp_config["browser_kernel_config"] = {}
            fp_config["browser_kernel_config"]["version"] = "151"
            fp_config["browser_kernel_config"]["type"] = "chrome"
            payload["fingerprint_config"] = fp_config

        if copy_proxy and proxy_cfg.get("proxy_host"):
            payload["user_proxy_config"] = {
                "proxy_soft": proxy_cfg.get("proxy_soft", "other"),
                "proxy_type": proxy_cfg.get("proxy_type", "http"),
                "proxy_host": proxy_cfg.get("proxy_host", ""),
                "proxy_port": str(proxy_cfg.get("proxy_port", "")),
                "proxy_user": proxy_cfg.get("proxy_user", ""),
                "proxy_password": proxy_cfg.get("proxy_password", "")
            }

        try:
            resp = requests.post(
                f"{self.api_url}/api/v1/user/create",
                json=payload,
                headers=self._get_headers(),
                timeout=12
            )
            data = resp.json()
            if data.get("code") != 0 and "12" not in str(data.get("msg", "")) and "exceed" not in str(data.get("msg", "")).lower():
                try:
                    v2_resp = requests.post(
                        f"{self.api_url}/api/v2/browser-profile/create",
                        json=payload,
                        headers=self._get_headers(),
                        timeout=12
                    )
                    v2_data = v2_resp.json()
                    if v2_data.get("code") == 0:
                        data = v2_data
                except Exception:
                    pass
            if data.get("code") == 0:
                new_id = data.get("data", {}).get("id")
                # Save metadata for the new profile
                metadata[new_id] = {
                    "name": new_name,
                    "group_name": "الافتراضية",
                    "domain_name": payload.get("domain_name", "")
                }
                if copy_proxy and proxy_cfg.get("proxy_host"):
                    metadata[new_id].update(payload.get("user_proxy_config", {}))

                if copy_automations:
                    metadata[new_id]["instagram_username"] = usernames.get("instagram", "")
                    metadata[new_id]["facebook_username"] = usernames.get("facebook", "")
                    metadata[new_id]["twitter_username"] = usernames.get("twitter", "")
                    metadata[new_id]["platforms"] = plat_configs

                self._save_profiles_metadata(metadata)

                # Pre-populate new profile's cache directory with full session, storage & fingerprint
                try:
                    tgt_cache = self._find_cache_dir(new_id)
                    if not tgt_cache:
                        suffix = self._get_active_cache_suffix()
                        tgt_cache = os.path.join(LOCAL_CACHE_DIR, f"{new_id}_{suffix}")
                    self._restore_profile_cache_data(tgt_cache, source_pkg)
                except Exception as e:
                    logger.warning(f"Error pre-populating new clone cache: {e}")

                return {
                    "success": True,
                    "message": f"تم إنشاء واستنساخ الملف الجديد بالبصمة الكاملة وبيانات المتصفح بنجاح: {new_name}",
                    "target_profile_id": new_id,
                    "target_name": new_name,
                    "cookies_count": cookies_count,
                    "fingerprint_summary": fp_summary
                }
            else:
                err_msg = data.get("msg", "فشل إنشاء الملف في AdsPower")
                if "12" in err_msg or "exceed" in err_msg.lower():
                    return {
                        "success": False,
                        "limit_reached": True,
                        "message": f"تم الوصول إلى الحد الأقصى لحسابات AdsPower (12 ملف). يرجى اختيار 'استنساخ إلى ملف بروفايل موجود' لنقل الجلسة والبصمة وتجاوز هذا الحد، أو حذف ملف غير مستخدم في AdsPower."
                    }
                return {"success": False, "message": err_msg}
        except Exception as e:
            return {"success": False, "message": f"خطأ اتصال بـ AdsPower: {str(e)}"}

    def import_profile_package(
        self,
        package_data: Dict[str, Any],
        target_profile_id: Optional[str] = None,
        new_name: Optional[str] = None,
        copy_proxy: bool = True,
        copy_automations: bool = True,
        copy_fingerprint: bool = True
    ) -> Dict[str, Any]:
        """
        Imports a profile package from JSON data:
        Can apply to an existing profile or create a new profile.
        Restores:
        - Decrypted session cookies
        - Complete hardware and software fingerprint (WebGL, Canvas, Audio, OS)
        - Raw binary fingerprint files into target cache
        - Proxy configuration and automation settings
        """
        if not isinstance(package_data, dict):
            return {"success": False, "message": "صيغة بيانات JSON غير صالحة"}

        # Handle bulk backup package restoration
        packages = package_data.get("packages")
        if isinstance(packages, list) and packages:
            imported = 0
            failed = 0
            results = []
            existing_data = self.get_profiles(page=1, page_size=200)
            existing_profiles = existing_data.get("profiles", [])
            existing_ids = {p.get("user_id") for p in existing_profiles if isinstance(p, dict) and p.get("user_id")}

            for pkg in packages:
                try:
                    src_uid = pkg.get("profile", {}).get("user_id")
                    tgt_id = src_uid if (src_uid and src_uid in existing_ids) else None
                    res = self.import_profile_package(
                        package_data=pkg,
                        target_profile_id=tgt_id,
                        new_name=pkg.get("profile", {}).get("name"),
                        copy_proxy=copy_proxy,
                        copy_automations=copy_automations,
                        copy_fingerprint=copy_fingerprint
                    )
                    results.append(res)
                    if res.get("success"):
                        imported += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Error importing bulk package item: {e}")
                    failed += 1
            return {
                "success": imported > 0,
                "is_bulk": True,
                "message": f"تمت استعادة {imported} ملف بنجاح من النسخة الاحتياطية" + (f" (وفشل {failed})" if failed else ""),
                "imported_count": imported,
                "failed_count": failed,
                "results": results
            }

        cookies = package_data.get("cookies", [])
        cookies_raw = json.dumps(cookies) if isinstance(cookies, list) else str(cookies)
        cookies_count = len(cookies) if isinstance(cookies, list) else 0

        fp_config = dict(package_data.get("fingerprint_config", {}))

        # Detect canonical target OS from package
        target_os = package_data.get("os") or package_data.get("fingerprint", {}).get("os")
        if not target_os:
            ua_hint = package_data.get("user_agent") or fp_config.get("ua", "")
            if "macintosh" in ua_hint.lower() or "mac os x" in ua_hint.lower():
                target_os = "macOS"
            elif "windows" in ua_hint.lower():
                target_os = "Windows"
            elif "linux" in ua_hint.lower():
                target_os = "Linux"
            else:
                target_os = "macOS"

        if target_os.lower() in ["mac", "macos", "darwin", "mac os x"]:
            canonical_os = "macOS"
            ua_sys_version = ["Mac OS X"]
            canonical_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        elif target_os.lower() in ["win", "windows"]:
            canonical_os = "Windows"
            ua_sys_version = ["Windows 10", "Windows 11"]
            canonical_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        elif target_os.lower() in ["linux"]:
            canonical_os = "Linux"
            ua_sys_version = ["Linux"]
            canonical_ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        else:
            canonical_os = "macOS"
            ua_sys_version = ["Mac OS X"]
            canonical_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"

        # Strictly enforce random_ua and ua_system_version (AdsPower randomizes to Android if omitted!)
        if "random_ua" not in fp_config or not isinstance(fp_config["random_ua"], dict):
            fp_config["random_ua"] = {}
        fp_config["random_ua"]["ua_browser"] = ["chrome"]
        fp_config["random_ua"]["ua_version"] = ["151"]
        fp_config["random_ua"]["ua_system_version"] = ua_sys_version

        # Strictly enforce Chrome 151 browser kernel
        if "browser_kernel_config" not in fp_config or not isinstance(fp_config["browser_kernel_config"], dict):
            fp_config["browser_kernel_config"] = {}
        fp_config["browser_kernel_config"]["version"] = "151"
        fp_config["browser_kernel_config"]["type"] = "chrome"

        # Strictly enforce User-Agent matching canonical OS
        cur_ua = fp_config.get("ua") or package_data.get("user_agent")
        if not cur_ua or (canonical_os == "macOS" and "macintosh" not in cur_ua.lower()):
            fp_config["ua"] = canonical_ua
        else:
            fp_config["ua"] = cur_ua

        # Screen resolution
        if "screen_resolution" not in fp_config or not fp_config["screen_resolution"]:
            scr = package_data.get("screen") or package_data.get("fingerprint", {}).get("screen")
            if isinstance(scr, dict) and scr.get("resolution"):
                fp_config["screen_resolution"] = scr["resolution"]
            else:
                fp_config["screen_resolution"] = "1920_1200"

        # Fonts
        if "fonts" not in fp_config or not fp_config["fonts"]:
            fnts = package_data.get("fonts") or package_data.get("fingerprint", {}).get("fonts")
            if isinstance(fnts, list) and fnts:
                fp_config["fonts"] = fnts
            else:
                fp_config["fonts"] = self._get_default_fonts(canonical_os)

        # Hardware specs
        if "hardware_concurrency" not in fp_config:
            hw = package_data.get("hardware") or package_data.get("fingerprint", {}).get("hardware")
            cores = hw.get("cpu_cores", 8) if isinstance(hw, dict) else 8
            fp_config["hardware_concurrency"] = str(cores)
        if "device_memory" not in fp_config:
            hw = package_data.get("hardware") or package_data.get("fingerprint", {}).get("hardware")
            mem = hw.get("device_memory_gb", 8) if isinstance(hw, dict) else 8
            fp_config["device_memory"] = str(mem)

        # WebGL Config
        if "webgl" not in fp_config or fp_config["webgl"] != "2":
            fp_config["webgl"] = "2"
        if "webgl_config" not in fp_config or not isinstance(fp_config["webgl_config"], dict):
            wg = package_data.get("fingerprint", {}).get("webgl", {})
            fp_config["webgl_config"] = {
                "unmasked_vendor": wg.get("unmasked_vendor", "Google Inc. (Intel Inc.)"),
                "unmasked_renderer": wg.get("unmasked_renderer", "ANGLE (Intel, ANGLE Metal Renderer: Intel(R) Iris(TM) Plus Graphics OpenGL Engine, Unspecified Version)"),
                "webgpu": {"webgpu_switch": "1"}
            }

        raw_files = package_data.get("raw_fingerprint_files", {})
        fp_summary = package_data.get("fingerprint", {}).get("summary", "")

        proxy_cfg = package_data.get("proxy", {})
        usernames = package_data.get("usernames", {})
        plat_configs = package_data.get("platforms", {})
        source_prof = package_data.get("profile", {})
        source_name = source_prof.get("name") or "Profile_Imported"
        chrome_data = package_data.get("chrome_data", {})

        metadata = self._load_profiles_metadata()

        # Target existing profile
        if target_profile_id and target_profile_id.strip():
            target_profile_id = str(target_profile_id).strip()

            # Ensure browser is closed to safely write cache files without locks
            if self.is_browser_active(target_profile_id):
                logger.info(f"Browser {target_profile_id} is active before import. Closing browser...")
                self.stop_browser(target_profile_id)
                time.sleep(2.0)

            update_payload = {"user_id": target_profile_id}
            if cookies:
                update_payload["cookie"] = cookies_raw
            if copy_fingerprint and fp_config:
                update_payload["fingerprint_config"] = fp_config

            try:
                requests.post(
                    f"{self.api_url}/api/v1/user/update",
                    json=update_payload,
                    headers=self._get_headers(),
                    timeout=10
                )
            except Exception as e:
                logger.warning(f"Error applying imported cookies/fingerprint to {target_profile_id}: {e}")

            # Reconstruct raw files and full Chrome profile cache
            tgt_cache = self._find_cache_dir(target_profile_id)
            if not tgt_cache:
                suffix = self._get_active_cache_suffix()
                tgt_cache = os.path.join(LOCAL_CACHE_DIR, f"{target_profile_id}_{suffix}")

            chrome_restored, chrome_skipped = self._restore_profile_cache_data(tgt_cache, package_data)

            if copy_proxy and proxy_cfg.get("proxy_host"):
                self.update_profile_proxy(target_profile_id, proxy_cfg)

            if copy_automations:
                if target_profile_id not in metadata:
                    metadata[target_profile_id] = {}
                tgt_meta = metadata[target_profile_id]
                tgt_meta["instagram_username"] = usernames.get("instagram", "")
                tgt_meta["facebook_username"] = usernames.get("facebook", "")
                tgt_meta["twitter_username"] = usernames.get("twitter", "")
                tgt_meta["platforms"] = plat_configs
                self._save_profiles_metadata(metadata)

            target_name_disp = metadata.get(target_profile_id, {}).get("name", target_profile_id)
            chrome_msg = f" | تم استعادة {chrome_restored} عنصراً (كلمات مرور، تخزين محلي، إضافات، عتاد، شاشة، خطوط)"
            return {
                "success": True,
                "message": f"تم تطبيق البصمة والعتاد والشاشة والجلسة وبيانات Chrome بنجاح على البروفايل: {target_name_disp} ({cookies_count} كوكيز){chrome_msg}",
                "target_profile_id": target_profile_id,
                "target_name": target_name_disp,
                "cookies_count": cookies_count,
                "fingerprint_summary": fp_summary,
                "chrome_data_restored": chrome_restored,
                "chrome_data_skipped": chrome_skipped
            }

        # Create new profile
        target_name = (new_name or f"{source_name} (مستورد)").strip()
        payload = {
            "name": target_name,
            "group_id": "0",
            "domain_name": source_prof.get("domain_name", "")
        }
        if cookies:
            payload["cookie"] = cookies_raw
        if copy_fingerprint and fp_config:
            payload["fingerprint_config"] = fp_config
        if copy_proxy and proxy_cfg.get("proxy_host"):
            payload["user_proxy_config"] = {
                "proxy_soft": proxy_cfg.get("proxy_soft", "other"),
                "proxy_type": proxy_cfg.get("proxy_type", "http"),
                "proxy_host": proxy_cfg.get("proxy_host", ""),
                "proxy_port": str(proxy_cfg.get("proxy_port", "")),
                "proxy_user": proxy_cfg.get("proxy_user", ""),
                "proxy_password": proxy_cfg.get("proxy_password", "")
            }

        try:
            resp = requests.post(
                f"{self.api_url}/api/v1/user/create",
                json=payload,
                headers=self._get_headers(),
                timeout=12
            )
            data = resp.json()
            if data.get("code") != 0 and "12" not in str(data.get("msg", "")) and "exceed" not in str(data.get("msg", "")).lower():
                try:
                    v2_resp = requests.post(
                        f"{self.api_url}/api/v2/browser-profile/create",
                        json=payload,
                        headers=self._get_headers(),
                        timeout=12
                    )
                    v2_data = v2_resp.json()
                    if v2_data.get("code") == 0:
                        data = v2_data
                except Exception:
                    pass
            if data.get("code") == 0:
                new_id = data.get("data", {}).get("id")
                metadata[new_id] = {
                    "name": target_name,
                    "group_name": "الافتراضية",
                    "domain_name": payload.get("domain_name", "")
                }
                if copy_proxy and proxy_cfg.get("proxy_host"):
                    metadata[new_id].update(payload.get("user_proxy_config", {}))

                if copy_automations:
                    metadata[new_id]["instagram_username"] = usernames.get("instagram", "")
                    metadata[new_id]["facebook_username"] = usernames.get("facebook", "")
                    metadata[new_id]["twitter_username"] = usernames.get("twitter", "")
                    metadata[new_id]["platforms"] = plat_configs

                self._save_profiles_metadata(metadata)

                # Pre-populate new profile's cache directory with full session, storage, history, passwords & fingerprint
                tgt_cache = self._find_cache_dir(new_id)
                if not tgt_cache:
                    suffix = self._get_active_cache_suffix()
                    tgt_cache = os.path.join(LOCAL_CACHE_DIR, f"{new_id}_{suffix}")

                chrome_restored, chrome_skipped = self._restore_profile_cache_data(tgt_cache, package_data)

                return {
                    "success": True,
                    "message": f"تم إنشاء بروفايل جديد واستيراد البصمة والعتاد والشاشة والخطوط وبيانات Chrome بنجاح: {target_name} ({chrome_restored} عنصراً مُستعاداً)",
                    "target_profile_id": new_id,
                    "target_name": target_name,
                    "cookies_count": cookies_count,
                    "fingerprint_summary": fp_summary,
                    "chrome_data_restored": chrome_restored,
                    "chrome_data_skipped": chrome_skipped
                }
            else:
                err_msg = data.get("msg", "فشل إنشاء الملف في AdsPower")
                if "12" in err_msg or "exceed" in err_msg.lower():
                    return {
                        "success": False,
                        "limit_reached": True,
                        "message": f"تم الوصول إلى الحد الأقصى لحسابات AdsPower (12 ملف). يرجى اختيار ملف بروفايل حالي للاستيراد فوقه لتجاوز هذا الحد."
                    }
                return {"success": False, "message": err_msg}
        except Exception as e:
            return {"success": False, "message": f"خطأ اتصال بـ AdsPower: {str(e)}"}

    def get_account_plan_info(self) -> Dict[str, Any]:
        """
        Retrieves AdsPower account subscription and plan expiration details.
        Extracts balanceDay timestamp, calculates remaining days/hours,
        account profile capacity and usage.
        """
        config_path = os.path.expanduser("~/.config/adspower_global/config.json")
        user_data = {}
        company_data = {}

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    snapshot_raw = cdata.get("AI_AGENT_STORE_SNAPSHOT")
                    if snapshot_raw:
                        snap = json.loads(snapshot_raw)
                        state = snap.get("state", {})
                        user_data = state.get("user", {})
                        company_data = state.get("company", {})
            except Exception as e:
                logger.warning(f"Error reading AdsPower config for plan info: {e}")

        # Account details
        user_name = user_data.get("userName") or user_data.get("email") or "AdsPower User"
        user_id = user_data.get("userId") or ""
        email = user_data.get("email") or ""
        company = user_data.get("company") or ""
        fee = user_data.get("fee") or "9.00"
        package_account_num = int(user_data.get("packageAccountNum") or 10)
        expired_account_num = int(user_data.get("expiredAccountNum") or 2)
        total_account_num = int(user_data.get("accountNum") or (package_account_num + expired_account_num))
        user_num = int(user_data.get("userNum") or 1)
        package_type = user_data.get("companyPackageType", 1)

        # Plan name
        plan_name = "خطة Base (الأساسية)" if package_type == 1 or total_account_num <= 12 else "خطة Pro (الاحترافية)"

        # Expiration calculation
        balance_day = user_data.get("balanceDay")
        expire_ts = None
        expire_dt = None
        days_left = 0
        hours_left = 0
        mins_left = 0
        is_expired = False
        status = "unknown"
        status_label = "غير معروف"
        expire_date_iso = ""
        expire_date_ar = ""
        remaining_text = ""

        if balance_day:
            try:
                expire_ts = float(balance_day)
                expire_dt = datetime.fromtimestamp(expire_ts)
                now = datetime.now()
                diff_seconds = expire_ts - now.timestamp()

                is_expired = diff_seconds <= 0
                days_left = int(diff_seconds // 86400)
                hours_left = int((diff_seconds % 86400) // 3600)
                mins_left = int((diff_seconds % 3600) // 60)

                months_ar = [
                    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"
                ]
                month_name = months_ar[expire_dt.month - 1]
                am_pm = "ص" if expire_dt.hour < 12 else "م"
                hour_12 = expire_dt.hour % 12 or 12
                expire_date_ar = f"{expire_dt.day} {month_name} {expire_dt.year} الساعة {hour_12:02d}:{expire_dt.minute:02d} {am_pm}"
                expire_date_iso = expire_dt.strftime("%Y-%m-%d %H:%M:%S")

                if is_expired:
                    status = "expired"
                    status_label = "منتهي الصلاحية"
                    remaining_text = "انتهت فترة الاشتراك"
                elif days_left <= 0 and hours_left > 0:
                    status = "critical"
                    status_label = "ينتهي اليوم"
                    remaining_text = f"متبقي {hours_left} ساعة و {mins_left} دقيقة"
                elif days_left <= 3:
                    status = "critical"
                    status_label = "ينتهي قريباً جداً"
                    remaining_text = f"متبقي {days_left} أيام و {hours_left} ساعة" if hours_left > 0 else f"متبقي {days_left} أيام"
                elif days_left <= 7:
                    status = "expiring_soon"
                    status_label = "ينتهي قريباً"
                    remaining_text = f"متبقي {days_left} أيام و {hours_left} ساعة" if hours_left > 0 else f"متبقي {days_left} أيام"
                else:
                    status = "active"
                    status_label = "نشط"
                    remaining_text = f"متبقي {days_left} يوماً"
            except Exception as e:
                logger.warning(f"Error parsing balanceDay {balance_day}: {e}")

        # Current profile usage
        local_profiles = self._discover_local_profiles()
        used_profiles = len(local_profiles)
        usage_pct = round((used_profiles / total_account_num) * 100, 1) if total_account_num > 0 else 0

        return {
            "success": True,
            "has_data": bool(balance_day),
            "user_name": user_name,
            "user_id": user_id,
            "email": email,
            "company": company,
            "fee": str(fee),
            "fee_formatted": f"${fee} / شهرياً",
            "plan_name": plan_name,
            "package_type": package_type,
            "balance_day_raw": balance_day,
            "expire_timestamp": expire_ts,
            "expire_date_iso": expire_date_iso,
            "expire_date_ar": expire_date_ar,
            "days_left": max(0, days_left),
            "hours_left": max(0, hours_left),
            "mins_left": max(0, mins_left),
            "is_expired": is_expired,
            "status": status,
            "status_label": status_label,
            "remaining_text": remaining_text,
            "max_profiles": total_account_num,
            "package_account_num": package_account_num,
            "expired_account_num": expired_account_num,
            "used_profiles": used_profiles,
            "usage_percentage": usage_pct,
            "has_renewal": bool(user_data.get("hasRenewal", False)),
            "has_subscription": bool(user_data.get("hasSubscription", False))
        }



