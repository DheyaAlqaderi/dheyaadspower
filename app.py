import os
import json
import logging
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, make_response

from adspower_client import AdsPowerClient
from proxy_manager import ProxyManager
from automation_runner import MultiPlatformAutomationHub

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DashboardApp")

CONFIG_FILE = "config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "adspower_api_url": "http://127.0.0.1:50325",
        "api_key": "",
        "default_profile_id": "",
        "post_url": "",
        "page_name": "DheyaStore",
        "public_reply_template": "Hello {name}! Thanks for reaching out. Please check your inbox 📩",
        "private_dm_template": "Hi {name}, thank you for your comment! How can we assist you with our store today?",
        "check_interval_seconds": 45,
        "port": 5000
    }


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False


config = load_config()

# Initialize core services
adspower_client = AdsPowerClient(
    api_url=config.get("adspower_api_url", "http://127.0.0.1:50325"),
    api_key=config.get("api_key", "")
)
proxy_manager = ProxyManager("proxies.json")
automation_hub = MultiPlatformAutomationHub(adspower_client)

app = Flask(__name__)


# -------------------------- WEB PAGES --------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -------------------------- STATUS & HEALTH --------------------------
@app.route("/api/status", methods=["GET"])
def get_system_status():
    adspower_conn = adspower_client.check_connection()
    runner_status = automation_hub.get_status()
    proxies = proxy_manager.load_proxies()
    plan_info = adspower_client.get_account_plan_info()

    return jsonify({
        "adspower": adspower_conn,
        "runner": runner_status,
        "proxy_count": len(proxies),
        "plan": plan_info,
        "config": {
            "adspower_api_url": adspower_client.api_url,
            "has_api_key": bool(adspower_client.api_key)
        }
    })


@app.route("/api/adspower/plan", methods=["GET"])
def get_adspower_plan():
    """Returns AdsPower account subscription and expiration plan details."""
    plan_info = adspower_client.get_account_plan_info()
    return jsonify(plan_info)


# -------------------------- CONFIGURATION --------------------------
@app.route("/api/config", methods=["GET", "POST"])
def manage_config():
    global config
    if request.method == "GET":
        return jsonify({"success": True, "config": config})

    data = request.get_json() or {}
    config.update(data)
    save_config(config)

    # Reconfigure adspower client
    adspower_client.api_url = config.get("adspower_api_url", "http://127.0.0.1:50325").rstrip("/")
    adspower_client.api_key = config.get("api_key", "")

    return jsonify({"success": True, "message": "تم حفظ الإعدادات بنجاح", "config": config})


# -------------------------- ADSPOWER PROFILES --------------------------
@app.route("/api/profiles", methods=["GET"])
def get_profiles():
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 100))
    res = adspower_client.get_profiles(page=page, page_size=page_size)
    return jsonify(res)


@app.route("/api/profiles/add", methods=["POST"])
def add_profile():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()
    name = data.get("name", "").strip()
    group_name = data.get("group_name", "عام").strip()
    res = adspower_client.add_custom_profile(user_id, name, group_name)
    return jsonify(res)


@app.route("/api/profiles/<profile_id>/start", methods=["POST"])
def start_profile_browser(profile_id):
    res = adspower_client.start_browser(profile_id)
    return jsonify(res)


@app.route("/api/profiles/<profile_id>/stop", methods=["POST"])
def stop_profile_browser(profile_id):
    res = adspower_client.stop_browser(profile_id)
    return jsonify(res)


@app.route("/api/profiles/<profile_id>/proxy", methods=["POST", "DELETE"])
def profile_proxy(profile_id):
    if request.method == "DELETE":
        res = adspower_client.remove_profile_proxy(profile_id)
        return jsonify(res)

    proxy_data = request.get_json() or {}
    res = adspower_client.update_profile_proxy(profile_id, proxy_data)
    return jsonify(res)


# -------------------------- PROFILE SESSION & CLONING --------------------------
@app.route("/api/profiles/<profile_id>/cookies", methods=["GET"])
def get_profile_cookies_endpoint(profile_id):
    res = adspower_client.get_profile_cookies(profile_id)
    return jsonify(res)


