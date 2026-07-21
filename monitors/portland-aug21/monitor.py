#!/usr/bin/env python3
"""
Self-contained webpage-section change monitor.

Loads a page with a real browser (Playwright/Chromium), extracts the smallest
element whose text matches a set of patterns (e.g. an event's date line),
hashes that block's text + links, and emails an alert when the block changes
relative to the last run.

Everything this monitor needs lives next to this file:
  - config.json   configuration (url, match_patterns, label, ...)
  - state.json    baseline captured on the previous run (committed back by CI)

It has no dependency on any other monitor in the repo. Copy the whole folder,
change config.json, and you have an independent monitor for another site.

Email is sent one of two ways, tried in this order (env vars set as GitHub
Actions secrets):

  1. Resend HTTP API (preferred — no SMTP creds, no 2FA, no burner Gmail):
       RESEND_API_KEY   API key from resend.com
       MAIL_TO          recipient address
       MAIL_FROM        default "Site Alerts <onboarding@resend.dev>"

  2. SMTP fallback (e.g. Gmail with an app password):
       MAIL_USERNAME    SMTP login / From address
       MAIL_PASSWORD    SMTP password / app password
       MAIL_TO          recipient (defaults to MAIL_USERNAME)
       MAIL_HOST        default smtp.gmail.com
       MAIL_PORT        default 465 (SSL)

If neither is configured, the alert is logged but not sent, so the very first
(baseline) run works before you've configured secrets.
"""
import json
import os
import re
import ssl
import sys
import smtplib
import hashlib
import urllib.request
import urllib.error
from email.message import EmailMessage
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
STATE_FILE = HERE / "state.json"
LOG_FILE = HERE / "monitor.log"


