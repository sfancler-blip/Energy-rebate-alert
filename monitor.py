import requests
import json
import os
import sys
import hashlib
from datetime import datetime

URL = os.environ["TARGET_URL"]
PHONE = os.environ["PHONE"]
TEXTBELT_KEY = os.environ["TEXTBELT_APIKEY"]
ALERT_MESSAGE = os.environ.get("ALERT_MESSAGE", "ALERT: The webpage you are monitoring has changed.")
WATCH_TEXT = os.environ.get("WATCH_TEXT", "")
MISSING_TEXT_MESSAGE = os.environ.get("MISSING_TEXT_MESSAGE", f"ALERT: Expected text is no longer found on the monitored page.")

# MODE: "hash" — alert on any page change | "text" — alert when WATCH_TEXT disappears
MODE = os.environ.get("MODE", "hash")

STATE_FILE = "state.json"
LOG_FILE = "monitor.log"


def log(message):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] {message}"
    print(entry, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"page_hash": None, "text_found": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_page():
    response = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.text


def hash_content(content):
    return hashlib.sha256(content.encode()).hexdigest()


def send_sms(message):
    resp = requests.post(
        "https://textbelt.com/text",
        {"phone": PHONE, "message": message, "key": TEXTBELT_KEY},
        timeout=15,
    )
    result = resp.json()
    if result.get("success"):
        log(f"SMS sent. Remaining quota: {result.get('quotaRemaining', '?')}")
    else:
        log(f"SMS failed: {result.get('error', 'unknown error')}")


def check_watch_text(content, state):
    if not WATCH_TEXT:
        return state

    prev_found = state.get("text_found")
    currently_found = WATCH_TEXT in content

    if prev_found is None:
        log(f"Watch text {'found' if currently_found else 'NOT found'} on first run — baseline established.")
    elif prev_found and not currently_found:
        msg = MISSING_TEXT_MESSAGE
        log(f"Watch text gone missing: {msg}")
        send_sms(msg)
    elif not prev_found and not currently_found:
        log("Watch text still missing — already alerted.")
    else:
        log("Watch text present — OK.")

    state["text_found"] = currently_found
    return state


def main():
    state = load_state()
    prev_hash = state.get("page_hash")

    try:
        content = fetch_page()
    except Exception as e:
        log(f"ERROR fetching {URL}: {e}")
        sys.exit(1)

    if MODE == "hash":
        current_hash = hash_content(content)
        log(f"Checked {URL} | Hash: {current_hash[:12]}... | Previous: {str(prev_hash)[:12]}...")

        if prev_hash is None:
            log("First run — baseline established. No alert sent.")
        elif current_hash != prev_hash:
            msg = ALERT_MESSAGE
            log(msg)
            send_sms(msg)
        else:
            log("No change detected.")

        state["page_hash"] = current_hash

    elif MODE == "text":
        state = check_watch_text(content, state)

    else:
        log(f"ERROR: Unknown MODE '{MODE}'. Use 'hash' or 'text'.")
        sys.exit(1)

    save_state(state)


if __name__ == "__main__":
    main()
