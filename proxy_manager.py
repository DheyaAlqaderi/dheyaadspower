import json
import os
import re
import time
import uuid
import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ProxyManager")


class ProxyManager:
    def __init__(self, file_path: str = "proxies.json"):
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def load_proxies(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading proxies file: {e}")
            return []

    def save_proxies(self, proxies: List[Dict[str, Any]]) -> bool:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(proxies, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving proxies: {e}")
            return False

    def sync_from_adspower(self, adspower_client) -> Dict[str, Any]:
        """Fetches all proxies saved in AdsPower (profiles and proxy list) and syncs them."""
        discovered = adspower_client.fetch_all_adspower_proxies()
        proxies = self.load_proxies()
        imported = 0
        updated = 0

        def _px_key(p):
            h = (p.get("host") or "").strip().lower()
            pt = str(p.get("port") or "").strip()
            u = (p.get("user") or "").strip()
            return f"{h}:{pt}:{u}"

        for item in discovered:
            host = (item.get("host") or "").strip()
            port = str(item.get("port") or "").strip()
            user = (item.get("user") or "").strip()
            password = (item.get("password") or "").strip()
            if not host or not port:
                continue

            item_key = _px_key(item)
            existing = next((p for p in proxies if _px_key(p) == item_key), None)

            if existing:
                modified = False
                if item.get("assigned_to") and existing.get("assigned_to") != item.get("assigned_to"):
                    existing["assigned_to"] = item.get("assigned_to")
                    existing["assigned_profile_name"] = item.get("assigned_profile_name")
                    modified = True
                if password and not existing.get("password"):
                    existing["password"] = password
                    modified = True
                if item.get("last_ip") and not existing.get("last_ip"):
                    existing["last_ip"] = item.get("last_ip")
                    modified = True
                if modified:
                    updated += 1
            else:
                new_px = {
                    "id": f"px_{uuid.uuid4().hex[:8]}",
                    "host": host,
                    "port": port,
                    "type": (item.get("type") or "http").lower(),
                    "user": user,
                    "password": password,
                    "status": "untested",
                    "latency_ms": None,
                    "assigned_to": item.get("assigned_to"),
                    "assigned_profile_name": item.get("assigned_profile_name"),
                    "source": item.get("source", "AdsPower"),
                    "created_at": time.strftime("%Y-%m-%d %H:%M"),
                    "last_ip": item.get("last_ip")
                }
                proxies.insert(0, new_px)
                imported += 1

        self.save_proxies(proxies)
        if imported > 0:
            msg = f"تم استيراد {imported} بروكسي جديد من AdsPower (المجموع: {len(proxies)})"
        elif updated > 0:
            msg = f"تم تحديث بيانات وتعيينات {updated} بروكسي مع AdsPower (المجموع: {len(proxies)})"
        else:
            msg = f"كافة البروكسيات ({len(proxies)}) متزامنة ومحدثة بالفعل مع AdsPower"

        return {
            "success": True,
            "message": msg,
            "imported_count": imported,
            "updated_count": updated,
            "total_count": len(proxies)
        }

    def add_proxy(self, proxy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Adds a single proxy to the list."""
        proxies = self.load_proxies()

        new_proxy = {
            "id": f"px_{uuid.uuid4().hex[:8]}",
            "host": proxy_data.get("host", "").strip(),
            "port": str(proxy_data.get("port", "")).strip(),
            "type": (proxy_data.get("type") or "http").lower().strip(),
            "user": proxy_data.get("user", "").strip(),
            "password": proxy_data.get("password", "").strip(),
            "country": proxy_data.get("country", "").strip(),
            "status": "untested",
            "latency_ms": None,
            "assigned_to": None,
            "assigned_profile_name": None,
            "source": "إضافة يدوية",
            "created_at": time.strftime("%Y-%m-%d %H:%M")
        }

        if not new_proxy["host"] or not new_proxy["port"]:
            return {"success": False, "message": "يجب إدخال عنوان IP والمنفذ (Port) بشكل صحيح"}

        def _px_key(p):
            h = (p.get("host") or "").strip().lower()
            pt = str(p.get("port") or "").strip()
            u = (p.get("user") or "").strip()
            return f"{h}:{pt}:{u}"

        target_key = _px_key(new_proxy)
        for p in proxies:
            if _px_key(p) == target_key:
                return {"success": False, "message": "هذا البروكسي موجود بالفعل في القائمة بنفس البيانات والمستخدم"}

        proxies.insert(0, new_proxy)
        self.save_proxies(proxies)
        return {"success": True, "message": "تمت إضافة البروكسي بنجاح", "proxy": new_proxy}

    def bulk_add_proxies(self, text: str, default_type: str = "http") -> Dict[str, Any]:
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        added = 0
        updated = 0
        errors = 0
        proxies = self.load_proxies()

        def _px_key(p):
            h = (p.get("host") or "").strip().lower()
            pt = str(p.get("port") or "").strip()
            u = (p.get("user") or "").strip()
            return f"{h}:{pt}:{u}"

        for line in lines:
            proxy_dict = self.parse_proxy_string(line, default_type)
            if not proxy_dict:
                errors += 1
                continue

            target_key = _px_key(proxy_dict)
            existing_proxy = next((p for p in proxies if _px_key(p) == target_key), None)
            if existing_proxy:
                changed = False
                if proxy_dict.get("country") and existing_proxy.get("country") != proxy_dict.get("country"):
                    existing_proxy["country"] = proxy_dict["country"]
                    changed = True
                if proxy_dict.get("password") and not existing_proxy.get("password"):
                    existing_proxy["password"] = proxy_dict["password"]
                    changed = True
                if changed:
                    updated += 1
            else:
                proxy_dict["id"] = f"px_{uuid.uuid4().hex[:8]}"
                proxy_dict["status"] = "untested"
                proxy_dict["latency_ms"] = None
                proxy_dict["assigned_to"] = None
                proxy_dict["assigned_profile_name"] = None
                proxy_dict["source"] = "استيراد جماعي"
                proxy_dict["created_at"] = time.strftime("%Y-%m-%d %H:%M")
                proxies.insert(0, proxy_dict)
                added += 1

        self.save_proxies(proxies)
        msg = f"تمت إضافة {added} بروكسي بنجاح"
        if updated > 0:
            msg += f" (تم تحديث {updated} بروكسي موجود مسبقاً)"
        if errors > 0:
            msg += f" (تم تجاهل {errors} سطر غير صالح)"

        return {
            "success": True,
            "message": msg,
            "added_count": added,
            "updated_count": updated,
            "error_count": errors
        }

    @staticmethod
    def parse_proxy_string(raw: str, default_type: str = "http") -> Optional[Dict[str, str]]:
        raw = raw.strip().strip("\"'")
        if not raw:
            return None

        country = ""
        ptype = default_type.lower()
        user = ""
        pwd = ""
        host = ""
        port = ""

        # 1. Detect scheme (e.g. geolocation://, http://, https://, socks5://, socks4://)
        scheme_match = re.match(r"^([a-zA-Z0-9_-]+)://(.*)$", raw)
        if scheme_match:
            scheme = scheme_match.group(1).lower()
            if scheme in ["http", "https", "socks5", "socks4"]:
                ptype = "http" if scheme == "https" else scheme
            else:
                # E.g. geolocation:// or provider scheme -> default to HTTP
                ptype = default_type.lower()
            raw = scheme_match.group(2).strip()

        # 2. Detect user:pass@ or user@ before host
        if "@" in raw:
            auth_part, host_part = raw.split("@", 1)
            if ":" in auth_part:
                user, pwd = auth_part.split(":", 1)
            else:
                user = auth_part
            raw = host_part.strip()

        # 3. Check colon separated parts: host:port[:user:pass][:country]
        parts = [p.strip() for p in raw.split(":") if p.strip()]
        if not parts:
            return None

        if len(parts) == 1:
            return None
        elif len(parts) == 2:
            host, port = parts[0], parts[1]
        elif len(parts) == 3:
            if user or pwd:
                host, port, country = parts[0], parts[1], parts[2]
            else:
                host, port, country = parts[0], parts[1], parts[2]
        elif len(parts) == 4:
            if user or pwd:
                host, port = parts[0], parts[1]
                country = ":".join(parts[2:])
            else:
                host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
        elif len(parts) >= 5:
            if user or pwd:
                host, port = parts[0], parts[1]
                country = ":".join(parts[2:])
            else:
                host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
                country = ":".join(parts[4:])

        # Clean port: keep digits only
        port = re.sub(r"\D", "", port)
        if not host or not port:
            return None

        return {
            "type": ptype,
            "host": host,
            "port": port,
            "user": user,
            "password": pwd,
            "country": country
        }

    def delete_proxy(self, proxy_id: str) -> Dict[str, Any]:
        proxies = self.load_proxies()
        initial_len = len(proxies)
        proxies = [p for p in proxies if p["id"] != proxy_id]

        if len(proxies) < initial_len:
            self.save_proxies(proxies)
            return {"success": True, "message": "تم حذف البروكسي بنجاح"}
        return {"success": False, "message": "البروكسي غير موجود"}

    def test_proxy(self, proxy_id: str) -> Dict[str, Any]:
        proxies = self.load_proxies()
        target = next((p for p in proxies if p["id"] == proxy_id), None)
        if not target:
            return {"success": False, "message": "البروكسي غير موجود"}

        protocol = target.get("type", "http").lower()
        host = target.get("host")
        port = target.get("port")
        user = target.get("user")
        pwd = target.get("password")

        auth_str = f"{user}:{pwd}@" if user and pwd else ""
        proxy_url = f"{protocol}://{auth_str}{host}:{port}"
        proxies_dict = {
            "http": proxy_url,
            "https": proxy_url
        }

        test_urls = [
            "http://api.ipify.org?format=json",
            "http://ip-api.com/json",
            "https://api.ipify.org?format=json"
        ]
        start_time = time.time()
        tested_ip = ""

        for test_url in test_urls:
            try:
                resp = requests.get(test_url, proxies=proxies_dict, timeout=10)

                # Check for FloppyData / proxy provider quota expiration
                if resp.status_code == 402 or "payment required" in resp.text.lower():
                    target["status"] = "expired"
                    target["latency_ms"] = None
                    target["error_msg"] = "باقة البروكسي منتهية (402 Payment Required)"
                    self.save_proxies(proxies)
                    return {
                        "success": False,
                        "status": "expired",
                        "message": "انتهت باقة أو رصيد هذا البروكسي لدى مزود الخدمة FloppyData (402 Payment Required)"
                    }

                # Check for auth failure
                if resp.status_code in [401, 407] or "authentication" in resp.text.lower():
                    target["status"] = "failed"
                    target["latency_ms"] = None
                    target["error_msg"] = "بيانات المصادقة غير صحيحة (407)"
                    self.save_proxies(proxies)
                    return {
                        "success": False,
                        "status": "failed",
                        "message": "فشل الاتصال: اسم المستخدم أو كلمة المرور غير صحيحة"
                    }

                if resp.status_code == 200:
                    latency = int((time.time() - start_time) * 1000)
                    try:
                        res_json = resp.json()
                        tested_ip = res_json.get("ip", "") or res_json.get("query", "") or res_json.get("origin", "")
                        if not target.get("country") and res_json.get("country"):
                            target["country"] = res_json.get("country")
                    except Exception:
                        tested_ip = host
                    target["status"] = "active"
                    target["latency_ms"] = latency
                    target["last_ip"] = tested_ip
                    target["error_msg"] = None
                    self.save_proxies(proxies)
                    return {
                        "success": True,
                        "status": "active",
                        "latency_ms": latency,
                        "ip": tested_ip,
                        "message": f"البروكسي نشط وشغال! السرعة: {latency}ms (IP: {tested_ip})"
                    }
            except Exception as e:
                err_str = str(e)
                if "402" in err_str or "payment required" in err_str.lower():
                    target["status"] = "expired"
                    target["latency_ms"] = None
                    target["error_msg"] = "باقة البروكسي منتهية (Payment Required)"
                    self.save_proxies(proxies)
                    return {
                        "success": False,
                        "status": "expired",
                        "message": "انتهت باقة أو رصيد هذا البروكسي لدى مزود الخدمة FloppyData (402 Payment Required)"
                    }
                continue

        target["status"] = "failed"
        target["latency_ms"] = None
        target["error_msg"] = "فشل الاتصال بالبروكسي"
        self.save_proxies(proxies)
        return {
            "success": False,
            "status": "failed",
            "message": "فشل الاتصال بالبروكسي (انتهت مهلة الاتصال أو تعذر الوصول للهوست)"
        }

    def assign_to_profile(self, proxy_id: str, profile_id: str, profile_name: str, adspower_client) -> Dict[str, Any]:
        proxies = self.load_proxies()
        proxy = next((p for p in proxies if p["id"] == proxy_id), None)
        if not proxy:
            return {"success": False, "message": "البروكسي غير موجود"}

        res = adspower_client.update_profile_proxy(profile_id, proxy)
        if res.get("success"):
            proxy["assigned_to"] = profile_id
            proxy["assigned_profile_name"] = profile_name
            self.save_proxies(proxies)
            return {
                "success": True,
                "message": f"تم تعيين البروكسي للملف '{profile_name}' بنجاح"
            }
        else:
            return {
                "success": False,
                "message": f"فشل التعيين: {res.get('message')}"
            }

    def unassign_from_profile(self, proxy_id: str, adspower_client) -> Dict[str, Any]:
        proxies = self.load_proxies()
        proxy = next((p for p in proxies if p["id"] == proxy_id), None)
        if not proxy:
            return {"success": False, "message": "البروكسي غير موجود"}

        profile_id = proxy.get("assigned_to")
        if profile_id:
            adspower_client.remove_profile_proxy(profile_id)

        proxy["assigned_to"] = None
        proxy["assigned_profile_name"] = None
        self.save_proxies(proxies)
        return {"success": True, "message": "تم إلغاء ربط البروكسي بالملف بنجاح"}
