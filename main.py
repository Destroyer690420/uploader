"""
main.py — Multi-Source Pipeline Orchestrator

Designed for GitHub Actions: performs exactly ONE upload cycle and exits.
No time.sleep() — the cron schedule handles spacing between runs.

Sources (checked in order):
  1. Discord Bridge — video links posted to a Discord channel (priority)
  2. X Bookmarks — bookmarked video tweets (fallback)

Flow:
  1. Check Discord channel for video links
  2. If no Discord links, scrape X bookmarks
  3. Download the video (yt-dlp with cookies)
  4. Convert to 9:16 vertical format
  5. Upload to YouTube (unlisted) + Instagram (Reel)
  6. Save state + Generate README dashboard
  7. Exit

Usage:
    python main.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding for emoji/unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from scraper import fetch_bookmarked_videos, save_processed_id
from downloader import download_video, cleanup_video, convert_to_vertical
from uploader import upload_video

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
README_PATH = str(BASE_DIR / "README.md")
YT_DAILY_COUNT_PATH = str(BASE_DIR / "yt_daily_count.txt")
YT_DAILY_LIMIT = 6


def timestamp() -> str:
    """Returns a human-readable timestamp for log banners."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def utc_now() -> str:
    """Returns a UTC timestamp for the dashboard."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ===================================================================
# YouTube Daily Limit Tracker (6/day)
# ===================================================================

def _get_yt_daily_count() -> int:
    """Returns how many YouTube uploads have been done today (UTC)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if os.path.exists(YT_DAILY_COUNT_PATH):
            with open(YT_DAILY_COUNT_PATH, "r", encoding="utf-8") as f:
                line = f.read().strip()
            if line:
                date_str, count_str = line.split(":")
                if date_str == today:
                    return int(count_str)
    except Exception:
        pass
    return 0


def _increment_yt_daily_count() -> int:
    """Increments today's YouTube upload count. Returns new count."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current = _get_yt_daily_count()
    new_count = current + 1
    with open(YT_DAILY_COUNT_PATH, "w", encoding="utf-8") as f:
        f.write(f"{today}:{new_count}")
    logger.info("YouTube daily count: %d / %d", new_count, YT_DAILY_LIMIT)
    return new_count


def _yt_limit_reached() -> bool:
    """Returns True if today's YouTube upload limit has been reached."""
    count = _get_yt_daily_count()
    if count >= YT_DAILY_LIMIT:
        logger.info(
            "⏸️  YouTube daily limit reached (%d/%d). Skipping YT upload.",
            count, YT_DAILY_LIMIT,
        )
        return True
    logger.info("YouTube daily count: %d / %d — upload allowed.", count, YT_DAILY_LIMIT)
    return False


# ===================================================================
# Discord Source — check for video links in Discord channel
# ===================================================================

def _try_discord_source() -> dict | None:
    """
    Fetches one video link from the Discord channel.
    Returns a dict or None.
    """
    try:
        from discord_scraper import fetch_discord_links
    except ImportError as e:
        logger.warning("[Source: Discord] discord_scraper module not available: %s", e)
        return None

    logger.info("[Source: Discord] Checking channel for video links...")

    try:
        result = fetch_discord_links()
    except Exception as e:
        logger.error("[Source: Discord] Scraper error: %s", e)
        return None

    if result:
        logger.info(
            "[Source: Discord] Found link: %s (%s)",
            result["video_url"], result["source"],
        )
    else:
        logger.info("[Source: Discord] No video links found.")

    return result


# ===================================================================
# README Dashboard Generator
# ===================================================================

