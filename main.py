import requests
import pandas as pd
import json
import filelock
from datetime import datetime
import pytz
import os

# --- READ TELEGRAM BOT TOKEN AND CHAT ID FROM ENVIRONMENT VARIABLES ---
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
# ---------------------------------------------------------------------

GITHUB_RAW_URL = "https://raw.githubusercontent.com/KHwang9883/MobileModels-csv/main/models.csv"
GOOGLE_DEVICES_URL = "https://storage.googleapis.com/play_public/supported_devices.html"

PROGRESS_FILE = "device_progress.json"
LOCK_FILE = "device_checker.lock"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=data, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def get_github_devices():
    try:
        df = pd.read_csv(GITHUB_RAW_URL)
        return set(df['Model'].astype(str).str.strip())
    except Exception as e:
        print(f"Error fetching GitHub devices: {e}")
        return set()

def get_google_devices():
    try:
        df = pd.read_html(GOOGLE_DEVICES_URL, header=0)[0]
        return set(df['Model'].astype(str).str.strip())
    except Exception as e:
        print(f"Error fetching Google devices: {e}")
        return set()

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {"github": [], "google": [], "last_check": ""}
    with open(PROGRESS_FILE, "r") as f:
        return json.load(f)

def save_progress(github_list, google_list):
    data = {
        "github": list(github_list),
        "google": list(google_list),
        "last_check": datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def main():
    lock = filelock.FileLock(LOCK_FILE)
    try:
        with lock.acquire(timeout=30):
            progress = load_progress()
            prev_github = set(progress.get("github", []))
            prev_google = set(progress.get("google", []))

            github_devices = get_github_devices()
            google_devices = get_google_devices()

            new_github = github_devices - prev_github
            new_google = google_devices - prev_google

            messages = []
            if new_github:
                messages.append(f"🆕 <b>New devices in GitHub list:</b>\n" + "\n".join(sorted(new_github)))
            if new_google:
                messages.append(f"🆕 <b>New devices in Google list:</b>\n" + "\n".join(sorted(new_google)))

            if messages:
                for msg in messages:
                    send_telegram_message(msg[:4096])  # Telegram max message size
            else:
                send_telegram_message("✅ No new devices found in either list today.")

            save_progress(github_devices, google_devices)
    except filelock.Timeout:
        print("Another process is running. Exiting.")
        send_telegram_message("❌ Another check is currently running. Please wait.")

if __name__ == "__main__":
    main()
