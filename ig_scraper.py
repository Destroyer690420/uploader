"""
ig_scraper.py — Instagram Saved Posts Scraper

Fetches saved video posts using instaloader with cookie auth.
Avoids rate limits by NOT calling Profile.from_username() — instead
constructs a lazy Profile object directly from the ds_user_id cookie.

Auth:
    Loads browser cookies from public/ig_cookies.json
    (exported via a cookie-export Chrome extension).

Usage:
    from ig_scraper import fetch_saved_videos
    videos = fetch_saved_videos(limit=20)
"""

import json
import logging
import os
from itertools import islice
from pathlib import Path

import instaloader

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
IG_COOKIES_PATH = str(BASE_DIR / "public" / "ig_cookies.json")
PROCESSED_IDS_PATH = str(BASE_DIR / "processed_ids.txt")

# Must match a real browser to avoid blocks
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ===================================================================
# 1. Cookie Loading
# ===================================================================

def _load_cookies() -> tuple[dict, str]:
    """
    Loads cookies from ig_cookies.json and extracts ds_user_id.

    Returns:
        (cookies_dict, ds_user_id)

    Raises:
        FileNotFoundError: if cookie file missing
        ValueError: if ds_user_id not found in cookies
    """
    if not os.path.exists(IG_COOKIES_PATH):
        raise FileNotFoundError(f"Cookie file not found: {IG_COOKIES_PATH}")

    with open(IG_COOKIES_PATH, "r", encoding="utf-8") as f:
        raw_cookies = json.load(f)

    # Build a {name: value} dict for injection
    cookies_dict = {}
    ds_user_id = None

    for c in raw_cookies:
        name = c.get("name")
        value = c.get("value")
        if name and value:
            cookies_dict[name] = value
            if name == "ds_user_id":
                ds_user_id = value

    if not ds_user_id:
        raise ValueError(
            "CRITICAL: 'ds_user_id' cookie not found in ig_cookies.json. "
            "Cannot identify user. Re-export cookies from a logged-in browser."
        )

    if "sessionid" not in cookies_dict:
        raise ValueError("No 'sessionid' cookie found — cannot authenticate.")

    logger.info(
        "[IG Scraper] Loaded %d cookies, ds_user_id=%s",
        len(cookies_dict), ds_user_id,
    )

    return cookies_dict, ds_user_id


# ===================================================================
# 2. Helpers
# ===================================================================

def _load_processed_ids() -> set:
    """Load already-processed IDs from processed_ids.txt."""
    if not os.path.exists(PROCESSED_IDS_PATH):
        return set()
    with open(PROCESSED_IDS_PATH, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


# ===================================================================
# 3. Main API — fetch_saved_videos()
# ===================================================================

def fetch_saved_videos(limit: int = 20) -> list[dict]:
    """
    Fetches saved posts from Instagram, filters for videos,
    and returns unprocessed ones in a standardized format.

    Uses a lazy Profile construction to avoid the web_profile_info
    API call that triggers 429 rate limits.

    Args:
        limit: Maximum number of saved posts to scan.

    Returns:
        List of dicts (newest-first, caller picks oldest):
        [
            {
                "tweet_id":   "SHORTCODE",
                "video_url":  "https://...",
                "tweet_text": "caption...",
                "author":     "@username",
                "source":     "instagram",
            },
            ...
        ]
    """
    # --- Step 1: Load cookies and get user ID ---
    try:
        cookies_dict, ds_user_id = _load_cookies()
    except (FileNotFoundError, ValueError) as e:
        logger.error("[IG Scraper] %s", e)
        return []

    # --- Step 2: Initialize instaloader with custom User-Agent ---
    L = instaloader.Instaloader(
        download_comments=False,
        download_geotags=False,
        download_video_thumbnails=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
        user_agent=WEB_USER_AGENT,
    )

    # --- Step 3: Inject cookies into instaloader's session ---
    for name, value in cookies_dict.items():
        L.context._session.cookies.set(
            name, value,
            domain=".instagram.com",
            path="/",
        )

    # --- Step 4: Verify auth via test_login() ---
    try:
        username = L.test_login()
    except Exception as e:
        logger.error("[IG Scraper] test_login() failed: %s", e)
        return []

    if not username:
        logger.error(
            "[IG Scraper] Session invalid — test_login() returned None. "
            "Cookies may be expired. Re-export from browser."
        )
        return []

    logger.info("[IG Scraper] Authenticated as @%s (id=%s)", username, ds_user_id)

    # --- Step 5: Construct lazy Profile (NO web_profile_info call) ---
    # This avoids the extra API request that triggers 429 rate limits.
    # We feed instaloader a minimal node dict with the username and id
    # we already have from cookies + test_login().
    try:
        profile = instaloader.Profile(
            L.context,
            {"username": username, "id": ds_user_id},
        )
    except Exception as e:
        logger.error("[IG Scraper] Failed to construct Profile: %s", e)
        return []

    # --- Step 6: Fetch saved posts ---
    try:
        logger.info("[IG Scraper] Fetching saved posts (limit=%d)...", limit)
        saved_posts = profile.get_saved_posts()
    except Exception as e:
        logger.error("[IG Scraper] Failed to fetch saved posts: %s", e)
        return []

    # --- Step 7: Iterate, filter, deduplicate ---
    processed_ids = _load_processed_ids()
    new_videos: list[dict] = []

    try:
        for post in islice(saved_posts, limit):
            shortcode = post.shortcode

            # Skip already-processed
            if shortcode in processed_ids:
                logger.debug("[IG Scraper] Skipping processed: %s", shortcode)
                continue

            # Filter: only videos
            if not post.is_video:
                logger.debug("[IG Scraper] Skipping non-video: %s", shortcode)
                continue

            # Extract video URL
            try:
                video_url = post.video_url
            except Exception:
                video_url = f"https://www.instagram.com/reel/{shortcode}/"

            # Extract caption
            caption = ""
            try:
                caption = post.caption or ""
            except Exception:
                pass

            # Extract author
            author = "unknown"
            try:
                author = f"@{post.owner_username}"
            except Exception:
                pass

            entry = {
                "tweet_id": shortcode,
                "video_url": video_url,
                "tweet_text": caption[:280] if caption else "",
                "author": author,
                "source": "instagram",
            }
            new_videos.append(entry)
            logger.info(
                "[IG Scraper] ✅ New saved video: %s by %s",
                shortcode, author,
            )

    except Exception as e:
        logger.error("[IG Scraper] Error iterating saved posts: %s", e)

    logger.info(
        "[IG Scraper] Found %d new video(s) in saved posts.",
        len(new_videos),
    )

    return new_videos


# ===================================================================
# CLI test
# ===================================================================

if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    videos = fetch_saved_videos(limit=10)
    if videos:
        print(f"\n✅ Found {len(videos)} saved video(s):")
        for v in videos:
            print(f"   {v['tweet_id']} by {v['author']} — {v['tweet_text'][:60]}...")
    else:
        print("\n❌ No new saved videos found.")