@app.route("/api/profiles/<profile_id>/export", methods=["GET"])
def export_profile_endpoint(profile_id):
    try:
        pkg = adspower_client.export_profile_package(profile_id)
        download = request.args.get("download", "true").lower() == "true"
        prof_name = pkg.get("profile", {}).get("name", profile_id)
        
        # Pure ASCII fallback filename for HTTP latin-1 header compatibility
        ascii_filename = f"profile_{profile_id}_session.json"
        
        # UTF-8 encoded filename for modern browsers supporting RFC 5987 / RFC 6266
        raw_filename = f"profile_{profile_id}_{prof_name}_session.json"
        encoded_filename = urllib.parse.quote(raw_filename)

        if download:
            json_str = json.dumps(pkg, indent=2, ensure_ascii=False)
            return Response(
                json_str,
                mimetype="application/json; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"
                }
            )
        return jsonify({"success": True, "package": pkg})
    except Exception as e:
        logger.error(f"Error exporting profile {profile_id}: {e}")
        return jsonify({"success": False, "message": f"حدث خطأ أثناء تصدير البروفايل: {str(e)}"})


@app.route("/api/profiles/<profile_id>/clone", methods=["POST"])
def clone_profile_endpoint(profile_id):
    try:
        data = request.get_json() or {}
        mode = data.get("mode", "existing")
        target_profile_id = data.get("target_profile_id") if mode == "existing" else None
        target_name = data.get("target_name")
        copy_proxy = data.get("copy_proxy", True)
        copy_automations = data.get("copy_automations", True)
        copy_fingerprint = data.get("copy_fingerprint", True)

        res = adspower_client.clone_profile(
            source_id=profile_id,
            target_name=target_name,
            target_profile_id=target_profile_id,
            copy_proxy=copy_proxy,
            copy_automations=copy_automations,
            copy_fingerprint=copy_fingerprint
        )
        return jsonify(res)
    except Exception as e:
        logger.error(f"Error cloning profile {profile_id}: {e}")
        return jsonify({"success": False, "message": f"خطأ أثناء استنساخ البروفايل: {str(e)}"})


@app.route("/api/profiles/import", methods=["POST"])
def import_profile_endpoint():
    try:
        package_data = None
        target_profile_id = None
        new_name = None
        copy_proxy = True
        copy_automations = True
        copy_fingerprint = True

        if request.content_type and "multipart/form-data" in request.content_type:
            uploaded_file = request.files.get("file")
            if not uploaded_file:
                return jsonify({"success": False, "message": "لم يتم اختيار ملف JSON"})
            content = uploaded_file.read().decode("utf-8")
            package_data = json.loads(content)
            target_profile_id = request.form.get("target_profile_id")
            new_name = request.form.get("target_name")
            copy_proxy = request.form.get("copy_proxy", "true").lower() == "true"
            copy_automations = request.form.get("copy_automations", "true").lower() == "true"
            copy_fingerprint = request.form.get("copy_fingerprint", "true").lower() == "true"
        else:
            data = request.get_json() or {}
            package_data = data.get("package") or data
            target_profile_id = data.get("target_profile_id")
            new_name = data.get("target_name")
            copy_proxy = data.get("copy_proxy", True)
            copy_automations = data.get("copy_automations", True)
            copy_fingerprint = data.get("copy_fingerprint", True)

        if not package_data or not isinstance(package_data, dict):
            return jsonify({"success": False, "message": "ملف JSON غير صالح أو فارغ"})

        res = adspower_client.import_profile_package(
            package_data=package_data,
            target_profile_id=target_profile_id,
            new_name=new_name,
            copy_proxy=copy_proxy,
            copy_automations=copy_automations,
            copy_fingerprint=copy_fingerprint
        )
        return jsonify(res)
    except Exception as e:
        logger.error(f"Error importing profile package: {e}")
        return jsonify({"success": False, "message": f"خطأ أثناء استيراد ملف JSON: {str(e)}"})


