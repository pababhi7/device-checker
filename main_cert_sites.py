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

SMARTPHONE_BRANDS = [
    "samsung", "apple", "xiaomi", "redmi", "poco", "nothing", "oneplus", "oppo", "vivo", "realme", "iqoo", "huawei", "honor",
    "google", "sony", "motorola", "nokia", "asus", "lenovo", "infinix", "tecno", "itel", "meizu", "zte", "sharp", "doogee",
    "ulefone", "cat", "blu", "cubot", "blackview", "leeco", "tcl", "alcatel", "coolpad", "gionee", "vsmart", "wiko", "hisense",
    "panasonic", "kyocera", "energizer"
]

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
        return {"nbtc": [], "qi_wpc": [], "audio_jp": [], "last_check": "", "initialized": False}
    try:
        with open(PROGRESS_FILE, "r") as f:
            data = json.load(f)
            print(f"📝 Progress loaded - last check: {data.get('last_check', 'Unknown')}")
            if "initialized" not in data:
                data["initialized"] = False
            return data
    except Exception as e:
        print(f"✗ Error loading progress: {e}")
        return {"nbtc": [], "qi_wpc": [], "audio_jp": [], "last_check": "", "initialized": False}

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
    first_run = not progress.get("initialized", False)

    # --- NBTC ---
    nbtc_ids = []
    nbtc_new_devices = []
    nbtc_ok = False
    try:
        nbtc_url = "https://hub.nbtc.go.th/api/certification"
        resp = requests.get(nbtc_url, timeout=20)
        data = resp.json()
        for item in data:
            device_type = item.get("device_type", "").lower()
            device_id = str(item.get("id"))
            device_name = item.get("model_code", "")
            if any(x in device_type for x in ["smartphone", "smart phone", "phone", "mobile", "mobile phone", "mobile device"]):
                nbtc_ids.append(device_id)
                if not first_run and device_id not in progress["nbtc"]:
                    nbtc_new_devices.append((device_id, device_name, device_type))
        nbtc_ok = True
    except Exception as e:
        print(f"NBTC error: {e}")
        nbtc_ok = False

    # --- Qi WPC (brand name substring match, case-insensitive) ---
    qi_ids = []
    qi_new_devices = []
    qi_ok = False
    try:
        qi_url = "https://jpsapi.wirelesspowerconsortium.com/products/qi"
        resp = requests.get(qi_url, timeout=20)
        data = resp.json()
        for item in data.get("products", []):
            device_id = str(item.get("id"))
            brand = item.get("brandName", "").lower()
            model = item.get("name", "")
            if any(b in brand for b in SMARTPHONE_BRANDS):
                qi_ids.append(device_id)
                if not first_run and device_id not in progress["qi_wpc"]:
                    qi_new_devices.append((device_id, brand, model))
        qi_ok = True
    except Exception as e:
        print(f"Qi WPC error: {e}")
        qi_ok = False

    # --- Audio JP ---
    audio_jp_ids = []
    audio_jp_new_devices = []
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
            device_name = device_id
            if any(x in device_type for x in ["smartphone", "smart phone", "phone", "mobile", "mobile phone", "mobile device"]):
                audio_jp_ids.append(device_id)
                if not first_run and device_id not in progress["audio_jp"]:
                    audio_jp_new_devices.append((device_id, device_name, device_type))
        audio_jp_ok = True
    except Exception as e:
        print(f"Audio JP error: {e}")
        audio_jp_ok = False

    # --- Per-device notifications for new devices (not on first run) ---
    if not first_run:
        for device_id, device_name, device_type in nbtc_new_devices:
            send_telegram_message(f"🆕 <b>NBTC</b> new device:\n<b>Name:</b> {device_name}\n<b>ID:</b> {device_id}\n<b>Type:</b> {device_type}\n<a href='https://hub.nbtc.go.th/certification'>NBTC Link</a>")

        for device_id, brand, model in qi_new_devices:
            send_telegram_message(f"🆕 <b>Qi WPC</b> new device:\n<b>Brand:</b> {brand}\n<b>Model:</b> {model}\n<b>ID:</b> {device_id}\n<a href='https://jpsapi.wirelesspowerconsortium.com/products/qi'>Qi WPC Link</a>")

        for device_id, device_name, device_type in audio_jp_new_devices:
            send_telegram_message(f"🆕 <b>Audio JP</b> new device:\n<b>Name:</b> {device_name}\n<b>ID:</b> {device_id}\n<b>Type:</b> {device_type}\n<a href='https://www.jas-audio.or.jp/english/hi-res-logo-en/use-situation-en'>Audio JP Link</a>")

    # --- Summary Report ---
    summary = (
        "✅ <b>Certification site check completed</b>\n"
        f"Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📊 <b>Current smartphone totals:</b>\n"
        f"• NBTC: {len(nbtc_ids)}\n"
        f"• Qi WPC: {len(qi_ids)}\n"
        f"• Audio JP: {len(audio_jp_ids)}\n\n"
        f"🆕 <b>New devices this run:</b>\n"
        f"• NBTC: {len(nbtc_new_devices)}\n"
        f"• Qi WPC: {len(qi_new_devices)}\n"
        f"• Audio JP: {len(audio_jp_new_devices)}"
    )
    if first_run:
        send_telegram_message(
            "🚨 <b>Baseline established!</b>\n"
            "All current devices are now tracked. You will receive notifications for new devices from the next run.\n\n" + summary
        )
    else:
        send_telegram_message(summary)

    # Save progress
    progress["nbtc"] = nbtc_ids
    progress["qi_wpc"] = qi_ids
    progress["audio_jp"] = audio_jp_ids
    progress["initialized"] = True
    save_progress(progress)
    print("✅ Script completed successfully")

if __name__ == "__main__":
    main()
