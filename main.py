import requests
import pandas as pd
import json
import filelock
from datetime import datetime
import pytz
import os
import time

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

def get_github_devices_df():
    try:
        df = pd.read_csv(GITHUB_RAW_URL)
        df = df.fillna("")
        return df
    except Exception as e:
        print(f"Error fetching GitHub devices: {e}")
        return pd.DataFrame()

def get_google_devices_df():
    try:
        df = pd.read_html(GOOGLE_DEVICES_URL, header=0)[0]
        df = df.fillna("")
        return df
    except Exception as e:
        print(f"Error fetching Google devices: {e}")
        return pd.DataFrame()

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return None  # None means first run
    with open(PROGRESS_FILE, "r") as f:
        return json.load(f)

def save_progress(github_list, google_list):
    data = {
        "github": github_list,
        "google": google_list,
        "last_check": datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def format_device_row(row, source):
    details = [f"🆕 <b>New device in {source} list:</b>"]
    for col in row.index:
        value = str(row[col]).strip()
        if value and value.lower() != "nan":
            details.append(f"<b>{col}:</b> {value}")
    return "\n".join(details)

def check_for_status_command():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if not data.get("ok"):
            return False
        # Check last 10 updates for /status command from the correct chat
        for update in reversed(data.get("result", [])[-10:]):
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) == str(CHAT_ID):
                text = msg.get("text", "")
                if text.strip().lower() == "/status":
                    return True
        return False
    except Exception as e:
        print(f"Error checking for /status command: {e}")
        return False

def send_status():
    progress = load_progress()
    if not progress:
        send_telegram_message("ℹ️ No device check has been performed yet.")
        return
    last_check = progress.get("last_check", "N/A")
    github_count = len(progress.get("github", []))
    google_count = len(progress.get("google", []))
    msg = (
        f"📊 <b>Device Checker Status</b>\n"
        f"Last check: <b>{last_check}</b>\n"
        f"GitHub devices tracked: <b>{github_count}</b>\n"
        f"Google devices tracked: <b>{google_count}</b>"
    )
    send_telegram_message(msg)

def main():
    # If /status command is received, reply and exit
    if check_for_status_command():
        send_status()
        return

    lock = filelock.FileLock(LOCK_FILE)
    try:
        with lock.acquire(timeout=30):
            progress = load_progress()
            first_run = progress is None

            github_df = get_github_devices_df()
            google_df = get_google_devices_df()

            github_key_cols = [col for col in github_df.columns if col.lower() in ["model", "device", "codename", "manufacturer", "marketing name", "android version"]]
            if not github_key_cols:
                github_key_cols = ["Model"]
            google_key_cols = [col for col in google_df.columns if col.lower() in ["model", "device", "codename", "manufacturer", "marketing name", "android version"]]
            if not google_key_cols:
                google_key_cols = ["Model"]

            github_df["unique_key"] = github_df[github_key_cols].astype(str).agg("|".join, axis=1)
            google_df["unique_key"] = google_df[google_key_cols].astype(str).agg("|".join, axis=1)

            github_keys = github_df["unique_key"].tolist()
            google_keys = google_df["unique_key"].tolist()

            if first_run:
                prev_github_keys = []
                prev_google_keys = []
            else:
                prev_github_keys = progress.get("github", [])
                prev_google_keys = progress.get("google", [])

            new_github_keys = set(github_keys) - set(prev_github_keys)
            new_google_keys = set(google_keys) - set(prev_google_keys)

            if first_run:
                send_telegram_message(
                    "🚀 Device checker is now active!\n"
                    "You will receive notifications for new devices from now on.\n"
                    "This is a test message to confirm everything is working. ✅"
                )

            # Send each new GitHub device as a separate message
            for key in new_github_keys:
                row = github_df[github_df["unique_key"] == key].iloc[0]
                send_telegram_message(format_device_row(row, "GitHub"))
                time.sleep(1)  # To avoid hitting Telegram rate limits

            # Send each new Google device as a separate message
            for key in new_google_keys:
                row = google_df[google_df["unique_key"] == key].iloc[0]
                send_telegram_message(format_device_row(row, "Google"))
                time.sleep(1)  # To avoid hitting Telegram rate limits

            # If not first run and no new devices, send "no new devices" message
            if not first_run and not new_github_keys and not new_google_keys:
                send_telegram_message("✅ No new devices found in either list today.")

            # Save progress (list of unique keys)
            save_progress(github_keys, google_keys)
    except filelock.Timeout:
        print("Another process is running. Exiting.")
        send_telegram_message("❌ Another check is currently running. Please wait.")

if __name__ == "__main__":
    main()
