import requests
import pandas as pd
import time
from datetime import datetime
import os

BOT_TOKEN = "7650673916:AAFgHG6XEivz6_5fKQ076JLyHJk6NFQKipc"
CHAT_ID = "700563168"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/KHwang9883/MobileModels-csv/main/models.csv"

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
        print(f"Message sent: {response.json()}")
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
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
    send_telegram_message(f"⏰ Checking for new devices at {current_time}")
    
    df = get_devices_data()
    if df is not None:
        try:
            # Send all devices info
            send_telegram_message(f"📱 Found {len(df)} devices")
            
            for index, row in df.iterrows():
                message = format_device_message(row, is_new=True)
                if message:
                    send_telegram_message(message)
                    time.sleep(0.1)  # Avoid rate limiting
                
                # Send progress every 100 devices
                if (index + 1) % 100 == 0:
                    send_telegram_message(f"Progress: {index + 1}/{len(df)} devices processed")
            
            send_telegram_message("✅ Device check complete!")
            
        except Exception as e:
            error_message = f"❌ Error during check: {str(e)}"
            print(error_message)
            send_telegram_message(error_message)

if __name__ == '__main__':
    check_for_updates()