@app.route("/api/profiles/<profile_id>/details", methods=["GET", "POST"])
def profile_details(profile_id):
    metadata = adspower_client._load_profiles_metadata()
    meta = metadata.get(profile_id, {})

    if request.method == "POST":
        data = request.get_json() or {}
        if "name" in data and data["name"].strip():
            meta["name"] = data["name"].strip()
        if "group_name" in data:
            meta["group_name"] = data["group_name"].strip()

        # Update platform usernames
        if "instagram_username" in data:
            meta["instagram_username"] = data["instagram_username"].strip()
        if "facebook_username" in data:
            meta["facebook_username"] = data["facebook_username"].strip()
        if "twitter_username" in data:
            meta["twitter_username"] = data["twitter_username"].strip()

        # Update per-platform automation configs
        if "platforms" in data and isinstance(data["platforms"], dict):
            current_platforms = meta.get("platforms", {})
            for plat_name, plat_cfg in data["platforms"].items():
                if isinstance(plat_cfg, dict):
                    if plat_name not in current_platforms:
                        current_platforms[plat_name] = {}
                    current_platforms[plat_name].update(plat_cfg)
            meta["platforms"] = current_platforms

        metadata[profile_id] = meta
        adspower_client._save_profiles_metadata(metadata)
        return jsonify({"success": True, "message": "تم حفظ تفاصيل وإعدادات الملف بنجاح", "details": meta})

    # GET method
    is_active = adspower_client.is_browser_active(profile_id)
    all_proxies = proxy_manager.load_proxies()
    active_platforms = automation_hub.get_profile_active_platforms(profile_id)

    plat_configs = meta.get("platforms", {})
    has_proxy = bool(meta.get("proxy_host") and meta.get("proxy_soft") != "no_proxy")
    current_proxy = {
        "has_proxy": has_proxy,
        "proxy_soft": meta.get("proxy_soft", "no_proxy"),
        "proxy_type": meta.get("proxy_type", "http"),
        "proxy_host": meta.get("proxy_host", ""),
        "proxy_port": meta.get("proxy_port", ""),
        "proxy_user": meta.get("proxy_user", ""),
        "country": meta.get("country", "")
    }

    cookies_info = adspower_client.get_profile_cookies(profile_id)
    cookies_count = cookies_info.get("count", 0)
    fp_info = adspower_client.get_profile_fingerprint(profile_id)

    # Load twitter dm history count for this profile
    clean_id = "".join(c for c in str(profile_id) if c.isalnum() or c in ("-", "_"))
    history_file = os.path.join(os.path.dirname(__file__), f"twitter_dm_history_{clean_id}.json")
    tw_history_count = 0
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as hf:
                hdata = json.load(hf)
                tw_history_count = len(hdata) if isinstance(hdata, dict) else 0
        except Exception:
            pass

    # Load facebook comment history count for this profile
    fb_history_file = os.path.join(os.path.dirname(__file__), f"facebook_history_{clean_id}.json")
    fb_history_count = 0
    if os.path.exists(fb_history_file):
        try:
            with open(fb_history_file, "r", encoding="utf-8") as fbf:
                fb_data = json.load(fbf)
                fb_history_count = len(fb_data) if isinstance(fb_data, dict) else 0
        except Exception:
            pass

    details = {
        "profile_id": profile_id,
        "name": meta.get("name") or f"Profile_{profile_id}",
        "group_name": meta.get("group_name", "الافتراضية"),
        "serial_number": meta.get("serial_number", profile_id),
        "is_active": is_active,
        "cookies_count": cookies_count,
        "fingerprint": fp_info,
        "proxy": current_proxy,
        "available_proxies": all_proxies,
        "usernames": {
            "instagram": meta.get("instagram_username") or plat_configs.get("instagram", {}).get("username", ""),
            "facebook": meta.get("facebook_username") or plat_configs.get("facebook", {}).get("username", meta.get("page_name", "DheyaStore")),
            "twitter": meta.get("twitter_username") or plat_configs.get("twitter", {}).get("username", "")
        },
        "platforms": {
            "instagram": {
                "post_url": plat_configs.get("instagram", {}).get("post_url", config.get("post_url", "")),
                "public_reply_template": plat_configs.get("instagram", {}).get("public_reply_template", "Appreciate your thoughts on this! Check your DMs 💬"),
                "private_dm_template": plat_configs.get("instagram", {}).get("private_dm_template", "Hey! Reached out regarding your comment on the post. Hope you're having a great day! 😊"),
                "check_interval_seconds": int(plat_configs.get("instagram", {}).get("check_interval_seconds", 30)),
                "status": active_platforms.get("instagram", {"is_running": False, "status": "متوقف"})
            },
            "facebook": {
                "post_url": plat_configs.get("facebook", {}).get("post_url", config.get("post_url", "")),
                "public_reply_template": plat_configs.get("facebook", {}).get("public_reply_template", "Hello {name}! Thanks for reaching out. Please check your inbox 📩"),
                "private_dm_template": plat_configs.get("facebook", {}).get("private_dm_template", "Hi {name}, thank you for your comment! How can we assist you with our store today?"),
                "page_name": meta.get("facebook_username") or plat_configs.get("facebook", {}).get("page_name", "DheyaStore"),
                "action_type": plat_configs.get("facebook", {}).get("action_type", "reply_and_dm"),
                "check_interval_seconds": int(plat_configs.get("facebook", {}).get("check_interval_seconds", 45)),
                "cooldown_hours": float(plat_configs.get("facebook", {}).get("cooldown_hours") if plat_configs.get("facebook", {}).get("cooldown_hours") is not None else 24.0),
                "max_replies_per_hour": int(plat_configs.get("facebook", {}).get("max_replies_per_hour", 30)),
                "history_count": fb_history_count,
                "status": active_platforms.get("facebook", {"is_running": False, "status": "متوقف"})
            },
            "twitter": {
                "post_url": plat_configs.get("twitter", {}).get("post_url", "https://x.com/i/chat"),
                "dm_template": plat_configs.get("twitter", {}).get("dm_template") or plat_configs.get("twitter", {}).get("private_dm_template") or plat_configs.get("twitter", {}).get("public_reply_template") or "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨",
                "public_reply_template": plat_configs.get("twitter", {}).get("dm_template") or plat_configs.get("twitter", {}).get("private_dm_template") or plat_configs.get("twitter", {}).get("public_reply_template") or "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨",
                "private_dm_template": plat_configs.get("twitter", {}).get("private_dm_template") or plat_configs.get("twitter", {}).get("dm_template") or "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨",
                "check_interval_seconds": int(plat_configs.get("twitter", {}).get("check_interval_seconds", 12)),
                "cooldown_hours": float(plat_configs.get("twitter", {}).get("cooldown_hours") if plat_configs.get("twitter", {}).get("cooldown_hours") is not None else 24.0),
                "check_requests": bool(plat_configs.get("twitter", {}).get("check_requests", True)),
                "max_replies_per_hour": int(plat_configs.get("twitter", {}).get("max_replies_per_hour", 25)),
                "batch_limit": int(plat_configs.get("twitter", {}).get("batch_limit", 6)),
                "skip_if_last_outgoing": bool(plat_configs.get("twitter", {}).get("skip_if_last_outgoing", True)),
                "history_count": tw_history_count,
                "status": active_platforms.get("twitter", {"is_running": False, "status": "متوقف"})
            }
        }
    }
    return jsonify({"success": True, "details": details})


