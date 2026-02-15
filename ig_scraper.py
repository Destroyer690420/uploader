"""
ig_scraper.py — Instagram DM Reel Monitor (Web-Based)

Monitors Direct Messages on the Instagram account for shared Reels.
Uses Instaloader for downloading and raw requests (web API) for DM access.

This avoids Instagram's Mobile API entirely — uses the Web API with
browser cookies exported to public/ig_cookies.json.

Auth:
    Loads browser cookies from public/ig_cookies.json
    (exported via a cookie-export Chrome extension).

Usage:
    from ig_scraper import get_client, get_latest_dm_reel
    session, loader = get_client()
    result = get_latest_dm_reel(session)
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

# Desktop Chrome User-Agent (must match a real browser)
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

# Instagram Web API endpoints
IG_INBOX_URL = "https://www.instagram.com/api/v1/direct_v2/inbox/"
IG_WEB_BASE = "https://www.instagram.com"


# ===================================================================
# 1. Authentication — cookie file + requests session
# ===================================================================

def get_client(cookies_path: str = IG_COOKIES_PATH):
    """
    Creates and returns:
      - An authenticated requests.Session for the Instagram Web API
      - An Instaloader instance for downloading posts

    Loads browser cookies from ig_cookies.json.

    Returns:
        Tuple of (requests.Session, instaloader.Instaloader) or (None, None).
    """
    if not os.path.exists(cookies_path):
        logger.error("Cookie file not found: %s", cookies_path)
        return None, None

    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            raw_cookies = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read cookie file %s: %s", cookies_path, e)
        return None, None

    # Build a {name: value} dict
    cookies_dict = {
        c["name"]: c["value"]
        for c in raw_cookies
        if "name" in c and "value" in c
    }

    if "sessionid" not in cookies_dict:
        logger.error("No 'sessionid' cookie found in %s", cookies_path)
        return None, None

    logger.info(
        "Loaded %d cookies from %s", len(cookies_dict), cookies_path
    )

    # --- Build requests.Session for Web API (DMs) ---
    session = requests.Session()
    session.headers.update({
        "User-Agent": WEB_USER_AGENT,
        "X-CSRFToken": cookies_dict.get("csrftoken", ""),
        "X-IG-App-ID": "936619743392459",  # Instagram Web App ID
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/direct/inbox/",
        "Accept": "*/*",
    })
    for name, value in cookies_dict.items():
        session.cookies.set(name, value, domain=".instagram.com")

    # Verify session by hitting the DM inbox (avoids useragent mismatch
    # on the accounts/current_user endpoint which is UA-locked)
    try:
        r = session.get(IG_INBOX_URL, timeout=15)
        if r.status_code == 200:
            logger.info("Instagram web session verified (DM inbox OK).")
        else:
            logger.warning(
                "Instagram session check returned %d — DMs may not work.",
                r.status_code,
            )
    except Exception as e:
        logger.warning("Could not verify IG web session: %s", e)

    # --- Build Instaloader for downloading ---
    try:
        import instaloader
        L = instaloader.Instaloader(
            download_comments=False,
            download_geotags=False,
            download_video_thumbnails=False,
            save_metadata=False,
            post_metadata_txt_pattern="",
        )
        # Inject cookies into instaloader's internal session
        for cookie in raw_cookies:
            L.context._session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ".instagram.com"),
                path=cookie.get("path", "/"),
            )
        logger.info("Instaloader session initialized with cookies.")
    except ImportError:
        logger.warning("instaloader not installed — downloads will fail.")
        L = None

    return session, L


# ===================================================================
# 2. DM Monitor — find oldest unread Reel (via Web API)
# ===================================================================

IG_INBOX_UNREAD_URL = IG_INBOX_URL + "?selected_filter=unread"


def _load_processed_ids() -> set:
    """Load already-processed IDs from processed_ids.txt."""
    ids_file = str(BASE_DIR / "processed_ids.txt")
    if not os.path.exists(ids_file):
        return set()
    with open(ids_file, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _extract_reel_from_item(item: dict) -> dict | None:
    """Try to extract Reel info from a single DM message item."""
    media = None
    media_source = None

    # Method 1: clip (shared Reel)
    clip = item.get("clip", {})
    if clip and isinstance(clip, dict) and clip.get("clip"):
        media = clip["clip"]
        media_source = "clip"

    # Method 2: media_share (shared post/reel)
    if media is None:
        media_share = item.get("media_share", {})
        if media_share and isinstance(media_share, dict):
            media = media_share
            media_source = "media_share"

    # Method 3: felix_share (IGTV / Reel share)
    if media is None:
        felix = item.get("felix_share", {})
        if felix and isinstance(felix, dict) and felix.get("video"):
            media = felix["video"]
            media_source = "felix_share"

    if media is None:
        return None

    # Extract shortcode
    shortcode = media.get("code") or media.get("shortcode")
    if not shortcode:
        return None

    # Extract media_pk
    media_pk = media.get("pk") or media.get("id", "")
    if isinstance(media_pk, str) and "_" in media_pk:
        media_pk = media_pk.split("_")[0]

    # Extract caption
    caption = ""
    caption_obj = media.get("caption")
    if isinstance(caption_obj, dict):
        caption = caption_obj.get("text", "")
    elif isinstance(caption_obj, str):
        caption = caption_obj

    return {
        "shortcode": shortcode,
        "media_pk": str(media_pk),
        "caption": caption,
        "media_source": media_source,
    }


def mark_dm_seen(
    session: requests.Session,
    thread_id: str,
    item_id: str,
) -> bool:
    """
    Marks a specific DM item as seen via Instagram's Web API.

    POST /api/v1/direct_v2/threads/{thread_id}/items/{item_id}/seen/

    Args:
        session: Authenticated requests.Session with cookies + headers.
        thread_id: The DM thread ID.
        item_id: The specific message item ID.

    Returns:
        True if marked successfully, False otherwise.
    """
    url = (
        f"{IG_WEB_BASE}/api/v1/direct_v2/threads/"
        f"{thread_id}/items/{item_id}/seen/"
    )

    try:
        r = session.post(url, timeout=15)
        if r.status_code == 200:
            logger.info(
                "Marked DM item %s in thread %s as seen.",
                item_id, thread_id,
            )
            return True
        else:
            logger.warning(
                "Mark-as-seen returned %d: %s",
                r.status_code, r.text[:200],
            )
            return False
    except Exception as e:
        logger.warning("Failed to mark DM as seen: %s", e)
        return False


def get_latest_dm_reel(session: requests.Session) -> dict | None:
    """
    Scans UNREAD DMs for the oldest unprocessed shared Reel.

    Flow:
      1. Fetch inbox with ?selected_filter=unread
      2. Collect ALL Reel messages across all threads
      3. Sort oldest-first (by timestamp)
      4. Skip any already in processed_ids.txt (backup dedup)
      5. Return the first unprocessed one with thread_id + item_id

    Returns:
        Dict with keys {shortcode, media_pk, caption, sender,
                        thread_id, item_id}
        or None if no unprocessed Reel found.
    """
    # Try unread filter first, fall back to full inbox
    try:
        r = session.get(IG_INBOX_UNREAD_URL, timeout=15)
        if r.status_code != 200:
            logger.warning(
                "Unread inbox filter returned %d, falling back to full inbox.",
                r.status_code,
            )
            r = session.get(IG_INBOX_URL, timeout=15)
    except Exception as e:
        logger.error("Failed to fetch DM inbox: %s", e)
        return None

    if r.status_code != 200:
        logger.error(
            "DM inbox request failed with status %d: %s",
            r.status_code,
            r.text[:300],
        )
        return None

    try:
        data = r.json()
    except json.JSONDecodeError:
        logger.error("DM inbox returned non-JSON response.")
        return None

    inbox = data.get("inbox", {})
    threads = inbox.get("threads", [])

    if not threads:
        logger.info("No unread DM threads found.")
        return None

    # Load already-processed IDs (backup dedup layer)
    processed = _load_processed_ids()

    # Collect ALL reels from ALL threads with timestamps + IDs
    all_reels = []

    for thread in threads:
        thread_id = str(thread.get("thread_id", ""))
        items = thread.get("items", [])
        sender = ""
        users = thread.get("users", [])
        if users:
            sender = users[0].get("username", "")

        for item in items:
            reel = _extract_reel_from_item(item)
            if reel is None:
                continue

            # Add metadata for tracking
            reel["sender"] = sender
            reel["timestamp"] = item.get("timestamp", 0)
            reel["thread_id"] = thread_id
            reel["item_id"] = str(item.get("item_id", ""))

            all_reels.append(reel)

    if not all_reels:
        logger.info("No shared Reels found in unread DMs.")
        return None

    # Sort oldest-first (smallest timestamp = oldest)
    all_reels.sort(key=lambda r: int(r.get("timestamp", 0)))

    logger.info(
        "Found %d Reel(s) in unread DMs. Checking for unprocessed...",
        len(all_reels),
    )

    for reel in all_reels:
        reel_id = f"ig_{reel['media_pk']}"
        if reel_id in processed:
            logger.debug(
                "Skipping already-processed Reel %s (%s)",
                reel["shortcode"], reel_id,
            )
            continue

        logger.info(
            "Found unprocessed Reel! shortcode=%s (pk=%s) from @%s "
            "[thread=%s, item=%s, via %s]",
            reel["shortcode"], reel["media_pk"],
            reel["sender"], reel["thread_id"],
            reel["item_id"], reel["media_source"],
        )
        # Remove internal keys before returning
        reel.pop("timestamp", None)
        reel.pop("media_source", None)
        return reel

    logger.info("All %d Reel(s) in DMs already processed.", len(all_reels))
    return None


# ===================================================================
# 3. Download a Reel by shortcode (via Instaloader)
# ===================================================================

def download_reel_by_shortcode(
    loader,
    shortcode: str,
    target_dir: str = str(BASE_DIR / "temp_videos"),
) -> str | None:
    """
    Downloads a Reel using Instaloader by its shortcode.

    Args:
        loader: Authenticated instaloader.Instaloader instance.
        shortcode: The Reel's shortcode (e.g., 'C1a2B3c4D5e').
        target_dir: Directory to save into.

    Returns:
        Path to the downloaded video file, or None on failure.
    """
    if loader is None:
        logger.error("Instaloader not available — cannot download.")
        return None

    os.makedirs(target_dir, exist_ok=True)

    try:
        import instaloader
        post = instaloader.Post.from_shortcode(loader.context, shortcode)

        logger.info(
            "Downloading Reel: %s (type: %s)", shortcode, post.typename
        )

        # Get the video URL directly from the Post object
        video_url = post.video_url
        if not video_url:
            logger.error("No video URL found for Reel %s", shortcode)
            return None

        # Download the video with requests to a known path
        output_path = os.path.join(target_dir, f"ig_{shortcode}.mp4")

        resp = requests.get(video_url, stream=True, timeout=60)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = os.path.getsize(output_path)
        logger.info(
            "Downloaded Reel to: %s (%.1f MB)",
            output_path, file_size / 1024 / 1024,
        )
        return output_path

    except Exception as e:
        logger.error("Error downloading Reel %s: %s", shortcode, e)
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

    session, loader = get_client()
    if session:
        result = get_latest_dm_reel(session)
        if result:
            print(f"\nReel found!")
            print(f"   shortcode: {result['shortcode']}")
            print(f"   media_pk:  {result['media_pk']}")
            print(f"   caption:   {result['caption'][:80]}...")
            print(f"   sender:    @{result['sender']}")
        else:
            print("\nNo Reels in DMs.")
    else:
        print("\nFailed to authenticate.")