def generate_dashboard(
    status: str = "Idle",
    queue_remaining: int = 0,
    last_tweet_id: str | None = None,
    last_author: str | None = None,
    last_yt_id: str | None = None,
    last_ig_id: str | None = None,
    last_timestamp: str | None = None,
    error_message: str | None = None,
    source: str = "Discord",
) -> None:
    """
    Rewrites README.md as a live dashboard showing pipeline status.
    """
    ts = last_timestamp or utc_now()

    # Status badge
    if status == "Running":
        status_badge = "🟢 **Running**"
    elif status == "Error":
        status_badge = "🔴 **Error**"
    else:
        status_badge = "⚪ **Idle**"

    # Last action section
    if last_tweet_id:
        last_action = f"""| Field | Value |
|---|---|
| **Timestamp** | `{ts}` |
| **Source** | `{source}` |
| **ID** | `{last_tweet_id}` |
| **Author** | {last_author or 'N/A'} |
| **YouTube** | {f'[▶ Watch](https://youtu.be/{last_yt_id})' if last_yt_id else '❌ Failed'} |
| **Instagram** | {f'✅ Media ID `{last_ig_id}`' if last_ig_id else '❌ Failed'} |"""
    else:
        last_action = "_No videos processed yet._"

    # Error section
    if error_message:
        error_section = f"""### 🚨 Recent Errors

```
{error_message}
```"""
    else:
        error_section = "_No recent errors._"

    readme = f"""# 🤖 Auto-Post Pipeline

> Automated multi-source → YouTube + Instagram pipeline powered by GitHub Actions.

---

## 📊 Dashboard

| Metric | Value |
|---|---|
| **Status** | {status_badge} |
| **Queue** | **{queue_remaining}** video(s) waiting |
| **Last Run** | `{utc_now()}` |

---

## 🎬 Last Action

{last_action}

---

## 📋 Error Log

{error_section}

---

## ⚙️ How It Works

1. **Checks** Discord channel for video links (priority source)
2. **Falls back** to X bookmarks for new video tweets
3. **Downloads** the video (yt-dlp with cookies)
4. **Converts** to 9:16 vertical format
5. **Uploads** to YouTube (unlisted) + Instagram (Reel)
6. **Updates** this dashboard automatically

| Module | Purpose |
|---|---|
| `discord_scraper.py` | Fetch video links from Discord channel |
| `scraper.py` | Fetch X bookmarks, extract video URLs |
| `downloader.py` | Download videos (yt-dlp + cookies) |
| `uploader.py` | Upload to YouTube + Instagram |
| `main.py` | Multi-source orchestrator |

---

<sub>Last updated: {utc_now()} · Powered by GitHub Actions</sub>
"""

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(readme)

    logger.info("📄 README dashboard updated.")


# ===================================================================
# Main Pipeline
# ===================================================================

