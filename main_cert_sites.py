#!/usr/bin/env python3
"""
Robust certification site scraper with change-detection and Telegram notifications.

Usage:
  python main_cert_sites.py           # normal run
  python main_cert_sites.py --simulate  # force simulate 'new devices' to test notifications
  python main_cert_sites.py --once      # run once (same as normal) kept for clarity
"""

import os
import json
import time
import tempfile
import hashlib
import argparse
import logging
from datetime import datetime
import pytz
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from filelock import FileLock, Timeout
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --- Configuration ---
PROGRESS_FILE = "cert_sites_progress.json"
PROGRESS_LOCK = PROGRESS_FILE + ".lock"
LOG_FILE = "cert_sites.log"
CHANGES_LOG = "changes.log"
TIMEZONE = "Asia/Kolkata"
SMARTPHONE_KEYWORDS = [
    "phone", "mobile", "smartphone", "smart phone", "mobile phone", "5g digital mobile phone"
]

# --- Telegram ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("certscraper")


# --- Utility helpers ---
def now_str():
    return datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


def safe_write_json(path, data):
    # atomic write
    fd, tmp = tempfile.mkstemp(prefix="tmp_", dir=".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def normalize_text(s):
    if not s:
        return ""
    return " ".join(str(s).strip().lower().split())


def fingerprint_from_fields(*fields):
    joined = "||".join(normalize_text(str(f) if f is not None else "") for f in fields)
    # stable short hash
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def fingerprint_from_json(obj):
    try:
        # deterministic representation
        text = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    except Exception:
        text = str(obj)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def requests_session_with_retries(total=3, backoff=1.0, status_forcelist=(429, 500, 502, 503, 504)):
    session = requests.Session()
    retries = Retry(total=total, backoff_factor=backoff, status_forcelist=status_forcelist, allowed_methods=False)
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "CertSitesScraper/1.0 (+https://example.com)"
    })
    return session


# --- Progress file handling with file lock ---
def load_progress():
    default = {"nbtc": [], "qi_wpc": [], "audio_jp": [], "last_check": "", "initialized": False}
    try:
        lock = FileLock(PROGRESS_LOCK, timeout=5)
        with lock:
            if not os.path.exists(PROGRESS_FILE):
                logger.info("No progress file found - creating baseline on first save.")
                return default
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # ensure keys exist
                for k in default:
                    if k not in data:
                        data[k] = default[k]
                return data
    except Timeout:
        logger.error("Timeout acquiring progress file lock. Proceeding without progress load (risk of duplicate notifications).")
        return default
    except Exception as e:
        logger.exception("Failed to load progress file, using default: %s", e)
        return default


def save_progress(progress):
    progress["last_check"] = now_str()
    try:
        lock = FileLock(PROGRESS_LOCK, timeout=5)
        with lock:
            safe_write_json(PROGRESS_FILE, progress)
            logger.info("Progress saved.")
    except Timeout:
        logger.error("Timeout acquiring progress file lock. Progress not saved.")
    except Exception:
        logger.exception("Failed to save progress.")


# --- Telegram sender ---
def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        logger.error("Telegram credentials are not set. Skipping send: %s", message[:60])
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        s = requests_session_with_retries(total=2, backoff=0.5)
        r = s.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            logger.info("Telegram message sent.")
            return True
        else:
            logger.warning("Telegram responded %s: %s", r.status_code, r.text[:200])
            return False
    except Exception as e:
        logger.exception("Telegram send failed: %s", e)
        return False


def append_changes_log(entry):
    try:
        with open(CHANGES_LOG, "a", encoding="utf-8") as f:
            f.write(f"{now_str()} {entry}\n")
    except Exception:
        logger.exception("Failed to write changes log.")