@app.route("/api/profiles/<profile_id>/twitter/clear-history", methods=["POST"])
def clear_twitter_profile_history(profile_id):
    clean_id = "".join(c for c in str(profile_id) if c.isalnum() or c in ("-", "_"))
    history_file = os.path.join(os.path.dirname(__file__), f"twitter_dm_history_{clean_id}.json")
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return jsonify({"success": True, "message": "تم تصفير سجل الذاكرة وفترة الانتظار (Cooldown) لهذا الملف بنجاح! 🧹"})
    except Exception as e:
        return jsonify({"success": False, "message": f"تعذر تصفير السجل: {e}"})


@app.route("/api/profiles/<profile_id>/facebook/clear-history", methods=["POST"])
def clear_facebook_profile_history(profile_id):
    clean_id = "".join(c for c in str(profile_id) if c.isalnum() or c in ("-", "_"))
    history_file = os.path.join(os.path.dirname(__file__), f"facebook_history_{clean_id}.json")
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return jsonify({"success": True, "message": "تم تصفير سجل تعليقات فيسبوك وفترة الانتظار (Cooldown) لهذا الملف بنجاح! 🧹"})
    except Exception as e:
        return jsonify({"success": False, "message": f"تعذر تصفير السجل: {e}"})


@app.route("/api/profiles/<profile_id>/automation/start", methods=["POST"])
def start_single_profile_automation(profile_id):
    data = request.get_json() or {}
    platform = (data.get("platform") or "instagram").lower()

    metadata = adspower_client._load_profiles_metadata()
    meta = metadata.get(profile_id, {})
    profile_name = meta.get("name", profile_id)

    plat_configs = meta.get("platforms", {})
    if platform not in plat_configs:
        plat_configs[platform] = {}

    for k in [
        "post_url", "public_reply_template", "private_dm_template", "dm_template", "action_type",
        "page_name", "check_interval_seconds", "cooldown_hours",
        "check_requests", "max_replies_per_hour", "batch_limit", "skip_if_last_outgoing"
    ]:
        if k in data and data[k] is not None:
            plat_configs[platform][k] = data[k]

    meta["platforms"] = plat_configs
    metadata[profile_id] = meta
    adspower_client._save_profiles_metadata(metadata)

    config_params = {
        "post_url": data.get("post_url") or plat_configs.get(platform, {}).get("post_url") or config.get("post_url"),
        "page_name": data.get("page_name") or meta.get("facebook_username") or "DheyaStore",
        "public_reply_template": data.get("public_reply_template") or plat_configs.get(platform, {}).get("public_reply_template"),
        "private_dm_template": data.get("private_dm_template") or data.get("dm_template") or plat_configs.get(platform, {}).get("private_dm_template") or plat_configs.get(platform, {}).get("dm_template"),
        "check_interval_seconds": int(data.get("check_interval_seconds") or plat_configs.get(platform, {}).get("check_interval_seconds") or 35),
        "cooldown_hours": float(data.get("cooldown_hours") if data.get("cooldown_hours") is not None else (plat_configs.get(platform, {}).get("cooldown_hours") if plat_configs.get(platform, {}).get("cooldown_hours") is not None else 24.0)),
        "check_requests": data.get("check_requests", plat_configs.get(platform, {}).get("check_requests", True)),
        "max_replies_per_hour": int(data.get("max_replies_per_hour") or plat_configs.get(platform, {}).get("max_replies_per_hour") or 25),
        "batch_limit": int(data.get("batch_limit") or plat_configs.get(platform, {}).get("batch_limit") or 6),
        "skip_if_last_outgoing": data.get("skip_if_last_outgoing", plat_configs.get(platform, {}).get("skip_if_last_outgoing", True)),
        "action_type": data.get("action_type", "reply_and_dm")
    }

    if platform in ("twitter", "x"):
        if not config_params["post_url"] or "x.com" not in config_params["post_url"]:
            config_params["post_url"] = "https://x.com/i/chat"
        if not config_params.get("private_dm_template"):
            config_params["private_dm_template"] = config_params.get("public_reply_template") or "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨"

    if not config_params["post_url"]:
        return jsonify({"success": False, "message": f"يرجى إدخال رابط المنشور المستهدف لأتمتة {platform.upper()}"})

    res = automation_hub.start_profile_automation(profile_id, profile_name, platform, config_params)
    return jsonify(res)