async def run_pipeline() -> None:
    """
    Executes a single upload cycle:
      1. Check Discord → 2. Fallback to X Bookmarks
      3. Download → 4. Convert → 5. Upload → 6. Cleanup
      7. Generate README dashboard
    """
    print("\n" + "=" * 65)
    print(f"  🚀 PIPELINE START — {timestamp()}")
    print("=" * 65)

    error_msg = None
    source = "Discord"
    target = None
    remaining = 0
    video = None

    # ------------------------------------------------------------------
    # STEP 1: Try Discord channel first (priority source)
    # ------------------------------------------------------------------
    logger.info("[%s] STEP 1 — Checking Discord channel...", timestamp())
    discord_result = _try_discord_source()

    if discord_result:
        video = discord_result
        source = discord_result.get("source", "Discord")
        logger.info(
            "[%s] [Source: Discord/%s] Found video link: %s",
            timestamp(), source, video["video_url"],
        )
    else:
        # ------------------------------------------------------------------
        # STEP 2: Fallback to X Bookmarks
        # ------------------------------------------------------------------
        logger.info("[%s] STEP 2 — No Discord links. Scraping X bookmarks...", timestamp())

        try:
            all_videos = await fetch_bookmarked_videos(auto_save=False)
        except Exception as e:
            logger.warning("[%s] X scraper error: %s", timestamp(), e)
            all_videos = []

        if all_videos:
            source = "X"
            video = all_videos[-1]  # oldest unprocessed
            remaining = len(all_videos) - 1
            logger.info(
                "[%s] [Source: X] Found %d unprocessed video(s). Selected: %s",
                timestamp(), len(all_videos), video["tweet_id"],
            )

    # ------------------------------------------------------------------
    # No content from either source
    # ------------------------------------------------------------------
    if not video:
        logger.info("No new content from any source. Exiting gracefully.")
        print(f"\n  ✅ No new videos to process. Pipeline complete at {timestamp()}")
        print(f"  📊 Queue: 0 videos remaining.\n")
        generate_dashboard(status="Idle", queue_remaining=0, source=source)
        return

    logger.info(
        "[%s] [Source: %s] Selected video: %s by %s",
        timestamp(), source, video["tweet_id"], video.get("author", "N/A"),
    )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    logger.info("[%s] [Source: %s] Downloading video...", timestamp(), source)
    local_path = None
    try:
        local_path = download_video(video["video_url"], video["tweet_id"])
    except Exception as e:
        error_msg = f"[Source: {source}] Download failed for {video['tweet_id']}: {e}"
        logger.error(error_msg)

    if not local_path:
        error_msg = error_msg or f"[Source: {source}] Download returned None for {video['tweet_id']}"
        logger.error(
            "❌ [Source: %s] Download failed for %s. "
            "ID NOT saved — will retry next run.",
            source, video["tweet_id"],
        )
        _print_summary(success=False, remaining=remaining + 1, target=video, source=source)
        generate_dashboard(
            status="Error",
            queue_remaining=remaining + 1,
            last_tweet_id=video["tweet_id"],
            last_author=video.get("author"),
            last_timestamp=timestamp(),
            error_message=error_msg,
            source=source,
        )
        return

    target = {**video, "local_path": local_path}

    local_path = target["local_path"]

    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    logger.info(
        "[%s] [Source: %s] Download complete — %.1f MB at %s",
        timestamp(), source, file_size_mb, local_path,
    )

    # ------------------------------------------------------------------
    # STEP 3: Convert to 9:16 vertical (for YouTube Shorts)
    # ------------------------------------------------------------------
    logger.info("[%s] [Source: %s] STEP 3 — Converting to 9:16 vertical...", timestamp(), source)
    vertical_path = convert_to_vertical(local_path)
    if vertical_path:
        local_path = vertical_path
        target["local_path"] = local_path
        logger.info("[%s] Conversion complete → %s", timestamp(), local_path)
    else:
        logger.warning("Conversion failed — uploading original file instead.")

    # ------------------------------------------------------------------
    # STEP 4: Upload to YouTube + Instagram
    # ------------------------------------------------------------------
    yt_allowed = not _yt_limit_reached()

    logger.info("[%s] [Source: %s] STEP 4 — Uploading to platforms...", timestamp(), source)

    try:
        result = upload_video(
            {**target, "local_path": local_path},
            upload_youtube=yt_allowed,
            upload_instagram=True,
        )
    except Exception as e:
        error_msg = f"[Source: {source}] Upload crashed for {target['tweet_id']}: {e}"
        logger.error(error_msg)
        _print_summary(success=False, remaining=remaining + 1, target=target, source=source)
        if local_path:
            cleanup_video(local_path)
        generate_dashboard(
            status="Error",
            queue_remaining=remaining + 1,
            last_tweet_id=target["tweet_id"],
            last_author=target.get("author"),
            last_timestamp=timestamp(),
            error_message=error_msg,
            source=source,
        )
        return

    yt_id = result.get("youtube_id")
    ig_id = result.get("instagram_id")

    yt_ok = yt_id is not None
    ig_ok = ig_id is not None

    # Track YouTube daily count
    if yt_ok:
        _increment_yt_daily_count()

    logger.info(
        "[%s] [Source: %s] Upload results — YouTube: %s | Instagram: %s",
        timestamp(), source,
        f"✅ {yt_id}" if yt_ok else "❌ Failed",
        f"✅ {ig_id}" if ig_ok else "❌ Failed",
    )

    # ------------------------------------------------------------------
    # STEP 5: Cleanup + State Update
    # ------------------------------------------------------------------
    logger.info("[%s] [Source: %s] STEP 5 — Cleanup & state update...", timestamp(), source)

    # Clean up local file IMMEDIATELY after uploads
    if local_path:
        cleanup_video(local_path)

    # Only save ID if AT LEAST ONE upload succeeded
    if yt_ok or ig_ok:
        save_processed_id(target["tweet_id"])
        logger.info("✅ [Source: %s] %s marked as processed.", source, target["tweet_id"])
    else:
        error_msg = (
            f"[Source: {source}] BOTH uploads failed for {target['tweet_id']}. "
            "Will retry next run."
        )
        logger.warning("⚠️  %s", error_msg)
        remaining += 1  # still in queue

    _print_summary(
        success=(yt_ok or ig_ok),
        remaining=remaining,
        target=target,
        yt_id=yt_id,
        ig_id=ig_id,
        source=source,
    )

    # ------------------------------------------------------------------
    # STEP 6: Generate README dashboard
    # ------------------------------------------------------------------
    generate_dashboard(
        status="Idle",
        queue_remaining=remaining,
        last_tweet_id=target["tweet_id"],
        last_author=target.get("author"),
        last_yt_id=yt_id,
        last_ig_id=ig_id,
        last_timestamp=timestamp(),
        error_message=error_msg,
        source=source,
    )


# ===================================================================
# Summary printer
# ===================================================================

def _print_summary(
    success: bool,
    remaining: int,
    target: dict,
    yt_id: str | None = None,
    ig_id: str | None = None,
    source: str = "Discord",
) -> None:
    """Prints a clean end-of-run summary."""
    print(f"\n{'=' * 65}")
    print(f"  {'✅' if success else '❌'} PIPELINE {'COMPLETE' if success else 'FAILED'} — {timestamp()}")
    print(f"{'=' * 65}")
    print(f"  Source   : {source}")
    print(f"  ID       : {target['tweet_id']}")
    print(f"  Author   : {target.get('author', 'N/A')}")
    print(f"  Text     : {target.get('tweet_text', '')[:80]}...")

    if yt_id:
        print(f"  YouTube  : https://youtu.be/{yt_id}")
    if ig_id:
        print(f"  Instagram: Media ID {ig_id}")

    print(f"\n  📊 Queue  : {remaining} video(s) remaining for future runs.")
    print()


# ===================================================================
# Entry point
# ===================================================================

if __name__ == "__main__":
    asyncio.run(run_pipeline())
