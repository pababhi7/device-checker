import requests
import pandas as pd
import time
from datetime import datetime
import os
import json
import filelock

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
GITHUB_RAW_URL = "https://raw.githubusercontent.com/KHwang9883/MobileModels-csv/main/models.csv"
PROGRESS_FILE = "device_progress.json"
LOCK_FILE = "device_checker.lock"  # Add lock file

def save_progress(index, total_devices):
    lock = filelock.FileLock(LOCK_FILE)
    try:
        with lock.acquire(timeout=10):  # Wait up to 10 seconds for lock
            progress_data = {
                'last_sent_index': index,
                'total_devices': total_devices,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(progress_data, f)
    except filelock.Timeout:
        print("Could not acquire lock - another process is running")
        return False

def get_saved_progress():
    lock = filelock.FileLock(LOCK_FILE)
    try:
        with lock.acquire(timeout=10):
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('last_sent_index', 0)
            return 0
    except filelock.Timeout:
        print("Could not acquire lock - another process is running")
        return None

def check_for_updates():
    lock = filelock.FileLock(LOCK_FILE)
    try:
        # Try to acquire lock
        with lock.acquire(timeout=1):  # Short timeout to fail fast if already running
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"Starting check at {current_time}")
            
            last_sent_index = get_saved_progress()
            if last_sent_index is None:
                send_telegram_message("❌ Another check is currently running. Please wait.")
                return
            
            df = get_devices_data()
            if df is not None:
                total_devices = len(df)
                
                if last_sent_index < total_devices:
                    send_telegram_message(
                        f"📱 Checking for new devices\n"
                        f"Progress: {last_sent_index}/{total_devices}\n"
                        f"Time: {current_time}"
                    )
                    
                    try:
                        for index, row in df.iloc[last_sent_index:].iterrows():
                            message = format_device_message(row)
                            if message:
                                send_result = send_telegram_message(message)
                                if send_result:
                                    save_progress(index + 1, total_devices)
                                    
                                    if (index + 1) % 50 == 0:
                                        progress_msg = (
                                            f"📊 Progress Update:\n"
                                            f"Sent: {index + 1}/{total_devices} devices\n"
                                            f"Remaining: {total_devices - (index + 1)} devices"
                                        )
                                        send_telegram_message(progress_msg)
                                
                                time.sleep(1)
                        
                        send_telegram_message("✅ Update complete!")
                        
                    except Exception as e:
                        error_message = (
                            f"❌ Error during sending: {str(e)}\n"
                            f"Will resume from device {last_sent_index + 1} in next run\n"
                            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        print(error_message)
                        send_telegram_message(error_message)
                else:
                    print("No new devices to send")
                    send_telegram_message("✅ Already up to date!")
                    
    except filelock.Timeout:
        send_telegram_message("❌ Another check is currently running. Please wait.")
        print("Could not acquire lock - another process is running")
      