@app.route("/api/profiles/<profile_id>/automation/stop", methods=["POST"])
def stop_single_profile_automation(profile_id):
    data = request.get_json() or {}
    platform = data.get("platform")
    res = automation_hub.stop_profile_automation(profile_id, platform)
    return jsonify(res)


# -------------------------- BULK PROFILE ACTIONS --------------------------
@app.route("/api/profiles/bulk-start", methods=["POST"])
def bulk_start_profiles():
    data = request.get_json() or {}
    user_ids = data.get("user_ids", [])
    if not user_ids:
        return jsonify({"success": False, "message": "لم يتم تحديد أي ملفات"})
    res = adspower_client.bulk_start_browsers(user_ids)
    return jsonify(res)


@app.route("/api/profiles/bulk-stop", methods=["POST"])
def bulk_stop_profiles():
    data = request.get_json() or {}
    user_ids = data.get("user_ids", [])
    if not user_ids:
        return jsonify({"success": False, "message": "لم يتم تحديد أي ملفات"})
    res = adspower_client.bulk_stop_browsers(user_ids)
    return jsonify(res)


@app.route("/api/profiles/bulk-proxy", methods=["POST"])
def bulk_assign_proxy():
    data = request.get_json() or {}
    user_ids = data.get("user_ids", [])
    proxy_id = data.get("proxy_id")

    if not user_ids or not proxy_id:
        return jsonify({"success": False, "message": "يرجى تحديد الملفات والبروكسي"})

    proxies = proxy_manager.load_proxies()
    proxy = next((p for p in proxies if p["id"] == proxy_id), None)
    if not proxy:
        return jsonify({"success": False, "message": "البروكسي المحدد غير موجود"})

    res = adspower_client.bulk_assign_proxy(user_ids, proxy)
    return jsonify(res)


@app.route("/api/profiles/bulk-export", methods=["GET", "POST"])
def bulk_export_profiles_endpoint():
    try:
        user_ids = None
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            user_ids = data.get("user_ids")
        else:
            ids_param = request.args.get("user_ids", "").strip()
            if ids_param:
                user_ids = [x.strip() for x in ids_param.split(",") if x.strip()]

        download = request.args.get("download", "true").lower() == "true"
        pkg = adspower_client.export_bulk_profiles(user_ids)

        if download:
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            count = pkg.get("total_profiles", 0)
            ascii_filename = f"adspower_backup_{count}_profiles_{now_str}.json"
            raw_filename = f"نسخة_احتياطية_شاملة_{count}_ملفات_{now_str}.json"
            encoded_filename = urllib.parse.quote(raw_filename)

            json_str = json.dumps(pkg, indent=2, ensure_ascii=False)
            return Response(
                json_str,
                mimetype="application/json; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"
                }
            )
        return jsonify({"success": True, "package": pkg})
    except Exception as e:
        logger.error(f"Error bulk exporting profiles: {e}")
        return jsonify({"success": False, "message": f"حدث خطأ أثناء تصدير النسخة الاحتياطية: {str(e)}"})


