import requests
import pandas as pd
import time
from datetime import datetime
import os
import json

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
GITHUB_RAW_URL = "https://raw.githubusercontent.com/KHwang9883/MobileModels-csv/main/models.csv"
PROGRESS_FILE = "device_progress.json"  # This file will persist in GitHub

def save_progress(index, total_devices):
    try:
        progress_data = {
            'last_sent_index': index,
            'total_devices': total_devices,
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress_data, f)
    except Exception as e:
        print(f"Error saving progress: {e}")

def get_saved_progress():
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_sent_index', 0)
        return 0
    except:
        return 0

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code == 429:  # Rate limit
            time.sleep(30)
            return send_telegram_message(message)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        time.sleep(5)
        return None

def get_devices_data():
    try:
        print("Fetching data from GitHub...")
        response = requests.get(GITHUB_RAW_URL)
        if response.status_code == 200:
            df = pd.read_csv(GITHUB_RAW_URL)
            print(f"Successfully loaded CSV with {len(df)} rows")
            return df
        else:
            print(f"Failed to fetch data: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def format_device_message(row, is_new=False):
    prefix = "🆕" if is_new else "📱"
    try:
        return (
            f"{prefix} <b>{row['brand_title']}</b>\n\n"
            f"<b>Model:</b> {row['model']}\n"
            f"<b>Type:</b> {row['dtype']}\n"
            f"<b>Brand:</b> {row['brand']}\n"
            f"<b>Code:</b> {row['code']}\n"
            f"<b>Code Alias:</b> {row['code_alias']}\n"
            f"<b>Model Name:</b> {row['model_name']}\n"
            f"<b>Version:</b> {row['ver_name']}"
        )
    except Exception as e:
        print(f"Error formatting device: {e}")
        return None

def check_for_updates():
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"Starting check at {current_time}")
    
    # Get last sent index
    last_sent_index = get_saved_progress()
    
    df = get_devices_data()
    if df is not None:
        total_devices = len(df)
        
        if last_sent_index < total_devices:
            send_telegram_message(
                f"📱 Resuming device notifications\n"
                f"Progress: {last_sent_index}/{total_devices}\n"
                f"Time: {current_time}"
            )
            
            try:
                # Continue from where we left off
                for index, row in df.iloc[last_sent_index:].iterrows():
                    message = format_device_message(row)
                    if message:
                        send_result = send_telegram_message(message)
                        if send_result:
                            save_progress(index + 1, total_devices)
                            
                            # Progress update every 50 devices
                            if (index + 1) % 50 == 0:
                                progress_msg = (
                                    f"📊 Progress Update:\n"
                                    f"Sent: {index + 1}/{total_devices} devices\n"
                                    f"Remaining: {total_devices - (index + 1)} devices"
                                )
                                send_telegram_message(progress_msg)
                        
                        time.sleep(1)  # Delay to avoid rate limits
                
                if last_sent_index + 1 >= total_devices:
                    send_telegram_message(
                        "✅ All devices have been sent!\n"
                        f"Total devices: {total_devices}\n"
                        f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
            except Exception as e:
                error_message = (
                    f"❌ Error during sending: {str(e)}\n"
                    f"Will resume from device {last_sent_index + 1} in next run\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                print(error_message)
                send_telegram_message(error_message)
        else:
            # Check for new devices
            if total_devices > last_sent_index:
                new_devices = df.iloc[last_sent_index:]
                send_telegram_message(f"🆕 Found {len(new_devices)} new device(s)!")
                
                for index, row in new_devices.iterrows():
                    message = format_device_message(row, is_new=True)
                    if message:
                        send_telegram_message(message)
                        save_progress(index + 1, total_devices)
                        time.sleep(1)
                
                send_telegram_message("✅ New devices update complete!")
            else:
                print("No new devices to send")

if __name__ == '__main__':
    check_for_updates()
