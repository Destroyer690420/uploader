"""
ig_scraper.py — Instagram Saved Posts Scraper

Mirrors the X (Twitter) bookmark scraper logic:
  - Checks the user's Saved collection on Instagram
  - Finds new video posts not yet in processed_ids.txt
  - Returns them in a standardized format for main.py

Auth:
    Uses instaloader with cookies injected from public/ig_cookies.json
    (exported via a cookie-export Chrome extension).

Usage:
    from ig_scraper import fetch_saved_videos
    videos = fetch_saved_videos(limit=20)
"""

import json
import logging
import os
from pathlib import Path

import instaloader

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
IG_COOKIES_PATH = str(BASE_DIR / "public" / "ig_cookies.json")
PROCESSED_IDS_PATH = str(BASE_DIR / "processed_ids.txt")


# ===================================================================
# 1. Authentication — cookie injection into instaloader
# ===================================================================

def _get_loader(cookies_path: str = IG_COOKIES_PATH) -> instaloader.Instaloader | None:
    """
    Creates an authenticated Instaloader instance by injecting
    browser cookies from ig_cookies.json.

    Returns:
        Authenticated Instaloader instance, or None on failure.
    """
    if not os.path.exists(cookies_path):
        logger.error("[IG Scraper] Cookie file not found: %s", cookies_path)
        return None

    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            raw_cookies = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("[IG Scraper] Failed to read cookies: %s", e)
        return None

    # Validate we have the required cookies
    cookie_names = {c.get("name") for c in raw_cookies}
    if "sessionid" not in cookie_names:
        logger.error("[IG Scraper] No 'sessionid' in cookies — cannot authenticate.")
        return None

    # Initialize instaloader with minimal options (we only need metadata)
    L = instaloader.Instaloader(
        download_comments=False,
        download_geotags=False,
        download_video_thumbnails=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )

    # Inject cookies into instaloader's internal requests session
    for cookie in raw_cookies:
        if "name" in cookie and "value" in cookie:
            L.context._session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ".instagram.com"),
                path=cookie.get("path", "/"),
            )

    # Extract username from ds_user_id for context
    ds_user_id = next(
        (c["value"] for c in raw_cookies if c.get("name") == "ds_user_id"),
        None,
    )

    logger.info(
        "[IG Scraper] Instaloader initialized with %d cookies (ds_user_id=%s)",
        len(raw_cookies), ds_user_id or "unknown",
    )

    return L


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

    Mirrors the X bookmarks scraper (scraper.py) interface.

    Args:
        limit: Maximum number of saved posts to scan.

    Returns:
        List of dicts (newest-first from IG, caller picks oldest):
        [
            {
                "tweet_id":   "SHORTCODE",     # Used as unique ID
                "video_url":  "https://...",    # Direct video URL or reel page URL
                "tweet_text": "caption...",     # Post caption
                "author":     "@username",      # Post owner
                "source":     "instagram",
            },
            ...
        ]
    """
    L = _get_loader()
    if L is None:
        return []

    # Verify authentication and get username
    try:
        username = L.test_login()
    except Exception as e:
        logger.error("[IG Scraper] test_login() failed: %s", e)
        return []

    if not username:
        logger.error("[IG Scraper] Cookie auth failed — test_login() returned None.")
        return []

    logger.info("[IG Scraper] Authenticated as @%s", username)

    # Get the Profile object (get_saved_posts lives on Profile, not Instaloader)
    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except Exception as e:
        logger.error("[IG Scraper] Failed to load profile for @%s: %s", username, e)
        return []

    processed_ids = _load_processed_ids()

    try:
        logger.info("[IG Scraper] Fetching saved posts (limit=%d)...", limit)
        saved_posts = profile.get_saved_posts()
    except Exception as e:
        logger.error("[IG Scraper] Failed to fetch saved posts: %s", e)
        return []

    new_videos: list[dict] = []
    scanned = 0

    try:
        for post in saved_posts:
            if scanned >= limit:
                break
            scanned += 1

            shortcode = post.shortcode

            # Skip already-processed
            if shortcode in processed_ids:
                logger.debug("[IG Scraper] Skipping processed: %s", shortcode)
                continue

            # Filter: only videos
            if not post.is_video:
                logger.debug("[IG Scraper] Skipping non-video: %s", shortcode)
                continue

            # Extract video URL (direct CDN link from instaloader)
            try:
                video_url = post.video_url
            except Exception:
                # Fallback to the reel page URL (yt-dlp can handle this)
                video_url = f"https://www.instagram.com/reel/{shortcode}/"

            # Extract caption safely
            caption = ""
            try:
                caption = post.caption or ""
            except Exception:
                pass

            # Extract owner username safely
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
        "[IG Scraper] Scanned %d saved posts. Found %d new video(s).",
        scanned, len(new_videos),
    )

    return new_videos


# ===================================================================
# CLI test
# ===================================================================

if __name__ == "__main__":
    import sys

    # Fix Windows console encoding
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
