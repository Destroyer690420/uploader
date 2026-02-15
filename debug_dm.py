"""Debug script — check pending inbox + more params."""
import json, sys, requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("public/ig_cookies.json", "r") as f:
    raw = json.load(f)
cookies = {c["name"]: c["value"] for c in raw}

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "X-CSRFToken": cookies.get("csrftoken", ""),
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/direct/inbox/",
})
for name, value in cookies.items():
    s.cookies.set(name, value, domain=".instagram.com")

print("=" * 50)
print("1. REGULAR INBOX (with limit=20)")
print("=" * 50)
r = s.get("https://www.instagram.com/api/v1/direct_v2/inbox/", params={"limit": 20}, timeout=15)
print(f"Status: {r.status_code}")
data = r.json()
inbox = data.get("inbox", {})
threads = inbox.get("threads", [])
print(f"Threads: {len(threads)}, unseen_count: {inbox.get('unseen_count')}")
print(f"has_older: {inbox.get('has_older')}, oldest_cursor: {inbox.get('oldest_cursor', 'N/A')}")
for i, t in enumerate(threads):
    users = t.get("users", [])
    uname = users[0].get("username", "?") if users else "?"
    items = t.get("items", [])
    print(f"  Thread {i}: @{uname} ({len(items)} items)")
    for j, item in enumerate(items[:5]):
        itype = item.get("item_type", "?")
        clip = item.get("clip", {})
        code = ""
        if clip and isinstance(clip, dict) and "clip" in clip:
            code = clip["clip"].get("code", "")
        media_share = item.get("media_share", {})
        if media_share and isinstance(media_share, dict):
            code = code or media_share.get("code", "")
        reel_share = item.get("reel_share", {})
        if reel_share and isinstance(reel_share, dict):
            code = code or str(list(reel_share.keys())[:5])
        print(f"    msg {j}: type={itype}, code={code}")

print()
print("=" * 50)
print("2. PENDING INBOX")
print("=" * 50)
r2 = s.get("https://www.instagram.com/api/v1/direct_v2/pending_inbox/", timeout=15)
print(f"Status: {r2.status_code}")
if r2.status_code == 200:
    data2 = r2.json()
    inbox2 = data2.get("inbox", {})
    threads2 = inbox2.get("threads", [])
    print(f"Pending threads: {len(threads2)}")
    for i, t in enumerate(threads2):
        users = t.get("users", [])
        uname = users[0].get("username", "?") if users else "?"
        items = t.get("items", [])
        print(f"  Thread {i}: @{uname} ({len(items)} items)")
        for j, item in enumerate(items[:5]):
            itype = item.get("item_type", "?")
            print(f"    msg {j}: type={itype}")
else:
    print(f"Error: {r2.text[:300]}")

print()
print("=" * 50)
print("3. SPAM INBOX")
print("=" * 50)
r3 = s.get("https://www.instagram.com/api/v1/direct_v2/spam_inbox/", timeout=15)
print(f"Status: {r3.status_code}")
if r3.status_code == 200:
    data3 = r3.json()
    inbox3 = data3.get("inbox", {})
    threads3 = inbox3.get("threads", [])
    print(f"Spam threads: {len(threads3)}")
else:
    print(f"Error: {r3.text[:300]}")
