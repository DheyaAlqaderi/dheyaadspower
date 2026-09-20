import os
import json
import time
import threading
from collections import deque
from typing import Dict, Any, List, Optional

from automations.base import PROCESSED_LOG_FILE, BaseAutomationWorker
from automations.facebook import FacebookWorker
from automations.instagram import InstagramWorker
from automations.twitter import TwitterWorker
from automations.tiktok import TikTokWorker

WORKER_REGISTRY = {
    "facebook": FacebookWorker,
    "instagram": InstagramWorker,
    "twitter": TwitterWorker,
    "x": TwitterWorker,
    "tiktok": TikTokWorker,
}


def get_worker_class(platform: str):
    plat = (platform or "").strip().lower()
    return WORKER_REGISTRY.get(plat, FacebookWorker)


class MultiPlatformAutomationHub:
    """Central orchestrator managing concurrent automation runs across multiple profiles & platforms."""
    def __init__(self, adspower_client):
        self.adspower_client = adspower_client
        self.workers: Dict[str, BaseAutomationWorker] = {}
        self.logs = deque(maxlen=1000)
        self.log_counter = 0
        self.start_time: Optional[float] = None
        self._lock = threading.Lock()

    def add_log(self, profile_id: str, profile_name: str, platform: str, level: str, message: str):
        with self._lock:
            self.log_counter += 1
            entry = {
                "id": self.log_counter,
                "time": time.strftime("%H:%M:%S"),
                "profile_id": profile_id,
                "profile_name": profile_name,
                "platform": platform,
                "level": level,
                "message": message
            }
            self.logs.append(entry)

    def load_processed_ids(self) -> set:
        if os.path.exists(PROCESSED_LOG_FILE):
            try:
                with open(PROCESSED_LOG_FILE, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

    def record_processed_id(self, comment_id: str, id_set: set):
        id_set.add(comment_id)
        try:
            with open(PROCESSED_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(list(id_set), f, indent=2)
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        active_workers = {k: w for k, w in self.workers.items() if w.thread and w.thread.is_alive()}
        is_running = len(active_workers) > 0
        unique_profiles_running = len(set(w.profile_id for w in active_workers.values()))

        uptime_str = "00:00:00"
        if is_running and self.start_time:
            elapsed = int(time.time() - self.start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            uptime_str = f"{h:02d}:{m:02d}:{s:02d}"

        # Aggregate stats
        total_scanned = sum(w.stats["comments_scanned"] for w in self.workers.values())
        total_replies = sum(w.stats["replies_sent"] for w in self.workers.values())
        total_dms = sum(w.stats["dms_sent"] for w in self.workers.values())
        total_errors = sum(w.stats["errors"] for w in self.workers.values())

        workers_info = []
        for k, w in self.workers.items():
            workers_info.append({
                "worker_key": k,
                "profile_id": w.profile_id,
                "profile_name": w.profile_name,
                "platform": w.platform,
                "status": w.status,
                "is_alive": bool(w.thread and w.thread.is_alive()),
                "replies": w.stats["replies_sent"],
                "dms": w.stats["dms_sent"]
            })

        return {
            "is_running": is_running,
            "running_count": len(active_workers),
            "unique_profiles_count": unique_profiles_running,
            "stats": {
                "uptime": uptime_str,
                "comments_scanned": total_scanned,
                "replies_sent": total_replies,
                "dms_sent": total_dms,
                "errors": total_errors,
                "status": "نشط" if is_running else "متوقف",
                "last_action": self.logs[-1]["message"] if self.logs else "لا يوجد نشاط بعد"
            },
            "workers": workers_info
        }

    def get_profile_active_platforms(self, profile_id: str) -> Dict[str, Any]:
        """Returns the real-time automation status of each platform for a specific profile."""
        result = {}
        for plat in ["instagram", "facebook", "twitter", "tiktok"]:
            key = f"{profile_id}_{plat}"
            w = self.workers.get(key)
            if not w and plat == "twitter":
                w = self.workers.get(f"{profile_id}_x")

            is_act = bool(w and w.thread and w.thread.is_alive())
            result[plat] = {
                "is_running": is_act,
                "status": w.status if is_act else "متوقف",
                "replies": w.stats["replies_sent"] if w else 0,
                "dms": w.stats["dms_sent"] if w else 0
            }
        return result

    def get_logs(self, last_id: int = 0, filter_profile: str = "", filter_platform: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            res = []
            for log in self.logs:
                if log["id"] > last_id:
                    if filter_profile and log["profile_id"] != filter_profile:
                        continue
                    if filter_platform and log["platform"] != filter_platform:
                        continue
                    res.append(log)
            return res

    def clear_logs(self):
        with self._lock:
            self.logs.clear()

    def start_profile_automation(self, profile_id: str, profile_name: str, platform: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Starts automation on a single platform for a single profile."""
        worker_key = f"{profile_id}_{platform.lower()}"
        if worker_key in self.workers and self.workers[worker_key].thread and self.workers[worker_key].thread.is_alive():
            return {"success": False, "message": f"أتمتة منصة [{platform.upper()}] قيد التشغيل بالفعل لهذا الملف"}

        if not self.start_time:
            self.start_time = time.time()

        worker_cls = get_worker_class(platform)
        worker = worker_cls(profile_id, profile_name, platform, config, self)
        worker.worker_key = worker_key
        self.workers[worker_key] = worker

        t = threading.Thread(target=worker.run, daemon=True)
        worker.thread = t
        t.start()

        return {
            "success": True,
            "worker_key": worker_key,
            "message": f"تم بدء أتمتة [{platform.upper()}] بنجاح للملف [{profile_name}]"
        }

    def stop_profile_automation(self, profile_id: str, platform: Optional[str] = None) -> Dict[str, Any]:
        """Stops a specific platform or all platforms for a given profile."""
        stopped = 0
        if platform:
            worker_key = f"{profile_id}_{platform.lower()}"
            w = self.workers.get(worker_key)
            if not w and platform.lower() == "twitter":
                w = self.workers.get(f"{profile_id}_x")
            if w and w.thread and w.thread.is_alive():
                w.stop_requested = True
                w.status = "جاري الإيقاف..."
                return {"success": True, "message": f"تم طلب إيقاف أتمتة [{platform.upper()}]"}
            return {"success": False, "message": f"أتمتة [{platform.upper()}] غير قيد التشغيل"}
        else:
            for k, w in self.workers.items():
                if w.profile_id == profile_id and w.thread and w.thread.is_alive():
                    w.stop_requested = True
                    w.status = "جاري الإيقاف..."
                    stopped += 1
            return {
                "success": stopped > 0,
                "stopped_count": stopped,
                "message": f"تم طلب إيقاف {stopped} أتمتة للملف {profile_id}"
            }

    def start_bulk(self, profiles_info: List[Dict[str, Any]], platform: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Starts concurrent automation on multiple profiles for a given platform with safe launch staggering."""
        if not profiles_info:
            return {"success": False, "message": "لم يتم تحديد أي ملفات للتشغيل"}

        if not self.start_time:
            self.start_time = time.time()

        worker_cls = get_worker_class(platform)

        started = 0
        total = len(profiles_info)

        def _staggered_runner(w: BaseAutomationWorker, delay: float, order_idx: int, total_cnt: int):
            if delay > 0:
                w.status = f"انتظار دور التشغيل ({order_idx + 1}/{total_cnt})..."
                w.log("INFO", f"⏳ انتظار دور تشغيل المتصفح للملف [{w.profile_name}] ({order_idx + 1}/{total_cnt}) لتفادي ضغط AdsPower...")
                time.sleep(delay)
            if not w.stop_requested:
                w.run()

        for idx, p in enumerate(profiles_info):
            pid = p["id"]
            pname = p.get("name", pid)
            worker_key = f"{pid}_{platform.lower()}"

            # Skip if this platform worker already alive for this profile
            if worker_key in self.workers and self.workers[worker_key].thread and self.workers[worker_key].thread.is_alive():
                continue

            # Use profile-specific config if supplied, otherwise fallback to shared config
            prof_config = p.get("config") if isinstance(p.get("config"), dict) and p.get("config") else config

            worker = worker_cls(pid, pname, platform, prof_config, self)
            worker.worker_key = worker_key
            self.workers[worker_key] = worker

            # 3-second safe stagger delay between starting consecutive browsers
            launch_delay = idx * 3.0
            t = threading.Thread(target=_staggered_runner, args=(worker, launch_delay, idx, total), daemon=True)
            worker.thread = t
            t.start()
            started += 1

        return {
            "success": started > 0,
            "started_count": started,
            "message": f"تم بدء تشغيل أتمتة [{platform.upper()}] بنجاح على {started} ملف بتتابع آمن!"
        }

    def stop_profile(self, profile_id: str) -> Dict[str, Any]:
        return self.stop_profile_automation(profile_id)

    def stop_all(self) -> Dict[str, Any]:
        count = 0
        for k, w in self.workers.items():
            if w.thread and w.thread.is_alive():
                w.stop_requested = True
                w.status = "جاري الإيقاف..."
                count += 1
        return {"success": True, "message": f"تم طلب إيقاف {count} مهمة أتمتة بأمان"}
