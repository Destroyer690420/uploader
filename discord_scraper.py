"""
discord_scraper.py — Discord Channel Link Scraper

Reads messages from a Discord channel, finds Instagram Reel or
Twitter/X video links, and returns one link per run for the pipeline.

After extracting a link, the message is DELETED from the channel
to act as a simple queue (no duplicate processing).

Auth:
    DISCORD_BOT_TOKEN  — Discord bot token (env var or .env)
    DISCORD_CHANNEL_ID — Channel ID to read from (env var or .env)

Usage:
    from discord_scraper import fetch_discord_links
    video = fetch_discord_links()   # returns dict or None
"""

import logging
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DISCORD_API = "https://discord.com/api/v10"

# Regex patterns for supported video URLs
URL_PATTERNS = [
    # Instagram Reels
    re.compile(r"https?://(?:www\.)?instagram\.com/reel/[\w-]+/?", re.IGNORECASE),
    # Instagram posts (may contain video)
    re.compile(r"https?://(?:www\.)?instagram\.com/p/[\w-]+/?", re.IGNORECASE),
    # Twitter / X video tweets
    re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+", re.IGNORECASE),
]


# ===================================================================
# 1. Discord API helpers
# ===================================================================

def _get_headers() -> dict:
    """Build auth headers from DISCORD_BOT_TOKEN."""
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not token:
        raise ValueError("DISCORD_BOT_TOKEN is not set.")
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }


def _get_channel_id() -> str:
    """Read DISCORD_CHANNEL_ID from env."""
    channel_id = os.getenv("DISCORD_CHANNEL_ID", "")
    if not channel_id:
        raise ValueError("DISCORD_CHANNEL_ID is not set.")
    return channel_id


def _fetch_messages(channel_id: str, limit: int = 50) -> list[dict]:
    """GET the latest messages from a Discord channel."""
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    params = {"limit": limit}
    resp = requests.get(url, headers=_get_headers(), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _delete_message(channel_id: str, message_id: str) -> bool:
    """DELETE a message by ID (acts as queue acknowledgement)."""
    url = f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}"
    try:
        resp = requests.delete(url, headers=_get_headers(), timeout=15)
        if resp.status_code == 204:
            logger.info("[Discord] 🗑️  Deleted message %s", message_id)
            return True
        else:
            logger.warning(
                "[Discord] Delete returned %d for message %s",
                resp.status_code, message_id,
            )
            return False
    except Exception as e:
        logger.error("[Discord] Failed to delete message %s: %s", message_id, e)
        return False


# ===================================================================
# 2. URL extraction
# ===================================================================

def _extract_video_url(text: str) -> str | None:
    """Extract the first Instagram or Twitter video URL from text."""
    if not text:
        return None
    for pattern in URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _determine_source(url: str) -> str:
    """Determine whether a URL is from Instagram or Twitter/X."""
    if "instagram.com" in url.lower():
        return "instagram"
    return "X"


# ===================================================================
# 3. Main API — fetch_discord_links()
# ===================================================================

def fetch_discord_links() -> dict | None:
    """
    Fetches one video link from the Discord channel.

    Scans messages oldest-first. When a video URL is found:
      1. Extracts the URL
      2. Deletes the message (queue management)
      3. Returns a standardized dict

    Returns:
        Dict matching pipeline format, or None if no links found:
        {
            "tweet_id":   "discord_{message_id}",
            "video_url":  "https://...",
            "tweet_text": "message content",
            "author":     "@discord_user",
            "source":     "instagram" or "X",
        }
    """
    try:
        channel_id = _get_channel_id()
        messages = _fetch_messages(channel_id)
    except ValueError as e:
        logger.error("[Discord] Config error: %s", e)
        return None
    except requests.HTTPError as e:
        logger.error("[Discord] API error: %s", e)
        return None
    except Exception as e:
        logger.error("[Discord] Unexpected error fetching messages: %s", e)
        return None

    if not messages:
        logger.info("[Discord] Channel is empty — no messages.")
        return None

    logger.info("[Discord] Fetched %d messages from channel.", len(messages))

    # Messages come newest-first from Discord API.
    # Process OLDEST first to maintain FIFO queue order.
    for msg in reversed(messages):
        msg_id = msg.get("id", "")
        content = msg.get("content", "")
        author_name = msg.get("author", {}).get("username", "unknown")

        # Try to find a video URL in the message content
        video_url = _extract_video_url(content)

        if not video_url:
            # Also check embeds (sometimes links are in embeds, not content)
            for embed in msg.get("embeds", []):
                embed_url = embed.get("url", "")
                video_url = _extract_video_url(embed_url)
                if video_url:
                    break

        if not video_url:
            logger.debug("[Discord] No video URL in message %s, skipping.", msg_id)
            continue

        source = _determine_source(video_url)

        logger.info(
            "[Discord] ✅ Found %s link in message %s by @%s: %s",
            source, msg_id, author_name, video_url,
        )

        # Delete the message to remove it from the queue
        _delete_message(channel_id, msg_id)

        return {
            "tweet_id": f"discord_{msg_id}",
            "video_url": video_url,
            "tweet_text": content[:280] if content else "",
            "author": f"@{author_name}",
            "source": source,
        }

    logger.info("[Discord] No video links found in any message.")
    return None


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

    result = fetch_discord_links()
    if result:
        print(f"\n✅ Found video link:")
        print(f"   ID:     {result['tweet_id']}")
        print(f"   URL:    {result['video_url']}")
        print(f"   Source: {result['source']}")
        print(f"   Author: {result['author']}")
    else:
        print("\n❌ No video links found in Discord channel.")
