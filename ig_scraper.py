"""
ig_scraper.py — Instagram DM Reel Monitor (Pure Web API)

Monitors Direct Messages for shared Reels using the Instagram Web API
with browser cookies (no instagrapi / instaloader).

Auth:
    Loads browser cookies from public/ig_cookies.json
    (exported via a cookie-export Chrome extension).
    Extracts csrftoken for the mark-as-seen POST.

Usage:
    from ig_scraper import get_oldest_unread_reel
    result = get_oldest_unread_reel()
    # result = {"reel_url": "...", "media_pk": "...", ...} or None
"""

import json
import logging
import os
import sys
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
IG_COOKIES_PATH = str(BASE_DIR / "public" / "ig_cookies.json")
PROCESSED_IDS_PATH = str(BASE_DIR / "processed_ids.txt")

# Desktop Chrome User-Agent (must match a real browser)
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

# Instagram Web API endpoints
IG_WEB_BASE = "https://www.instagram.com"
IG_INBOX_UNREAD_URL = f"{IG_WEB_BASE}/api/v1/direct_v2/inbox/?selected_filter=unread"


# ===================================================================
# 1. Cookie Loading & Session Setup
# ===================================================================

def _load_cookies(cookies_path: str = IG_COOKIES_PATH) -> tuple[dict, str, str] | None:
    """
    Loads cookies from ig_cookies.json.

    Returns:
        (cookies_dict, csrftoken, ds_user_id) or None on failure.
        csrftoken is REQUIRED for mark-as-seen.
        ds_user_id is the logged-in user's numeric ID (to filter out own messages).
    """
    if not os.path.exists(cookies_path):
        logger.error("Cookie file not found: %s", cookies_path)
        return None

    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            raw_cookies = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read cookie file %s: %s", cookies_path, e)
        return None

    # Build a {name: value} dict
    cookies_dict = {
        c["name"]: c["value"]
        for c in raw_cookies
        if "name" in c and "value" in c
    }

    if "sessionid" not in cookies_dict:
        logger.error("No 'sessionid' cookie found in %s", cookies_path)
        return None

    csrftoken = cookies_dict.get("csrftoken", "")
    if not csrftoken:
        logger.error("No 'csrftoken' cookie found — mark-as-seen will fail!")
        return None

    ds_user_id = cookies_dict.get("ds_user_id", "")
    if not ds_user_id:
        logger.warning("No 'ds_user_id' cookie — cannot filter outgoing messages.")

    logger.info(
        "[IG Scraper] Loaded %d cookies, csrftoken=%s..., ds_user_id=%s",
        len(cookies_dict), csrftoken[:8], ds_user_id,
    )

    return cookies_dict, csrftoken, ds_user_id


def _build_session(cookies_dict: dict, csrftoken: str) -> requests.Session:
    """
    Builds a requests.Session that mimics the Instagram web interface.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": WEB_USER_AGENT,
        "X-CSRFToken": csrftoken,
        "X-IG-App-ID": "936619743392459",  # Instagram Web App ID
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/direct/inbox/",
        "Accept": "*/*",
    })
    for name, value in cookies_dict.items():
        session.cookies.set(name, value, domain=".instagram.com")

    return session


# ===================================================================
# 2. Helpers
# ===================================================================

def _load_processed_ids() -> set:
    """Load already-processed IDs from processed_ids.txt."""
    if not os.path.exists(PROCESSED_IDS_PATH):
        return set()
    with open(PROCESSED_IDS_PATH, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _extract_reel_url(item: dict) -> str | None:
    """
    Extracts the Reel/video URL from a DM item.

    Checks clip → media_share for video_versions or video_url.
    Returns the best video URL or None.
    """
    media = None

    item_type = item.get("item_type", "")

    if item_type == "clip":
        clip = item.get("clip", {})
        if isinstance(clip, dict):
            media = clip.get("clip", clip)
    elif item_type == "media_share":
        media = item.get("media_share", {})

    if not media or not isinstance(media, dict):
        return None

    # Try video_versions first (array of {url, width, height})
    video_versions = media.get("video_versions", [])
    if video_versions and isinstance(video_versions, list):
        # Pick the highest quality (first is usually best)
        return video_versions[0].get("url")

    # Fallback: direct video_url
    video_url = media.get("video_url")
    if video_url:
        return video_url

    return None


def _extract_shortcode(item: dict) -> str:
    """Extracts the shortcode from a DM item's media."""
    item_type = item.get("item_type", "")
    media = None

    if item_type == "clip":
        clip = item.get("clip", {})
        if isinstance(clip, dict):
            media = clip.get("clip", clip)
    elif item_type == "media_share":
        media = item.get("media_share", {})

    if media and isinstance(media, dict):
        return media.get("code", "") or media.get("shortcode", "")
    return ""


