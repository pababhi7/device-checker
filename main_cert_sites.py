import requests
import json
import os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

try:
    BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
    print("✓ Telegram credentials loaded")
except KeyError as e:
    print(f"ERROR: Environment variable {e} not found!")
    exit(1)

PROGRESS_FILE = "cert_sites_progress.json"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code == 200:
            print("✓ Telegram message sent")
            return True
        else:
            print(f"✗ Telegram error: {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ Telegram error: {e}")
        return False

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        print("📝 No progress file found - first run")
        return {"nbtc": [], "qi_wpc": [], "audio_jp": [], "last_check": ""}
    try:
        with open(PROGRESS_FILE, "r") as f:
            data = json.load(f)
            print(f"📝 Progress loaded - last check: {data.get('last_check', 'Unknown')}")
            return data
    except Exception as e:
        print(f"✗ Error loading progress: {e}")
        return {"nbtc": [], "qi_wpc": [], "audio_jp": [], "last_check": ""}

def save_progress(progress):
    progress["last_check"] = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2)
        print("✓ Progress saved")
    except Exception as e:
        print(f"✗ Error saving progress: {e}")

def main():
    print("🚀 Cert Site Scraper Started")
    start_time = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    send_telegram_message(f"🔍 <b>Starting certification site check</b>\nTime: {start_time}")

    progress = load_progress()

    # --- NBTC ---
    nbtc_ids = []
    nbtc_ok = False
    try:
        nbtc_url = "https://hub.nbtc.go.th/api/certification"
        resp = requests.get(nbtc_url, timeout=20)
        data = resp.json()
        for item in data:
            device_type = item.get("device_type", "").lower()
            device_id = str(item.get("id"))
            if "smartphone" in device_type or "phone" in device_type or "mobile" in device_type:
                nbtc_ids.append(device_id)
        nbtc_ok = True
    except Exception as e:
        print(f"NBTC error: {e}")
        nbtc_ok = False

    # --- Qi WPC ---
    qi_ids = []
    qi_ok = False
    try:
        qi_url = "https://jpsapi.wirelesspowerconsortium.com/products/qi"
        resp = requests.get(qi_url, timeout=20)
        data = resp.json()
        for item in data.get("products", []):
            device_id = str(item.get("id"))
            device_type = item.get("category", "").lower()
            if "smartphone" in device_type or "phone" in device_type or "mobile" in device_type:
                qi_ids.append(device_id)
        qi_ok = True
    except Exception as e:
        print(f"Qi WPC error: {e}")
        qi_ok = False

    # --- Audio JP ---
    audio_jp_ids = []
    audio_jp_ok = False
    try:
        audio_jp_url = "https://www.jas-audio.or.jp/english/hi-res-logo-en/use-situation-en"
        resp = requests.get(audio_jp_url, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select("table#tablepress-1 tbody tr"):
            cols = row.find_all("td")
            if not cols or len(cols) < 5:
                continue
            device_type = cols[3].text.strip().lower()
            device_id = cols[2].text.strip()
            if "smartphone" in device_type or "phone" in device_type or "mobile" in device_type:
                audio_jp_ids.append(device_id)
        audio_jp_ok = True
    except Exception as e:
        print(f"Audio JP error: {e}")
        audio_jp_ok = False

    # --- Summary Report ---
    summary = (
        "✅ <b>Certification site check completed</b>\n"
        f"Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📊 <b>Current smartphone totals:</b>\n"
        f"• NBTC: {len(nbtc_ids)}\n"
        f"• Qi WPC: {len(qi_ids)}\n"
        f"• Audio JP: {len(audio_jp_ids)}"
    )

    # --- First run or full reset detection ---
    first_run = (progress["nbtc"] == [] and progress["qi_wpc"] == [] and progress["audio_jp"] == [])
    full_new = (
        set(nbtc_ids) != set(progress["nbtc"]) or
        set(qi_ids) != set(progress["qi_wpc"]) or
        set(audio_jp_ids) != set(progress["audio_jp"])
    )

    if first_run or full_new:
        send_telegram_message(
            "🚨 <b>Device list is new or has been reset!</b>\n"
            "All devices are now being tracked from scratch.\n\n" + summary
        )
    else:
        send_telegram_message(summary)

    # Save progress
    progress["nbtc"] = nbtc_ids
    progress["qi_wpc"] = qi_ids
    progress["audio_jp"] = audio_jp_ids
    save_progress(progress)
    print("✅ Script completed successfully")

if __name__ == "__main__":
    main()
