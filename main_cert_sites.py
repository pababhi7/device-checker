import requests
import json
import os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

# --- READ TELEGRAM BOT TOKEN AND CHAT ID FROM ENVIRONMENT VARIABLES ---
try:
    BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
    print("✓ Telegram credentials loaded")
except KeyError as e:
    print(f"ERROR: Environment variable {e} not found!")
    exit(1)
# ---------------------------------------------------------------------

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
    nbtc_new = []
    try:
        nbtc_progress = progress.get("nbtc", [])
        nbtc_url = "https://hub.nbtc.go.th/api/certification"
        nbtc_ok = False
        try:
            resp = requests.get(nbtc_url, timeout=20)
            data = resp.json()
            for item in data:
                device_type = item.get("device_type", "").lower()
                device_name = item.get("model_code", "")
                device_id = str(item.get("id"))
                if device_id not in nbtc_progress and (
                    "smartphone" in device_type or "phone" in device_type or "mobile" in device_type
                ):
                    nbtc_new.append((device_id, device_name, device_type))
            nbtc_ok = True
        except Exception as e:
            print(f"NBTC error: {e}")
            nbtc_ok = False

        if nbtc_ok:
            send_telegram_message(f"NBTC: Scraping successful. {len(nbtc_new)} new smartphones found.")
            for device_id, device_name, device_type in nbtc_new:
                send_telegram_message(f"NBTC: {device_name} (ID: {device_id})\nType: {device_type}\nhttps://hub.nbtc.go.th/certification")
                nbtc_progress.append(device_id)
        else:
            send_telegram_message("NBTC: Scraping failed.")
        progress["nbtc"] = nbtc_progress
    except Exception as e:
        send_telegram_message(f"NBTC: Scraping failed. Error: {e}")

    # --- Qi WPC ---
    qi_new = []
    try:
        qi_progress = progress.get("qi_wpc", [])
        qi_url = "https://jpsapi.wirelesspowerconsortium.com/products/qi"
        qi_ok = False
        try:
            resp = requests.get(qi_url, timeout=20)
            data = resp.json()
            for item in data.get("products", []):
                device_name = item.get("name", "")
                device_id = str(item.get("id"))
                device_type = item.get("category", "").lower()
                if device_id not in qi_progress and (
                    "smartphone" in device_type or "phone" in device_type or "mobile" in device_type
                ):
                    qi_new.append((device_id, device_name, device_type))
            qi_ok = True
        except Exception as e:
            print(f"Qi WPC error: {e}")
            qi_ok = False

        if qi_ok:
            send_telegram_message(f"Qi WPC: Scraping successful. {len(qi_new)} new smartphones found.")
            for device_id, device_name, device_type in qi_new:
                send_telegram_message(f"Qi WPC: {device_name} (ID: {device_id})\nType: {device_type}\n{qi_url}")
                qi_progress.append(device_id)
        else:
            send_telegram_message("Qi WPC: Scraping failed.")
        progress["qi_wpc"] = qi_progress
    except Exception as e:
        send_telegram_message(f"Qi WPC: Scraping failed. Error: {e}")

    # --- Audio JP ---
    audio_jp_new = []
    try:
        audio_jp_progress = progress.get("audio_jp", [])
        audio_jp_url = "https://www.jas-audio.or.jp/english/hi-res-logo-en/use-situation-en"
        audio_jp_ok = False
        try:
            resp = requests.get(audio_jp_url, timeout=20)
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table#tablepress-1 tbody tr"):
                cols = row.find_all("td")
                if not cols or len(cols) < 5:
                    continue
                device_type = cols[3].text.strip().lower()
                device_name = cols[2].text.strip()
                device_id = device_name
                if device_id not in audio_jp_progress and (
                    "smartphone" in device_type or "phone" in device_type or "mobile" in device_type
                ):
                    audio_jp_new.append((device_id, device_name, device_type))
            audio_jp_ok = True
        except Exception as e:
            print(f"Audio JP error: {e}")
            audio_jp_ok = False

        if audio_jp_ok:
            send_telegram_message(f"Audio JP: Scraping successful. {len(audio_jp_new)} new smartphones found.")
            for device_id, device_name, device_type in audio_jp_new:
                send_telegram_message(f"Audio JP: {device_name} (ID: {device_id})\nType: {device_type}\n{audio_jp_url}")
                audio_jp_progress.append(device_id)
        else:
            send_telegram_message("Audio JP: Scraping failed.")
        progress["audio_jp"] = audio_jp_progress
    except Exception as e:
        send_telegram_message(f"Audio JP: Scraping failed. Error: {e}")

    # --- Summary Report ---
    total_new = len(nbtc_new) + len(qi_new) + len(audio_jp_new)
    summary = (
        "✅ <b>Certification site check completed</b>\n"
        f"Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📱 <b>New smartphones found:</b>\n"
        f"• NBTC: {len(nbtc_new)}\n"
        f"• Qi WPC: {len(qi_new)}\n"
        f"• Audio JP: {len(audio_jp_new)}\n"
        f"• Total: {total_new}\n\n"
        f"📊 <b>Total tracked:</b>\n"
        f"• NBTC: {len(progress['nbtc'])}\n"
        f"• Qi WPC: {len(progress['qi_wpc'])}\n"
        f"• Audio JP: {len(progress['audio_jp'])}"
    )
    send_telegram_message(summary)

    save_progress(progress)
    print("✅ Script completed successfully")

if __name__ == "__main__":
    main()