def _extract_media_pk(item: dict) -> str:
    """Extracts the media_pk from a DM item's media."""
    item_type = item.get("item_type", "")
    media = None

    if item_type == "clip":
        clip = item.get("clip", {})
        if isinstance(clip, dict):
            media = clip.get("clip", clip)
    elif item_type == "media_share":
        media = item.get("media_share", {})

    if media and isinstance(media, dict):
        pk = media.get("pk") or media.get("id", "")
        pk = str(pk)
        if "_" in pk:
            pk = pk.split("_")[0]
        return pk
    return ""


def _extract_caption(item: dict) -> str:
    """Extracts the caption text from a DM item's media."""
    item_type = item.get("item_type", "")
    media = None

    if item_type == "clip":
        clip = item.get("clip", {})
        if isinstance(clip, dict):
            media = clip.get("clip", clip)
    elif item_type == "media_share":
        media = item.get("media_share", {})

    if media and isinstance(media, dict):
        caption_obj = media.get("caption")
        if isinstance(caption_obj, dict):
            return caption_obj.get("text", "")
        elif isinstance(caption_obj, str):
            return caption_obj
    return ""


# ===================================================================
# 3. Mark as Seen (THE FIX)
# ===================================================================

def mark_as_seen(
    session: requests.Session,
    thread_id: str,
    item_id: str,
    csrf_token: str,
) -> bool:
    """
    Marks a specific DM item as seen via Instagram's Web API.

    POST /api/v1/direct_v2/threads/{thread_id}/items/{item_id}/seen/

    CRITICAL: Must include x-csrftoken header, proper payload, and
    XMLHttpRequest + Referer headers or Instagram silently ignores it.

    Returns:
        True if marked successfully (200 OK), False otherwise.
    """
    url = f"{IG_WEB_BASE}/api/v1/direct_v2/threads/{thread_id}/items/{item_id}/seen/"

    payload = {
        "action": "mark_seen",
        "thread_id": thread_id,
        "item_id": item_id,
        "use_unified_inbox": "true",
    }

    headers = {
        "x-csrftoken": csrf_token,           # <--- CRITICAL
        "x-requested-with": "XMLHttpRequest",
        "x-instagram-ajax": "1",
        "Referer": "https://www.instagram.com/direct/inbox/",
    }

    try:
        resp = session.post(url, data=payload, headers=headers, timeout=15)

        if resp.status_code == 200:
            logger.info(
                "[IG Scraper] ✅ Mark-as-seen SUCCESS: thread=%s, item=%s (HTTP 200)",
                thread_id, item_id,
            )
            return True
        else:
            logger.error(
                "[IG Scraper] ❌ Mark-as-seen FAILED: HTTP %d — %s",
                resp.status_code, resp.text[:300],
            )
            return False
    except Exception as e:
        logger.error("[IG Scraper] ❌ Mark-as-seen exception: %s", e)
        return False


# ===================================================================
# 4. Main API — get_oldest_unread_reel()
# ===================================================================