def log(message):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{ts}] {message}"
    print(entry, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(entry + "\n")
    except OSError:
        pass


def load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Page fetch + section extraction
# ---------------------------------------------------------------------------

EXTRACT_JS = r"""
(patterns) => {
  const lc = patterns.map(p => p.toLowerCase());
  // How many distinct event-date lines a chunk of text contains. Used to keep
  // the captured block scoped to ONE event instead of the whole calendar.
  const DATE_RE = /\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/gi;
  const dateLineCount = (t) => { const m = t.match(DATE_RE); return m ? m.length : 0; };

  // 1) Smallest element whose text contains a match pattern (the date node).
  let seed = null;
  for (const el of document.querySelectorAll('body *')) {
    const t = el.innerText || '';
    if (t.length < 8) continue;
    const low = t.toLowerCase();
    if (!lc.some(p => low.includes(p))) continue;
    if (seed === null || t.length < seed.innerText.length) seed = el;
  }
  if (!seed) return { found: false };

  // 2) Climb to the largest ancestor that still describes a SINGLE event
  //    (i.e. does not pull in a second event's date line). This grabs the whole
  //    event card — date + description + ticket link/status — not just the header.
  let card = seed;
  while (card.parentElement && card.parentElement.tagName !== 'BODY') {
    const parentText = card.parentElement.innerText || '';
    if (dateLineCount(parentText) > 1) break;   // parent merges 2+ events -> stop
    if (parentText.length > 1500) break;         // safety: don't swallow the page
    card = card.parentElement;
  }

  const links = Array.from(card.querySelectorAll('a'))
    .map(a => a.href)
    .filter(Boolean);
  return {
    found: true,
    text: (card.innerText || '').replace(/\s+/g, ' ').trim(),
    links: Array.from(new Set(links)),
  };
}
"""


def fetch_section(cfg):
    """Return dict: {found, text, links} for the matched section."""
    from playwright.sync_api import sync_playwright

    url = cfg["url"]
    patterns = cfg["match_patterns"]
    ua = cfg.get(
        "user_agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    wait_ms = int(cfg.get("settle_ms", 3000))

    launch_kwargs = {}
    # Support running behind an inspecting HTTPS proxy (e.g. local dev sandbox).
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
        launch_kwargs["args"] = ["--ignore-certificate-errors"]
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if exe:
        launch_kwargs["executable_path"] = exe

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(user_agent=ua)
        # "networkidle" never fires on sites that keep a background connection
        # open (chat widgets, analytics beacons, embedded calendar polling —
        # common on Squarespace). Wait for "load" instead, then give the page
        # settle_ms to finish any client-side rendering.
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(wait_ms)
        result = page.evaluate(EXTRACT_JS, patterns)
        browser.close()
    return result


def fingerprint(section):
    payload = json.dumps(
        {
            "found": section.get("found", False),
            "text": section.get("text", ""),
            "links": sorted(section.get("links", [])),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_via_resend(subject, body):
    """Return True if handled (sent or definitively failed), False if not configured."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return False

    to_addr = os.environ.get("MAIL_TO")
    from_addr = os.environ.get("MAIL_FROM", "Site Alerts <onboarding@resend.dev>")
    if not to_addr:
        log("RESEND_API_KEY is set but MAIL_TO is missing — cannot send.")
        return True

    payload = json.dumps(
        {"from": from_addr, "to": [to_addr], "subject": subject, "text": body}
    ).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        log(f"Email sent via Resend to {to_addr}: {subject}")
    except urllib.error.HTTPError as e:
        log(f"Resend email FAILED ({e.code}): {e.read().decode(errors='replace')}")
    except Exception as e:  # noqa: BLE001
        log(f"Resend email FAILED: {e}")
    return True


def send_via_smtp(subject, body):
    """Return True if handled (sent or definitively failed), False if not configured."""
    user = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    if not user or not password:
        return False

    to_addr = os.environ.get("MAIL_TO") or user
    host = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "465"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body)

    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=context)
                s.login(user, password)
                s.send_message(msg)
        log(f"Email sent via SMTP to {to_addr}: {subject}")
    except Exception as e:  # noqa: BLE001
        log(f"SMTP email FAILED: {e}")
    return True


def send_email(subject, body):
    if send_via_resend(subject, body):
        return
    if send_via_smtp(subject, body):
        return
    log("Email NOT sent (no RESEND_API_KEY or MAIL_USERNAME/MAIL_PASSWORD set). Body follows:")
    log(body.replace("\n", " | "))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def describe(section):
    if not section.get("found"):
        return "(section not found on page)"
    lines = [section.get("text", "")]
    if section.get("links"):
        lines.append("Links: " + ", ".join(section["links"]))
    return "\n".join(lines)


def main():
    cfg = load_json(CONFIG_FILE, None)
    if cfg is None:
        log(f"ERROR: no config.json at {CONFIG_FILE}")
        sys.exit(1)

    label = cfg.get("label", cfg["url"])
    state = load_json(STATE_FILE, {})
    prev_fp = state.get("fingerprint")

    try:
        section = fetch_section(cfg)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR fetching {cfg['url']}: {e}")
        sys.exit(1)

    fp = fingerprint(section)
    status = "FOUND" if section.get("found") else "not found"
    log(f"[{label}] section {status} | fp {fp[:12]}... | prev {str(prev_fp)[:12]}...")

    if prev_fp is None:
        log("First run — baseline established. No alert sent.")
        log("Captured section:\n" + describe(section))
    elif fp != prev_fp:
        subject = cfg.get("alert_subject", f"CHANGE DETECTED: {label}")
        body = (
            f"The watched section changed.\n\n"
            f"Monitor: {label}\n"
            f"URL: {cfg['url']}\n\n"
            f"--- PREVIOUS ---\n{describe(state.get('section', {}))}\n\n"
            f"--- CURRENT ---\n{describe(section)}\n"
        )
        log("CHANGE DETECTED — sending alert.")
        send_email(subject, body)
    else:
        log("No change detected.")

    state["fingerprint"] = fp
    state["section"] = section
    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
