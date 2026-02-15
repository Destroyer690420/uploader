"""
convert_session.py — One-time Cookie -> Instaloader Session Converter

Reads browser cookies from public/ig_cookies.json and creates an
Instaloader session file that can be used for authenticated scraping.

Usage (run once on your PC):
    python convert_session.py

After running, the session file is saved at public/ig_session_file.
"""

import json
import os
import sys
from pathlib import Path

# Fix Windows console encoding for emoji/unicode
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import instaloader

BASE_DIR = Path(__file__).resolve().parent
COOKIES_PATH = str(BASE_DIR / "public" / "ig_cookies.json")
SESSION_FILE = str(BASE_DIR / "public" / "ig_session_file")


def main():
    if not os.path.exists(COOKIES_PATH):
        print(f"[ERROR] Cookie file not found: {COOKIES_PATH}")
        return

    with open(COOKIES_PATH, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"[OK] Loaded {len(cookies)} cookies from {COOKIES_PATH}")

    # Create an Instaloader instance and inject cookies
    L = instaloader.Instaloader()

    for cookie in cookies:
        L.context._session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain", ".instagram.com"),
            path=cookie.get("path", "/"),
        )

    # Extract username from ds_user_id or test the session
    ds_user_id = next(
        (c["value"] for c in cookies if c["name"] == "ds_user_id"), None
    )

    if ds_user_id:
        print(f"[INFO] User ID from cookies: {ds_user_id}")

    # Test the session by making a request
    try:
        username = L.test_login()
        if username:
            print(f"[OK] Session valid! Logged in as: @{username}")
        else:
            print("[WARN] Session test returned None, but saving anyway...")
    except Exception as e:
        print(f"[WARN] Session test error: {e}")
        print("   Saving session file anyway -- it may still work.")

    # Save the session file
    L.save_session_to_file(SESSION_FILE)
    print(f"\n[OK] Session file saved to: {SESSION_FILE}")
    print("   You can use this file with ig_scraper.py")


if __name__ == "__main__":
    main()