def get_oldest_unread_reel(cookies_path: str = IG_COOKIES_PATH) -> dict | None:
    """
    Finds the oldest unread Reel in Instagram DMs and marks it as seen.

    Flow:
      1. Load cookies, extract csrftoken + ds_user_id
      2. Build authenticated requests.Session
      3. GET /inbox/?selected_filter=unread
      4. Flatten all items across all threads
      5. Filter: only clip/media_share items NOT sent by me
      6. Sort by timestamp ascending (oldest → newest)
      7. Skip already-processed IDs (backup dedup)
      8. Pick the FIRST (oldest) unread reel
      9. Mark it as seen — if this fails, return None (prevent loop)
     10. Return reel info with URL

    Returns:
        Dict with keys: reel_url, media_pk, shortcode, caption, sender,
                        thread_id, item_id, tweet_id (unified ID)
        or None if no unprocessed Reel found or mark-as-seen failed.
    """
    # --- Step 1: Load cookies ---
    cookie_data = _load_cookies(cookies_path)
    if cookie_data is None:
        return None

    cookies_dict, csrftoken, my_user_id = cookie_data

    # --- Step 2: Build session ---
    session = _build_session(cookies_dict, csrftoken)

    # --- Step 3: Fetch unread inbox ---
    try:
        r = session.get(IG_INBOX_UNREAD_URL, timeout=15)
        if r.status_code != 200:
            logger.error(
                "[IG Scraper] Inbox request failed: HTTP %d — %s",
                r.status_code, r.text[:300],
            )
            return None
    except Exception as e:
        logger.error("[IG Scraper] Failed to fetch inbox: %s", e)
        return None

    try:
        data = r.json()
    except json.JSONDecodeError:
        logger.error("[IG Scraper] Inbox returned non-JSON response.")
        return None

    inbox = data.get("inbox", {})
    threads = inbox.get("threads", [])

    if not threads:
        logger.info("[IG Scraper] No unread DM threads found.")
        return None

    # --- Step 4 & 5: Flatten + Filter ---
    all_reels = []

    for thread in threads:
        thread_id = str(thread.get("thread_id", ""))
        items = thread.get("items", [])

        # Get sender info from thread users
        sender = ""
        users = thread.get("users", [])
        if users:
            sender = users[0].get("username", "")

        for item in items:
            item_type = item.get("item_type", "")

            # FILTER: Only clip (Reel) or media_share
            if item_type not in ("clip", "media_share"):
                continue

            # FILTER: Skip messages sent by ME (outgoing)
            item_user_id = str(item.get("user_id", ""))
            if my_user_id and item_user_id == my_user_id:
                logger.debug(
                    "[IG Scraper] Skipping outgoing message (user_id=%s)",
                    item_user_id,
                )
                continue

            # Extract reel URL
            reel_url = _extract_reel_url(item)
            if not reel_url:
                continue

            media_pk = _extract_media_pk(item)
            shortcode = _extract_shortcode(item)
            caption = _extract_caption(item)

            all_reels.append({
                "reel_url": reel_url,
                "media_pk": media_pk,
                "shortcode": shortcode,
                "caption": caption,
                "sender": sender,
                "timestamp": item.get("timestamp", 0),
                "thread_id": thread_id,
                "item_id": str(item.get("item_id", "")),
            })

    if not all_reels:
        logger.info("[IG Scraper] No shared Reels found in unread DMs.")
        return None

    # --- Step 6: Sort oldest-first ---
    all_reels.sort(key=lambda r: int(r.get("timestamp", 0)))

    logger.info(
        "[IG Scraper] Found %d Reel(s) in unread DMs. Checking for unprocessed...",
        len(all_reels),
    )

    # --- Step 7: Skip already-processed ---
    processed = _load_processed_ids()

    for reel in all_reels:
        reel_id = f"ig_{reel['media_pk']}"

        if reel_id in processed:
            logger.debug(
                "[IG Scraper] Skipping already-processed Reel %s (%s)",
                reel["shortcode"], reel_id,
            )
            continue

        # --- Step 8: Found our target ---
        logger.info(
            "[IG Scraper] 🎯 Oldest unread reel: shortcode=%s (pk=%s) from @%s "
            "[thread=%s, item=%s]",
            reel["shortcode"], reel["media_pk"],
            reel["sender"], reel["thread_id"], reel["item_id"],
        )

        # --- Step 9: Mark as seen BEFORE returning ---
        seen_ok = mark_as_seen(
            session, reel["thread_id"], reel["item_id"], csrftoken
        )

        if not seen_ok:
            logger.error(
                "[IG Scraper] ❌ Mark-as-seen failed for item %s. "
                "NOT returning this reel to prevent infinite loop.",
                reel["item_id"],
            )
            return None

        # --- Step 10: Return reel info ---
        return {
            "reel_url": reel["reel_url"],
            "media_pk": reel["media_pk"],
            "shortcode": reel["shortcode"],
            "caption": reel["caption"],
            "sender": reel["sender"],
            "thread_id": reel["thread_id"],
            "item_id": reel["item_id"],
            "tweet_id": f"ig_{reel['media_pk']}",  # Unified ID for processed_ids.txt
        }

    logger.info("[IG Scraper] All %d Reel(s) in DMs already processed.", len(all_reels))
    return None


# ===================================================================
# CLI test
# ===================================================================

if __name__ == "__main__":
    # Fix Windows console encoding
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = get_oldest_unread_reel()
    if result:
        print(f"\n✅ Reel found!")
        print(f"   shortcode : {result['shortcode']}")
        print(f"   media_pk  : {result['media_pk']}")
        print(f"   caption   : {result['caption'][:80]}...")
        print(f"   sender    : @{result['sender']}")
        print(f"   reel_url  : {result['reel_url'][:100]}...")
        print(f"   marked    : SEEN ✅")
    else:
        print("\n❌ No Reels in DMs (or mark-as-seen failed).")
