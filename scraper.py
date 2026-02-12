"""
scraper.py — Twitter/X Bookmark Video Scraper

Authenticates via cookies.json, fetches bookmarks, identifies video tweets,
and extracts the highest-quality video URL for each. Maintains processed_ids.txt
to avoid duplicate processing.

Usage:
    python scraper.py
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from twikit import Client
from twikit.media import Video

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (defaults — can be overridden when calling functions)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_COOKIES_PATH = str(BASE_DIR / "public" / "cookies.json")
DEFAULT_PROCESSED_PATH = str(BASE_DIR / "processed_ids.txt")
DEFAULT_BOOKMARK_COUNT = 20


# ===================================================================
# 1. State helpers — read / write processed tweet IDs
# ===================================================================

def load_processed_ids(path: str = DEFAULT_PROCESSED_PATH) -> set[str]:
    """
    Reads processed_ids.txt and returns a set of tweet IDs
    that have already been handled.
    """
    if not os.path.exists(path):
        logger.info("No processed_ids file found at %s — starting fresh.", path)
        return set()

    with open(path, "r", encoding="utf-8") as f:
        ids = {line.strip() for line in f if line.strip()}

    logger.info("Loaded %d processed IDs from %s", len(ids), path)
    return ids


def save_processed_id(tweet_id: str, path: str = DEFAULT_PROCESSED_PATH) -> None:
    """
    Appends a single tweet ID to the processed_ids file.
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{tweet_id}\n")
    logger.debug("Saved tweet ID %s to %s", tweet_id, path)


# ===================================================================
# 2. Video extraction — pull highest-bitrate URL from a Tweet
# ===================================================================

def get_video_url(tweet) -> str | None:
    """
    Inspects a Tweet's media attachments and returns the URL of the
    highest-bitrate video stream, or None if no video is present.
    """
    if not tweet.media:
        return None

    for media in tweet.media:
        if isinstance(media, Video):
            streams = media.streams
            if not streams:
                continue

            # Filter out non-mp4 streams (e.g. m3u8 playlists) and pick
            # the one with the highest bitrate.
            mp4_streams = [
                s for s in streams
                if s.content_type and "video/mp4" in s.content_type
            ]

            if not mp4_streams:
                # Fallback: use all streams if none are explicitly mp4
                mp4_streams = streams

            best = max(mp4_streams, key=lambda s: s.bitrate or 0)
            logger.info(
                "Found video for tweet %s — bitrate=%s, url=%s",
                tweet.id,
                best.bitrate,
                best.url[:80] + "..." if len(best.url) > 80 else best.url,
            )
            return best.url

    return None


# ===================================================================
# 3. Orchestrator — fetch bookmarks and return new video entries
# ===================================================================

async def fetch_bookmarked_videos(
    cookies_path: str = DEFAULT_COOKIES_PATH,
    processed_path: str = DEFAULT_PROCESSED_PATH,
    count: int = DEFAULT_BOOKMARK_COUNT,
    auto_save: bool = True,
) -> list[dict]:
    """
    Main scraper logic:
      1. Load cookies & authenticate the twikit Client.
      2. Fetch the latest bookmarks.
      3. Skip tweets already in processed_ids.txt.
      4. Extract video URLs from remaining tweets.
      5. Return a list of dicts ready for the Downloader module.

    Args:
        auto_save: If True (default), automatically saves processed IDs.
                   Set to False when main.py needs to control state
                   (e.g. save only after successful upload).

    Returns:
        [
            {
                "tweet_id":   "123456789",
                "video_url":  "https://video.twimg.com/...",
                "tweet_text": "Check this out!",
                "author":     "@username",
            },
            ...
        ]
    """
    # --- Authenticate ---
    client = Client()
    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Browser-export format: list of {"name": ..., "value": ..., ...}
        # twikit format: flat dict {"name": "value", ...}
        if isinstance(raw, list):
            cookie_dict = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
            logger.info("Converted %d browser cookies to twikit format.", len(cookie_dict))
        elif isinstance(raw, dict):
            cookie_dict = raw
        else:
            raise ValueError(f"Unexpected cookies.json format: {type(raw)}")

        client.set_cookies(cookie_dict)
        logger.info("Cookies loaded from %s", cookies_path)
    except Exception as e:
        logger.error("Failed to load cookies from %s: %s", cookies_path, e)
        return []

    # --- Fetch bookmarks ---
    try:
        bookmarks = await client.get_bookmarks(count=count)
        logger.info("Fetched %d bookmarks.", len(bookmarks))
    except Exception as e:
        logger.error("Failed to fetch bookmarks: %s", e)
        return []

    # --- Process bookmarks ---
    processed_ids = load_processed_ids(processed_path)
    new_videos: list[dict] = []

    for tweet in bookmarks:
        try:
            # Skip already-processed tweets
            if tweet.id in processed_ids:
                logger.debug("Skipping already-processed tweet %s", tweet.id)
                continue

            # Extract video URL
            video_url = get_video_url(tweet)
            if video_url is None:
                logger.debug("Tweet %s has no video — skipping.", tweet.id)
                # Always mark non-video tweets so we don't re-check next run
                save_processed_id(tweet.id, processed_path)
                continue

            # Build result entry
            author = f"@{tweet.user.screen_name}" if tweet.user else "unknown"
            entry = {
                "tweet_id": tweet.id,
                "video_url": video_url,
                "tweet_text": (tweet.text or "")[:280],
                "author": author,
            }
            new_videos.append(entry)

            # Only auto-save video IDs when caller doesn't need control
            if auto_save:
                save_processed_id(tweet.id, processed_path)
            logger.info(
                "✅ New video queued — tweet %s by %s", tweet.id, author
            )

        except Exception as e:
            logger.error(
                "⚠️  Error processing tweet %s: %s — skipping.",
                getattr(tweet, "id", "???"),
                e,
            )
            continue

    logger.info(
        "Scraping complete. %d new video(s) found out of %d bookmarks.",
        len(new_videos),
        len(bookmarks),
    )
    return new_videos


# ===================================================================
# 4. CLI entry point
# ===================================================================

async def main() -> None:
    """Runs the scraper and prints results."""
    logger.info("🚀 Starting X Bookmark Video Scraper...")

    videos = await fetch_bookmarked_videos()

    if not videos:
        logger.info("No new videos found. Exiting.")
        return

    print("\n" + "=" * 60)
    print(f"  Found {len(videos)} new video(s)")
    print("=" * 60)
    for i, v in enumerate(videos, 1):
        print(f"\n  [{i}] Tweet ID : {v['tweet_id']}")
        print(f"      Author   : {v['author']}")
        print(f"      Text     : {v['tweet_text'][:100]}...")
        print(f"      Video URL: {v['video_url'][:100]}...")
    print()


if __name__ == "__main__":
    asyncio.run(main())
