It seems the Telegram notifications aren't being sent. Let's debug this issue. Here's an updated version with better error handling and debugging:

```python
import requests
import pandas as pd
import json
import filelock
from datetime import datetime
import pytz
import os
import time
import sys

# --- READ TELEGRAM BOT TOKEN AND CHAT ID FROM ENVIRONMENT VARIABLES ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Debug: Print environment variables (masked)
print(f"BOT_TOKEN present: {'Yes' if BOT_TOKEN else 'No'} (length: {len(BOT_TOKEN)})")
print(f"CHAT_ID present: {'Yes' if CHAT_ID else 'No'} (value: {CHAT_ID})")

if not BOT_TOKEN or not CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables not set!")
    sys.exit(1)
# ---------------------------------------------------------------------

GITHUB_RAW_URL = "https://raw.githubusercontent.com/KHwang9883/MobileModels-csv/main/models.csv"
GOOGLE_DEVICES_URL = "https://storage.googleapis.com/play_public/supported_devices.html"

PROGRESS_FILE = "device_progress.json"
LOCK_FILE = "device_checker.lock"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    print(f"\n--- Attempting to send Telegram message ---")
    print(f"URL: {url[:50]}...")  # Print first 50 chars of URL
    print(f"Chat ID: {CHAT_ID}")
    print(f"Message preview: {message[:100]}...")
    
    try:
        resp = requests.post(url, data=data, timeout=10)
        print(f"Response status: {resp.status_code}")
        print(f"Response text: {resp.text}")
        
        if resp.status_code == 200:
            response_json = resp.json()
            if response_json.get("ok"):
                print("✓ Message sent successfully!")
                return True
            else:
                print(f"✗ Telegram API error: {response_json.get('description', 'Unknown error')}")
                return False
        else:
            print(f"✗ HTTP error: {resp.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Request error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def test_telegram_connection():
    """Test if Telegram bot is properly configured"""
    print("\n=== Testing Telegram Connection ===")
    test_message = "🔧 Test message: Bot connection successful!"
    success = send_telegram_message(test_message)
    if not success:
        print("\nFAILED TO SEND TEST MESSAGE. Please check:")
        print("1. Bot token is correct")
        print("2. Chat ID is correct") 
        print("3. Bot has permission to send messages to the chat")
        print("4. Network connection is working")
        return False
    return True

def get_github_devices_df():
    try:
        print("\nFetching GitHub devices...")
        df = pd.read_csv(GITHUB_RAW_URL)
        df = df.fillna("")
        print(f"✓ Fetched {len(df)} devices from GitHub.")
        return df
    except Exception as e:
        print(f"✗ Error fetching GitHub devices: {e}")
        return pd.DataFrame()

def get_google_devices_df():
    try:
        print("\nFetching Google devices...")
        df = pd.read_html(GOOGLE_DEVICES_URL, header=0)[0]
        df = df.fillna("")
        print(f"✓ Fetched {len(df)} devices from Google.")
        return df
    except Exception as e:
        print(f"✗ Error fetching Google devices: {e}")
        return pd.DataFrame()

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        print("\nNo progress file found. This is the first run.")
        return None  # None means first run
    try:
        with open(PROGRESS_FILE, "r") as f:
            data = json.load(f)
            print(f"\nLoaded progress file. Last check: {data.get('last_check', 'Unknown')}")
            return data
    except Exception as e:
        print(f"\nError loading progress file: {e}")
        return None

def save_progress(github_list, google_list):
    data = {
        "github": github_list,
        "google": google_list,
        "last_check": datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✓ Progress file saved. GitHub: {len(github_list)} devices, Google: {len(google_list)} devices")
    except Exception as e:
        print(f"\n✗ Error saving progress file: {e}")

def format_device_row(row, source):
    details = [f"🆕 <b>New device in {source} list:</b>"]
    for col in row.index:
        if col == "unique_key":  # Skip the unique_key column
            continue
        value = str(row[col]).strip()
        if value and value.lower() != "nan":
            details.append(f"<b>{col}:</b> {value}")
    return "\n".join(details)

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
    
    print(f"Key columns for {source_name}: {key_cols}")
    return key_cols

def main():
    print("=== Device Checker Script Started ===")
    print(f"Current time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test Telegram connection first
    if not test_telegram_connection():
        print("\nExiting due to Telegram connection failure.")
        return
    
    lock = filelock.FileLock(LOCK_FILE)
    try:
        with lock.acquire(timeout=30):
            # Send start message
            start_time = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
            print("\nSending start notification...")
            send_telegram_message(f"🔍 <b>Starting device check</b>\nTime: {start_time}")
            
            progress = load_progress()
            first_run = progress is None

            github_df = get_github_devices_df()
            google_df = get_google_devices_df()

            # Validate DataFrames
            if github_df.empty and google_df.empty:
                print("\n✗ Both DataFrames are empty!")
                send_telegram_message("⚠️ Failed to fetch both device lists. Please check data sources.")
                return
            
            # Initialize counters
            github_total = len(github_df) if not github_df.empty else 0
            google_total = len(google_df) if not google_df.empty else 0
            
            print(f"\nTotal devices - GitHub: {github_total}, Google: {google_total}")
            
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
                print("\nFirst run - all devices will be considered as already tracked")
            else:
                prev_github_keys = progress.get("github", [])
                prev_google_keys = progress.get("google", [])
                print(f"\nPrevious run - GitHub: {len(prev_github_keys)} devices, Google: {len(prev_google_keys)} devices")

            new_github_keys = set(github_keys) - set(prev_github_keys)
            new_google_keys = set(google_keys) - set(prev_google_keys)

            new_github_count = len(new_github_keys)
            new_google_count = len(new_google_keys)
            total_new = new_github_count + new_google_count

            print(f"\nNew devices found - GitHub: {new_github_count}, Google: {new_google_count}")

            if first_run:
                print("\nSending first run notification...")
                send_telegram_message(
                    "🚀 <b>Device checker is now active!</b>\n"
                    "You will receive notifications for new devices from now on.\n"
                    f"Currently tracking:\n"
                    f"• GitHub: {github_total} devices\n"
                    f"• Google: {google_total} devices\n"
                    "This is a test message to confirm everything is working. ✅"
                )

            # Send each new GitHub device as a separate message
            if new_github_count > 0:
                print(f"\nSending {new_github_count} new GitHub device notifications...")
                for i, key in enumerate(new_github_keys, 1):
                    row = github_df[github_df["unique_key"] == key].iloc[0]
                    print(f"Sending GitHub device {i}/{new_github_count}: {key[:50]}...")
                    send_telegram_message(format_device_row(row, "GitHub"))
                    time.sleep(1)  # To avoid hitting Telegram rate limits

            # Send each new Google device as a separate message
            if new_google_count > 0:
                print(f"\nSending {new_google_count} new Google device notifications...")
                for i, key in enumerate(new_google_keys, 1):
                    row = google_df[google_df["unique_key"] == key].iloc[0]
                    print(f"Sending Google device {i}/{new_google_count}: {key[:50]}...")
                    send_telegram_message(format_device_row(row, "Google"))
                    time.sleep(1)  # To avoid hitting Telegram rate limits

            # Send completion summary
            completion_time = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
            
            if first_run:
                print("\nFirst run complete - skipping completion summary")
            elif total_new > 0:
                print("\nSending completion summary (new devices found)...")
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
                send_telegram_message(summary_msg)
            else:
                print("\nSending completion summary (no new devices)...")
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
            
            print("\n=== Script completed successfully ===")
            
    except filelock.Timeout:
        print("\n✗ Another process is running. Exiting.")
        send_telegram_message("❌ Another check is currently running. Please wait.")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        send_telegram_message(f"❌ Error during device check: {str(e)}")

if __name__ == "__main__":
    main()
```

This updated version includes:

1. **Environment variable checking** - Verifies that BOT_TOKEN and CHAT_ID are set
2. **Test message** - Sends a test message at the start to verify Telegram is working
3. **Detailed logging** - Shows every step of the process
4. **Error details** - Shows full error messages and responses from Telegram API
5. **Progress tracking** - Shows what's happening at each stage

Run this version and share the console output. This will help identify exactly where the issue is occurring. Common issues include:

- Incorrect bot token
- Wrong chat ID
- Bot not added to the chat/channel
- Network connectivity issues
- Bot permissions not set correctly
