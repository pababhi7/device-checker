import requests
import pandas as pd
import json
import filelock
from datetime import datetime
import pytz
import os
import time

# --- READ TELEGRAM BOT TOKEN AND CHAT ID FROM ENVIRONMENT VARIABLES ---
try:
    BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
    print("✓ Telegram credentials loaded from environment variables")
except KeyError as e:
    print(f"ERROR: Environment variable {e} not found!")
    exit(1)
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
        print(f"Telegram response: {resp.status_code}")
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
        return None
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

def format_device_row(row, source):
    details = [f"🆕 <b>New device in {source} list:</b>"]
    for col in row.index:
        if col == "unique_key":
            continue
        value = str(row[col]).strip()
        if value and value.lower() != "nan":
            details.append(f"<b>{col}:</b> {value}")
    return "\n".join(details)

def get_key_columns(df, source_name):
    key_cols = [col for col in df.columns if col.lower() in ["model", "device", "codename", "manufacturer", "marketing name", "android version"]]
    
    if not key_cols:
        model_cols = [col for col in df.columns if 'model' in col.lower()]
        if model_cols:
            key_cols = model_cols[:1]
        elif "Model" in df.columns:
            key_cols = ["Model"]
        elif len(df.columns) > 0:
            key_cols = df.columns[:1].tolist()
            print(f"Warning: Using fallback column '{key_cols[0]}' for {source_name}")
        else:
            key_cols = []
    
    return key_cols

def main():
    print("=== Device Checker Started ===")
    
    # Send start message
    start_time = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    print("Sending start notification...")
    send_telegram_message(f"🔍 <b>Starting device check</b>\nTime: {start_time}")
    
    lock = filelock.FileLock(LOCK_FILE)
    try:
        with lock.acquire(timeout=30):
            progress = load_progress()
            first_run = progress is None

            print("Fetching device data...")
            github_df = get_github_devices_df()
            google_df = get_google_devices_df()

            # Validate DataFrames
            if github_df.empty and google_df.empty:
                print("ERROR: Failed to fetch device data")
                send_telegram_message("⚠️ Failed to fetch both device lists. Please check data sources.")
                return
            
            # Initialize counters
            github_total = len(github_df) if not github_df.empty else 0
            google_total = len(google_df) if not google_df.empty else 0
            
            print(f"GitHub devices: {github_total}, Google devices: {google_total}")
            
            # Process GitHub devices
            github_keys = []
            if not github_df.empty:
                github_key_cols = get_key_columns(github_df, "GitHub")
                if github_key_cols:
                    github_df["unique_key"] = github_df[github_key_cols].astype(str).agg("|".join, axis=1)
                    github_keys = github_df["unique_key"].tolist()

            # Process Google devices
            google_keys = []
            if not google_df.empty:
                google_key_cols = get_key_columns(google_df, "Google")
                if google_key_cols:
                    google_df["unique_key"] = google_df[google_key_cols].astype(str).agg("|".join, axis=1)
                    google_keys = google_df["unique_key"].tolist()

            # Compare with previous data
            if first_run:
                prev_github_keys = []
                prev_google_keys = []
                print("First run - establishing baseline")
            else:
                prev_github_keys = progress.get("github", [])
                prev_google_keys = progress.get("google", [])
                print(f"Previous: GitHub {len(prev_github_keys)}, Google {len(prev_google_keys)}")

            new_github_keys = set(github_keys) - set(prev_github_keys)
            new_google_keys = set(google_keys) - set(prev_google_keys)

            new_github_count = len(new_github_keys)
            new_google_count = len(new_google_keys)
            total_new = new_github_count + new_google_count

            print(f"New devices found: GitHub {new_github_count}, Google {new_google_count}")

            # Send notifications
            if first_run:
                print("Sending welcome message...")
                send_telegram_message(
                    "🚀 <b>Device checker is now active!</b>\n"
                    "You will receive notifications for new devices from now on.\n"
                    f"Currently tracking:\n"
                    f"• GitHub: {github_total} devices\n"
                    f"• Google: {google_total} devices\n\n"
                    "✅ Setup complete! Next run will check for new devices."
                )
            else:
                # Send new device notifications
                for key in new_github_keys:
                    row = github_df[github_df["unique_key"] == key].iloc[0]
                    print(f"Notifying about new GitHub device")
                    send_telegram_message(format_device_row(row, "GitHub"))
                    time.sleep(1)

                for key in new_google_keys:
                    row = google_df[google_df["unique_key"] == key].iloc[0]
                    print(f"Notifying about new Google device")
                    send_telegram_message(format_device_row(row, "Google"))
                    time.sleep(1)

                # Send completion summary
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
                
                print("Sending completion summary...")
                send_telegram_message(summary_msg)

            # Save progress
            save_progress(github_keys, google_keys)
            print("✓ Progress saved")
            print("=== Script completed successfully ===")
            
    except filelock.Timeout:
        error_msg = "❌ Another check is currently running. Please wait."
        print(error_msg)
        send_telegram_message(error_msg)
    except Exception as e:
        error_msg = f"❌ Error during device check: {str(e)}"
        print(f"ERROR: {e}")
        send_telegram_message(error_msg)

if __name__ == "__main__":
    main()