@app.route("/api/profiles/bulk-unlink-proxy", methods=["POST"])
def bulk_unlink_proxy_endpoint():
    try:
        data = request.get_json() or {}
        user_ids = data.get("user_ids", [])
        if not user_ids:
            return jsonify({"success": False, "message": "لم يتم تحديد أي ملفات"})
        res = adspower_client.bulk_unlink_proxies(user_ids)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Error bulk unlinking proxies: {e}")
        return jsonify({"success": False, "message": f"خطأ أثناء فك ارتباط البروكسيات: {str(e)}"})


@app.route("/api/profiles/bulk-group", methods=["POST"])
def bulk_group_endpoint():
    try:
        data = request.get_json() or {}
        user_ids = data.get("user_ids", [])
        group_name = data.get("group_name", "").strip()
        if not user_ids:
            return jsonify({"success": False, "message": "لم يتم تحديد أي ملفات"})
        if not group_name:
            return jsonify({"success": False, "message": "يرجى تحديد اسم المجموعة"})
        res = adspower_client.bulk_change_group(user_ids, group_name)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Error bulk changing group: {e}")
        return jsonify({"success": False, "message": f"خطأ أثناء نقل الملفات إلى المجموعة: {str(e)}"})


# -------------------------- PROXY MANAGEMENT --------------------------
@app.route("/api/proxies", methods=["GET", "POST"])
def handle_proxies():
    if request.method == "GET":
        proxies = proxy_manager.load_proxies()
        return jsonify({"success": True, "proxies": proxies})

    data = request.get_json() or {}
    res = proxy_manager.add_proxy(data)
    return jsonify(res)


@app.route("/api/proxies/sync-adspower", methods=["POST"])
def sync_proxies_from_adspower():
    res = proxy_manager.sync_from_adspower(adspower_client)
    return jsonify(res)


@app.route("/api/proxies/bulk", methods=["POST"])
def bulk_proxies():
    data = request.get_json() or {}
    text = data.get("text", "")
    default_type = data.get("type", "http")
    res = proxy_manager.bulk_add_proxies(text, default_type)
    return jsonify(res)


@app.route("/api/proxies/<proxy_id>", methods=["DELETE"])
def delete_proxy(proxy_id):
    res = proxy_manager.delete_proxy(proxy_id)
    return jsonify(res)


@app.route("/api/proxies/<proxy_id>/test", methods=["POST"])
def test_proxy(proxy_id):
    res = proxy_manager.test_proxy(proxy_id)
    return jsonify(res)


@app.route("/api/proxies/<proxy_id>/assign", methods=["POST"])
def assign_proxy(proxy_id):
    data = request.get_json() or {}
    profile_id = data.get("profile_id")
    profile_name = data.get("profile_name", profile_id)

    if not profile_id:
        return jsonify({"success": False, "message": "يجب تحديد معرف الملف (Profile ID)"})

    res = proxy_manager.assign_to_profile(proxy_id, profile_id, profile_name, adspower_client)
    return jsonify(res)


@app.route("/api/proxies/<proxy_id>/unassign", methods=["POST"])
def unassign_proxy(proxy_id):
    res = proxy_manager.unassign_from_profile(proxy_id, adspower_client)
    return jsonify(res)


# -------------------------- MULTI-PLATFORM AUTOMATION --------------------------
@app.route("/api/automation/status", methods=["GET"])
def automation_status():
    return jsonify(automation_hub.get_status())


@app.route("/api/automation/logs", methods=["GET"])
def automation_logs():
    last_id = int(request.args.get("last_id", 0))
    filter_profile = request.args.get("profile_id", "")
    filter_platform = request.args.get("platform", "")

    return jsonify({
        "success": True,
        "logs": automation_hub.get_logs(last_id, filter_profile, filter_platform)
    })


@app.route("/api/automation/clear-logs", methods=["POST"])
def automation_clear_logs():
    automation_hub.clear_logs()
    return jsonify({"success": True, "message": "تم مسح السجلات"})


