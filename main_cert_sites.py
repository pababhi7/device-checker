 import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import hashlib

# === CONFIG ===
KNOWN_DEVICES_FILE = "known_devices.json"
CHANGES_LOG_FILE = "changes_log.json"
IST = pytz.timezone("Asia/Kolkata")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# === UTILS ===
def load_known_devices():
    if os.path.exists(KNOWN_DEVICES_FILE):
        with open(KNOWN_DEVICES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_known_devices(devices):
    with open(KNOWN_DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(devices), f, ensure_ascii=False, indent=2)

def append_changes_log(message):
    log_entry = {
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "message": message
    }
    if os.path.exists(CHANGES_LOG_FILE):
        with open(CHANGES_LOG_FILE, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    else:
        log_data = []
    log_data.append(log_entry)
    with open(CHANGES_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")

def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# === SCRAPER FUNCTIONS ===
def fetch_nbtc():
    url = "https://mocheck.nbtc.go.th/search-equipments"
    r = requests.get(url, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    devices = []
    for row in soup.select("table tbody tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if cols:
            devices.append(f"NBTC | {' | '.join(cols)}")
    return devices

def fetch_qi_wpc():
    url = "https://www.wirelesspowerconsortium.com/products"
    r = requests.get(url, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    devices = []
    for row in soup.select("table tbody tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if cols:
            devices.append(f"Qi WPC | {' | '.join(cols)}")
    return devices

def fetch_audio_jp():
    url = "https://www.tele.soumu.go.jp/giteki/SearchServlet?pageID=2"
    r = requests.get(url, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    devices = []
    for row in soup.select("table tbody tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if cols:
            devices.append(f"Audio JP | {' | '.join(cols)}")
    return devices

# === MAIN ===
def run_scraper():
    known_devices = load_known_devices()
    current_devices = set()
    new_devices = []

    sources = [fetch_nbtc, fetch_qi_wpc, fetch_audio_jp]

    for fetch_fn in sources:
        try:
            for dev in fetch_fn():
                fid = fingerprint(dev)
                current_devices.add(fid)
                if fid not in known_devices:
                    new_devices.append(dev)
                    append_changes_log(dev)
        except Exception as e:
            print(f"[ERROR] {fetch_fn.__name__} failed: {e}")

    if new_devices:
        msg = "📢 New devices found:\n" + "\n".join(new_devices)
        send_telegram_message(msg)
        print(msg)
    else:
        print("[INFO] No new devices found.")

    save_known_devices(current_devices)

if __name__ == "__main__":
    run_scraper()
