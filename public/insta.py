# """
# One-time local login script for Instagrapi.
# Generates ig_session.json with cached session data.

# Usage:
#     python public/insta.py

# After running, copy the content of ig_session.json into a
# GitHub Secret named IG_SESSION_JSON.
# """

# import time
# from instagrapi import Client

# # --- Configuration ---
# USERNAME = "reels.getter"
# PASSWORD = "Gaurav@123"
# SESSION_FILE = "ig_session.json"

# # --- Login with anti-detection settings ---
# cl = Client()

# # Set realistic delay between requests to avoid rate limits
# cl.delay_range = [2, 5]

# print(f"Logging in as '{USERNAME}'...")
# try:
#     cl.login(USERNAME, PASSWORD)
#     cl.dump_settings(SESSION_FILE)
#     print(f"\n✅ Session saved to '{SESSION_FILE}'!")
#     print("📋 Copy the content of this file to GitHub Secrets as IG_SESSION_JSON.")
# except Exception as e:
#     print(f"\n❌ Login failed: {e}")
#     print("\nTroubleshooting:")
#     print("  1. Wait 5-10 minutes (Instagram may have rate-limited you)")
#     print("  2. Confirm the password by logging in at instagram.com")
#     print("  3. Check if Instagram sent a security challenge to your email/phone")
#     print("  4. Try logging in from the Instagram app first to 'trust' this device")



from instagrapi import Client

cl = Client()
# Replace with your actual sessionid value from the browser
SESSION_ID = "80585732868%3A6pxJCabn5kOkbW%3A26%3AAYiQB-KGTmLpMgpSOVoBxmRyQ3xHn1QwUjFnv1glXQ"

# This logs in WITHOUT a password using your browser's existing session
cl.login_by_sessionid(SESSION_ID)

# Now save the full settings (including device IDs) to a file
cl.dump_settings("ig_session.json")
print("Success! ig_session.json created. Copy its content to your GitHub Secret.")