# --- Site-specific extractors (produce list of fingerprints + friendly info) ---
def fetch_nbtc(session):
    """
    Returns list of tuples (fingerprint, dict with info)
    """
    url = "https://hub.nbtc.go.th/api/certification"
    result = []
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        for item in data:
            # prefer stable fields if available:
            model_code = item.get("model_code") or item.get("model") or item.get("modelCode")
            device_type = item.get("device_type") or item.get("type") or ""
            manufacturer = item.get("brand") or item.get("manufacturer") or item.get("company")
            # fingerprint: prefer model_code + manufacturer + device_type
            if model_code:
                fp = fingerprint_from_fields(model_code, manufacturer, device_type)
            elif "id" in item:
                fp = fingerprint_from_fields(item.get("id"), device_type)
            else:
                fp = fingerprint_from_json(item)
            info = {"source": "NBTC", "model_code": model_code, "manufacturer": manufacturer, "device_type": device_type, "raw": item}
            # filter smartphone keywords - keep only mobile-like devices
            dtype_lower = normalize_text(device_type)
            if any(k in dtype_lower for k in SMARTPHONE_KEYWORDS) or model_code:
                result.append((fp, info))
        logger.info("NBTC: fetched %d records", len(result))
    except Exception as e:
        logger.exception("NBTC fetch error: %s", e)
    return result