@app.route("/api/automation/bulk-apply-config", methods=["POST"])
def automation_bulk_apply_config():
    try:
        data = request.get_json() or {}
        platform = (data.get("platform") or "").lower().strip()
        profile_ids = data.get("profile_ids") or []
        cfg = data.get("config") or {}

        if not platform or platform not in ("facebook", "instagram", "twitter", "x", "tiktok"):
            return jsonify({"success": False, "message": "يرجى تحديد منصة صالحة"})

        if not profile_ids:
            return jsonify({"success": False, "message": "لم يتم تحديد أي ملفات للتطبيق عليها"})

        metadata = adspower_client._load_profiles_metadata()
        updated_count = 0

        for pid in profile_ids:
            pid = str(pid).strip()
            if not pid:
                continue
            if pid not in metadata:
                metadata[pid] = {
                    "name": f"ملف AdsPower ({pid})",
                    "group_name": "الافتراضية",
                    "platforms": {}
                }
            if "platforms" not in metadata[pid]:
                metadata[pid]["platforms"] = {}

            plat_entry = metadata[pid]["platforms"].get(platform, {})

            if "post_url" in cfg:
                plat_entry["post_url"] = str(cfg["post_url"]).strip()
            if "page_name" in cfg:
                plat_entry["page_name"] = str(cfg["page_name"]).strip()
                if platform == "facebook":
                    metadata[pid]["facebook_username"] = str(cfg["page_name"]).strip()
            if "public_reply_template" in cfg:
                plat_entry["public_reply_template"] = str(cfg["public_reply_template"])
            if "private_dm_template" in cfg or "dm_template" in cfg:
                val = str(cfg.get("private_dm_template") if "private_dm_template" in cfg else cfg.get("dm_template"))
                plat_entry["private_dm_template"] = val
                plat_entry["dm_template"] = val
            if "action_type" in cfg:
                plat_entry["action_type"] = str(cfg["action_type"]).strip()
            if "max_replies_per_hour" in cfg:
                plat_entry["max_replies_per_hour"] = int(cfg["max_replies_per_hour"])
            if "cooldown_hours" in cfg:
                plat_entry["cooldown_hours"] = float(cfg["cooldown_hours"])
            if "check_interval_seconds" in cfg:
                plat_entry["check_interval_seconds"] = int(cfg["check_interval_seconds"])

            metadata[pid]["platforms"][platform] = plat_entry
            updated_count += 1

        adspower_client._save_profiles_metadata(metadata)

        platform_names = {
            "facebook": "فيسبوك",
            "instagram": "إنستغرام",
            "twitter": "X / تويتر",
            "x": "X / تويتر",
            "tiktok": "تيك توك"
        }
        plat_disp = platform_names.get(platform, platform.upper())

        return jsonify({
            "success": True,
            "count": updated_count,
            "message": f"تم بنجاح حفظ وتطبيق إعدادات أتمتة [{plat_disp}] على {updated_count} ملف!"
        })
    except Exception as e:
        logger.error(f"Error bulk applying automation config: {e}")
        return jsonify({"success": False, "message": f"خطأ أثناء حفظ وتطبيق الإعدادات: {str(e)}"})


@app.route("/api/automation/start", methods=["POST"])
def automation_start():
    data = request.get_json() or {}
    platform = (data.get("platform") or "facebook").lower()
    use_saved_config = bool(data.get("use_saved_config", False))

    # Supports both multi-profile list and single profile
    profiles_input = data.get("profiles") or []
    if not profiles_input and data.get("profile_id"):
        profiles_input = [{"id": data.get("profile_id"), "name": data.get("profile_name", data.get("profile_id"))}]

    if not profiles_input:
        return jsonify({"success": False, "message": "يرجى تحديد ملف أو أكثر لتشغيل الأتمتة"})

    metadata = adspower_client._load_profiles_metadata()

    # Shared default config fallback
    shared_config = {
        "post_url": data.get("post_url") or config.get("post_url"),
        "page_name": data.get("page_name") or config.get("page_name", "DheyaStore"),
        "public_reply_template": data.get("public_reply_template") or config.get("public_reply_template"),
        "private_dm_template": data.get("private_dm_template") or data.get("dm_template") or config.get("private_dm_template"),
        "check_interval_seconds": int(data.get("check_interval_seconds") or 35),
        "cooldown_hours": float(data.get("cooldown_hours") if data.get("cooldown_hours") is not None else 24.0),
        "action_type": data.get("action_type", "reply_and_dm")
    }

    if platform in ("twitter", "x"):
        if not shared_config["post_url"] or "x.com" not in shared_config["post_url"]:
            shared_config["post_url"] = "https://x.com/i/chat"
        if not shared_config.get("private_dm_template"):
            shared_config["private_dm_template"] = shared_config.get("public_reply_template") or "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨"

    # Attach profile-specific configuration if use_saved_config is True
    for p in profiles_input:
        pid = p["id"]
        meta = metadata.get(pid, {})
        plat_cfg = meta.get("platforms", {}).get(platform, {})

        if use_saved_config:
            p_conf = {
                "post_url": plat_cfg.get("post_url") or ("https://x.com/i/chat" if platform in ("twitter", "x") else shared_config["post_url"]),
                "page_name": meta.get("facebook_username") or plat_cfg.get("page_name") or "DheyaStore",
                "public_reply_template": plat_cfg.get("public_reply_template") or plat_cfg.get("dm_template") or shared_config["public_reply_template"],
                "private_dm_template": plat_cfg.get("private_dm_template") or plat_cfg.get("dm_template") or shared_config["private_dm_template"],
                "check_interval_seconds": int(plat_cfg.get("check_interval_seconds") or shared_config["check_interval_seconds"]),
                "cooldown_hours": float(plat_cfg.get("cooldown_hours") if plat_cfg.get("cooldown_hours") is not None else shared_config["cooldown_hours"]),
                "action_type": plat_cfg.get("action_type") or shared_config.get("action_type", "reply_and_dm"),
                "max_replies_per_hour": int(plat_cfg.get("max_replies_per_hour") or shared_config.get("max_replies_per_hour", 30))
            }
            if platform in ("twitter", "x"):
                if not p_conf["post_url"] or "x.com" not in p_conf["post_url"]:
                    p_conf["post_url"] = "https://x.com/i/chat"
                if not p_conf.get("private_dm_template"):
                    p_conf["private_dm_template"] = p_conf.get("public_reply_template") or "مرحباً بك! شكراً لتواصلك معنا، نسعد بخدمتك دائماً 💬✨"

            p["config"] = p_conf
        else:
            p["config"] = shared_config

    if not use_saved_config and not shared_config["post_url"] and platform not in ("twitter", "x"):
        return jsonify({"success": False, "message": "يرجى إدخال الرابط المستهدف للأتمتة أو اختيار نمط الإعدادات المحفوظة"})

    res = automation_hub.start_bulk(profiles_input, platform, shared_config)
    return jsonify(res)


