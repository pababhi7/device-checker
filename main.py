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
UPDATE_ID_FILE = "telegram_update_id.txt"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=data, timeout=10)
        print("Telegram response:", resp.status_code, resp.text)  # Debug print
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def get_github_devices_df():
    try:
        df = pd.read_csv(GITHUB_RAW_URL)
        df = df.fillna("")
        print(f"Fetched {len(df)} devices from GitHub.")
        return df
    except Exception as e:
        print(f"Error fetching GitHub devices: {e}")
        return pd.DataFrame()

def get_google_devices_df():
    try:
        df = pd.read_html(GOOGLE_DEVICES_URL, header=0)[0]
        df = df.fillna("")
        print(f"Fetched {len(df)} devices from Google.")
        return df
    except Exception as e:
        print(f"Error fetching Google devices: {e}")
        return pd.DataFrame()

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        print("No progress file found. This is the first run.")
        return None  # None means first run
    with open(PROGRESS_FILE, "r") as f:
        print("Loaded progress file.")
        return json.load(f)

def save_progress(github_list, google_list):
    data = {
        "github": github_list,
        "google": google_list,
        "last_check": datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("Progress file saved.")

def get_last_update_id():
    if os.path.exists(UPDATE_ID_FILE):
        with open(UPDATE_ID_FILE, "r") as f:
            return int(f.read().strip())
    return 0

def save_last_update_id(update_id):
    with open(UPDATE_ID_FILE, "w") as f:
        f.write(str(update_id))

def format_device_row(row, source):
    details = [f"🆕 <b>New device in {source} list:</b>"]
    for col in row.index:
        if col == "unique_key":  # Skip the unique_key column
            continue
        value = str(row[col]).strip()
        if value and value.lower() != "nan":
            details.append(f"<b>{col}:</b> {value}")
    return "\n".join(details)

def check_for_status_command():
    last_update_id = get_last_update_id()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1} if last_update_id > 0 else {}
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print("Failed to get updates from Telegram.")
            return False
        data = resp.json()
        if not data.get("ok"):
            print("Telegram getUpdates not ok.")
            return False
        
        updates = data.get("result", [])
        for update in updates:
            update_id = update.get("update_id", 0)
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) == str(CHAT_ID):
                text = msg.get("text", "")
                if text.strip().lower() == "/status":
                    print("Received /status command.")
                    # Save the update_id to mark as processed
                    if update_id > last_update_id:
                        save_last_update_id(update_id)
                    return True
            # Save the highest update_id even if not a status command
            if update_id > last_update_id:
                save_last_update_id(update_id)
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

def get_key_columns(df, source_name):
    """Get key columns for creating unique identifiers"""
    key_cols = [col for col in df.columns if col.lower() in ["model", "device", "codename", "manufacturer", "marketing name", "android version"]]
    
    if not key_cols:
        # Try to find any column with 'model' in its name
        model_cols = [col for col in df.columns if 'model' in col.lower()]
        if model_cols:
            key_cols = model_cols[:1]
        elif "Model" in df.columns:
            key_cols = ["Model"]
        elif len(df.columns) > 0:
            # Use first column as fallback
            key_cols = df.columns[:1].tolist()
            print(f"Warning: Using fallback column '{key_cols[0]}' for {source_name}")
        else:
            key_cols = []
    
    return key_cols