def fetch_qi_wpc(session, use_playwright=False):
    """
    Returns list of tuples (fingerprint, dict with info)
    """
    result = []
    api_url = "https://jpsapi.wirelesspowerconsortium.com/products/qi"
    try:
        # API first
        r = session.get(api_url, timeout=20, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        for item in data.get("products", []):
            pid = item.get("id")
            name = item.get("name") or item.get("product_name")
            if pid:
                fp = fingerprint_from_fields(pid, name)
            else:
                fp = fingerprint_from_json(item)
            info = {"source": "Qi WPC", "id": pid, "name": name, "raw": item}
            result.append((fp, info))
        logger.info("Qi WPC (API): fetched %d products", len(result))
        return result
    except Exception as e:
        logger.warning("Qi WPC API failed: %s", e)
        if not use_playwright:
            # Playwright fallback if available
            logger.info("Attempting Playwright fallback for Qi WPC...")
        else:
            logger.info("Playwright fallback already requested.")

    # Playwright fallback
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            page.goto("https://www.wirelesspowerconsortium.com/products/qi.html", timeout=60000)
            # wait a bit for dynamic table to populate - adjust if necessary
            page.wait_for_timeout(8000)
            html = page.content()
            browser.close()
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("table#product_db tbody tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                pid = normalize_text(cols[1].text)
                name = normalize_text(cols[2].text)
                fp = fingerprint_from_fields(pid, name) if pid else fingerprint_from_fields(name)
                info = {"source": "Qi WPC", "id": pid, "name": name, "raw": {"row_html": str(row)[:800]}}
                result.append((fp, info))
        logger.info("Qi WPC (Playwright): fetched %d products", len(result))
    except PWTimeout as e:
        logger.exception("Playwright timeout for Qi WPC: %s", e)
    except Exception as e:
        logger.exception("Qi WPC Playwright fallback error: %s", e)

    return result


def fetch_audio_jp(session):
    result = []
    url = "https://www.jas-audio.or.jp/english/hi-res-logo-en/use-situation-en"
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.select_one("table#tablepress-1")
        if not table:
            logger.warning("Audio JP: expected table#tablepress-1 not found")
            return result
        for row in table.select("tbody tr"):
            cols = row.find_all("td")
            # index assumptions may change; we attempt to recover gracefully
            if len(cols) >= 4:
                device_id = normalize_text(cols[2].text)
                device_type = normalize_text(cols[3].text)
                name = device_id or normalize_text(cols[0].text or cols[1].text)
                fp = fingerprint_from_fields(name, device_type)
                info = {"source": "Audio JP", "id": device_id, "name": name, "device_type": device_type, "raw": [c.text for c in cols]}
                # keep if smartphone keywords in device_type OR some id/name exists
                if any(k in device_type for k in SMARTPHONE_KEYWORDS) or device_id or name:
                    result.append((fp, info))
        logger.info("Audio JP: fetched %d records", len(result))
    except Exception as e:
        logger.exception("Audio JP fetch error: %s", e)
    return result


# --- Runner that compares with progress and sends notifications ---
def run_once(simulate=False, force_notify=False):
    logger.info("=== Cert Sites Scraper run started (%s) ===", now_str())
    session = requests_session_with_retries(total=3, backoff=0.5)

    progress = load_progress()
    first_run = not progress.get("initialized", False)
    if simulate:
        logger.info("SIMULATE mode: clearing progress to force notifications for testing.")
        progress["nbtc"] = []
        progress["qi_wpc"] = []
        progress["audio_jp"] = []
        progress["initialized"] = True  # we simulate baseline existed previously but emptied to test

    # fetch each site
    nbtc_list = fetch_nbtc(session)
    qi_list = fetch_qi_wpc(session)
    audio_list = fetch_audio_jp(session)

    # helper to compare and produce new list
    def compare_and_notify(site_key, items, url_label=None):
        """
        items: list of tuples (fp, info)
        site_progress = progress[site_key] = list of fp strings
        returns list of new info dicts
        """
        existing = set(progress.get(site_key, []))
        current_fps = []
        new_infos = []
        for fp, info in items:
            current_fps.append(fp)
            if fp not in existing:
                # new device
                new_infos.append((fp, info))
        # notify if not first run or force_notify
        if (not first_run or force_notify) and new_infos:
            for fp, info in new_infos:
                # build friendly message
                if info["source"] == "NBTC":
                    model = info.get("model_code") or info["raw"].get("model_code") or ""
                    man = info.get("manufacturer") or ""
                    dtype = info.get("device_type") or ""
                    msg = (f"🆕 <b>NBTC</b> new device:\n"
                           f"<b>Model:</b> {model}\n<b>Manufacturer:</b> {man}\n<b>Type:</b> {dtype}\n"
                           f"<a href='https://hub.nbtc.go.th/certification'>NBTC Link</a>")
                elif info["source"] == "Qi WPC":
                    name = info.get("name") or info.get("raw", {}).get("name", "")
                    pid = info.get("id") or ""
                    msg = (f"🆕 <b>Qi WPC</b> new product:\n<b>Name:</b> {name}\n<b>ID:</b> {pid}\n"
                           f"<a href='https://www.wirelesspowerconsortium.com/products/qi.html'>Qi WPC Link</a>")
                else:  # Audio JP
                    name = info.get("name") or ""
                    dtype = info.get("device_type") or ""
                    msg = (f"🆕 <b>Audio JP</b> new device:\n<b>Name/ID:</b> {name}\n<b>Type:</b> {dtype}\n"
                           f"<a href='https://www.jas-audio.or.jp/english/hi-res-logo-en/use-situation-en'>Audio JP Link</a>")

                ok = send_telegram_message(msg)
                append_changes_log(f"{info['source']} NEW: {msg[:200].replace('\\n',' | ')}")
                logger.info("Notified new device for %s (sent=%s): %s", info["source"], ok, info)
        else:
            if first_run and not force_notify:
                logger.info("First run: baseline established for %s; skipping per-device notifications.", site_key)
        # update progress lists
        progress[site_key] = current_fps
        return len(current_fps), len(new_infos)

    # compare & notify
    nbtc_total, nbtc_new_count = compare_and_notify("nbtc", nbtc_list, url_label="NBTC")
    qi_total, qi_new_count = compare_and_notify("qi_wpc", qi_list, url_label="QiWPC")
    audio_total, audio_new_count = compare_and_notify("audio_jp", audio_list, url_label="AudioJP")

    # summary
    summary = (
        "✅ <b>Certification site check completed</b>\n"
        f"Time: {now_str()}\n\n"
        f"📊 <b>Current device totals:</b>\n"
        f"• NBTC: {nbtc_total}\n"
        f"• Qi WPC: {qi_total}\n"
        f"• Audio JP: {audio_total}\n\n"
        f"🆕 <b>New devices this run:</b>\n"
        f"• NBTC: {nbtc_new_count}\n"
        f"• Qi WPC: {qi_new_count}\n"
        f"• Audio JP: {audio_new_count}"
    )
    # send baseline or summary
    if first_run and not force_notify:
        send_telegram_message("🚨 <b>Baseline established!</b>\nAll current devices are tracked now; you will receive notifications for new items from subsequent runs.\n\n" + summary)
    else:
        send_telegram_message(summary)

    # Save progress (mark initialized)
    progress["initialized"] = True
    save_progress(progress)
    logger.info("=== Run finished ===")


# --- CLI ---
def main():
    parser = argparse.ArgumentParser(description="Cert Sites Scraper")
    parser.add_argument("--simulate", action="store_true", help="Simulate new devices by clearing progress (for testing).")
    parser.add_argument("--force-notify", action="store_true", help="Force notifications even on first run.")
    args = parser.parse_args()

    run_once(simulate=args.simulate, force_notify=args.force_notify)


if __name__ == "__main__":
    main()