@app.route("/api/automation/stop", methods=["POST"])
def automation_stop():
    data = request.get_json() or {}
    profile_id = data.get("profile_id")
    platform = data.get("platform")
    if profile_id:
        res = automation_hub.stop_profile_automation(profile_id, platform)
    else:
        res = automation_hub.stop_all()
    return jsonify(res)


@app.route("/api/automation/debug/facebook", methods=["GET", "POST"])
def automation_debug_facebook():
    try:
        workers = automation_hub.runner_hub.workers
        fb_worker = None
        for k, w in workers.items():
            if "facebook" in k and w.driver:
                fb_worker = w
                break
        if not fb_worker or not fb_worker.driver:
            return jsonify({"success": False, "message": "No active Facebook worker with valid driver found."})

        from automations.facebook import (
            OPEN_COMMENT_FILTER_DROPDOWN_JS,
            SELECT_NEWEST_MENUITEM_JS,
            EXTRACT_COMMENTS_JS
        )

        driver = fb_worker.driver
        title = driver.title
        url = driver.current_url

        # 1. Extract comments currently seen
        comments = driver.execute_script(EXTRACT_COMMENTS_JS, fb_worker.config.get("page_name", "DheyaStore"))

        # 2. Inspect buttons on page related to filter
        filter_buttons = driver.execute_script("""
            const buttons = Array.from(document.querySelectorAll('div[role="button"], span[role="button"], a[role="button"], button'));
            return buttons.map(b => {
                const txt = (b.innerText || '').trim();
                const aria = (b.getAttribute('aria-label') || '').trim();
                return {
                    tag: b.tagName,
                    role: b.getAttribute('role'),
                    text: txt.slice(0, 80),
                    aria: aria.slice(0, 80),
                    visible: !!(b.offsetWidth || b.offsetHeight)
                };
            }).filter(x => {
                const c = (x.text + ' ' + x.aria).toLowerCase();
                return c.includes('newest') || c.includes('الأحدث') || c.includes('relevant') || c.includes('الأبرز') ||
                       c.includes('all comments') || c.includes('كل التعليقات') || c.includes('comment') || c.includes('تعليق');
            });
        """)

        test_click = request.args.get("click") == "1"
        click_res = None
        sel_res = None
        if test_click:
            click_res = driver.execute_script(OPEN_COMMENT_FILTER_DROPDOWN_JS)
            import time
            time.sleep(1.0)
            sel_res = driver.execute_script(SELECT_NEWEST_MENUITEM_JS)

        return jsonify({
            "success": True,
            "title": title,
            "url": url,
            "comments_count": len(comments) if isinstance(comments, list) else 0,
            "comments": comments,
            "filter_buttons": filter_buttons,
            "click_res": click_res,
            "sel_res": sel_res
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    port = int(config.get("port", 5000))
    print(f"================================================================")
    print(f"  لوحة تحكم AdsPower وأتمتة المنصات المتعددة تعمل على:")
    print(f"  http://127.0.0.1:{port}")
    print(f"================================================================")
    app.run(host="0.0.0.0", port=port, debug=False)