def main():
    print("Script started.")
    
    # If /status command is received, reply and exit
    if check_for_status_command():
        send_status()
        print("Status command handled. Exiting.")
        return

    lock = filelock.FileLock(LOCK_FILE)
    try:
        with lock.acquire(timeout=30):
            # Send start message
            start_time = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
            send_telegram_message(f"🔍 <b>Starting device check</b>\nTime: {start_time}")
            
            progress = load_progress()
            first_run = progress is None

            github_df = get_github_devices_df()
            google_df = get_google_devices_df()

            # Validate DataFrames
            if github_df.empty and google_df.empty:
                send_telegram_message("⚠️ Failed to fetch both device lists. Please check data sources.")
                return
            
            # Initialize counters
            github_total = len(github_df) if not github_df.empty else 0
            google_total = len(google_df) if not google_df.empty else 0
            
            # Process GitHub devices
            if not github_df.empty:
                github_key_cols = get_key_columns(github_df, "GitHub")
                if github_key_cols:
                    github_df["unique_key"] = github_df[github_key_cols].astype(str).agg("|".join, axis=1)
                    github_keys = github_df["unique_key"].tolist()
                else:
                    github_keys = []
                    print("Warning: No suitable columns found for GitHub unique keys")
            else:
                github_keys = []

            # Process Google devices
            if not google_df.empty:
                google_key_cols = get_key_columns(google_df, "Google")
                if google_key_cols:
                    google_df["unique_key"] = google_df[google_key_cols].astype(str).agg("|".join, axis=1)
                    google_keys = google_df["unique_key"].tolist()
                else:
                    google_keys = []
                    print("Warning: No suitable columns found for Google unique keys")
            else:
                google_keys = []

            if first_run:
                prev_github_keys = []
                prev_google_keys = []
            else:
                prev_github_keys = progress.get("github", [])
                prev_google_keys = progress.get("google", [])

            new_github_keys = set(github_keys) - set(prev_github_keys)
            new_google_keys = set(google_keys) - set(prev_google_keys)

            new_github_count = len(new_github_keys)
            new_google_count = len(new_google_keys)
            total_new = new_github_count + new_google_count

            print(f"New GitHub devices: {new_github_count}")
            print(f"New Google devices: {new_google_count}")

            if first_run:
                print("First run, sending start notification.")
                send_telegram_message(
                    "🚀 <b>Device checker is now active!</b>\n"
                    "You will receive notifications for new devices from now on.\n"
                    f"Currently tracking:\n"
                    f"• GitHub: {github_total} devices\n"
                    f"• Google: {google_total} devices\n"
                    "This is a test message to confirm everything is working. ✅"
                )

            # Send each new GitHub device as a separate message
            for key in new_github_keys:
                row = github_df[github_df["unique_key"] == key].iloc[0]
                print(f"Sending new GitHub device: {key}")
                send_telegram_message(format_device_row(row, "GitHub"))
                time.sleep(1)  # To avoid hitting Telegram rate limits

            # Send each new Google device as a separate message
            for key in new_google_keys:
                row = google_df[google_df["unique_key"] == key].iloc[0]
                print(f"Sending new Google device: {key}")
                send_telegram_message(format_device_row(row, "Google"))
                time.sleep(1)  # To avoid hitting Telegram rate limits

            # Send completion summary
            if not first_run:
                completion_time = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
                
                if total_new > 0:
                    summary_msg = (
                        f"✅ <b>Device check completed</b>\n"
                        f"Time: {completion_time}\n\n"
                        f"📱 <b>New devices found:</b>\n"
                        f"• GitHub: {new_github_count} new\n"
                        f"• Google: {new_google_count} new\n"
                        f"• Total: {total_new} new devices\n\n"
                        f"📊 <b>Total devices tracked:</b>\n"
                        f"• GitHub: {github_total}\n"
                        f"• Google: {google_total}"
                    )
                else:
                    summary_msg = (
                        f"✅ <b>Device check completed</b>\n"
                        f"Time: {completion_time}\n\n"
                        f"No new devices found in either list.\n\n"
                        f"📊 <b>Total devices tracked:</b>\n"
                        f"• GitHub: {github_total}\n"
                        f"• Google: {google_total}"
                    )
                
                send_telegram_message(summary_msg)

            # Save progress (list of unique keys)
            save_progress(github_keys, google_keys)
            
    except filelock.Timeout:
        print("Another process is running. Exiting.")
        send_telegram_message("❌ Another check is currently running. Please wait.")

if __name__ == "__main__":
    main()
