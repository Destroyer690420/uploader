"""
main.py — Single-Cycle Pipeline Orchestrator

Designed for GitHub Actions: performs exactly ONE upload cycle and exits.
No time.sleep() — the cron schedule handles spacing between runs.

Flow:
  1. Scrape bookmarks (auto_save=False so we control state)
  2. Pick the single OLDEST unprocessed video
  3. Download → Upload (YouTube + Instagram) → Cleanup
  4. Save ID to processed_ids.txt ONLY after successful upload
  5. Generate README.md dashboard
  6. Exit

Usage:
    python main.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scraper import fetch_bookmarked_videos, save_processed_id
from downloader import download_video, cleanup_video
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
| **Tweet ID** | `{last_tweet_id}` |
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

> Automated Bookmark → YouTube + Instagram pipeline powered by GitHub Actions.

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

1. **Scrapes** X bookmarks for new videos every 2 hours
2. **Downloads** the oldest unprocessed video via `yt-dlp`
3. **Uploads** to YouTube (unlisted) + Instagram (Reel)
4. **Updates** this dashboard automatically

| Module | Purpose |
|---|---|
| `scraper.py` | Fetch X bookmarks, extract video URLs |
| `downloader.py` | Download videos via yt-dlp |
| `uploader.py` | Upload to YouTube + Instagram |
| `main.py` | Single-cycle orchestrator |

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
      1. Scrape → 2. Pick oldest → 3. Download → 4. Upload → 5. Cleanup
      6. Generate README dashboard
    """
    print("\n" + "=" * 65)
    print(f"  🚀 PIPELINE START — {timestamp()}")
    print("=" * 65)

    error_msg = None

    # ------------------------------------------------------------------
    # STEP 1: Scrape bookmarks (don't auto-save video IDs)
    # ------------------------------------------------------------------
    logger.info("[%s] STEP 1 — Scraping bookmarks...", timestamp())

    try:
        all_videos = await fetch_bookmarked_videos(auto_save=False)
    except Exception as e:
        error_msg = f"Fatal scraper error: {e}"
        logger.error(error_msg)
        generate_dashboard(status="Error", error_message=error_msg)
        sys.exit(1)

    if not all_videos:
        logger.info("No new bookmarks found. Exiting gracefully.")
        print(f"\n  ✅ No new videos to process. Pipeline complete at {timestamp()}")
        print(f"  📊 Queue: 0 videos remaining.\n")
        generate_dashboard(status="Idle", queue_remaining=0)
        return

    logger.info(
        "[%s] Scraper found %d unprocessed video(s).",
        timestamp(), len(all_videos),
    )

    # ------------------------------------------------------------------
    # STEP 2: Pick the OLDEST unprocessed video (last in list = oldest bookmark)
    # ------------------------------------------------------------------
    target = all_videos[-1]  # bookmarks are newest-first, so last = oldest
    remaining = len(all_videos) - 1

    logger.info(
        "[%s] STEP 2 — Selected oldest video: tweet %s by %s",
        timestamp(), target["tweet_id"], target["author"],
    )

    # ------------------------------------------------------------------
    # STEP 3: Download
    # ------------------------------------------------------------------
    logger.info("[%s] STEP 3 — Downloading video...", timestamp())

    local_path = None
    try:
        local_path = download_video(target["video_url"], target["tweet_id"])
    except Exception as e:
        error_msg = f"Download failed for tweet {target['tweet_id']}: {e}"
        logger.error(error_msg)

    if not local_path:
        error_msg = error_msg or f"Download returned None for tweet {target['tweet_id']}"
        logger.error(
            "❌ Download failed for tweet %s. "
            "ID NOT saved — will retry next run.",
            target["tweet_id"],
        )
        _print_summary(success=False, remaining=remaining + 1, target=target)
        generate_dashboard(
            status="Error",
            queue_remaining=remaining + 1,
            last_tweet_id=target["tweet_id"],
            last_author=target.get("author"),
            last_timestamp=timestamp(),
            error_message=error_msg,
        )
        return

    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    logger.info(
        "[%s] Download complete — %.1f MB at %s",
        timestamp(), file_size_mb, local_path,
    )

    # ------------------------------------------------------------------
    # STEP 4: Upload to YouTube + Instagram
    # ------------------------------------------------------------------
    # Check YouTube daily limit
    yt_allowed = not _yt_limit_reached()

    logger.info("[%s] STEP 4 — Uploading to platforms...", timestamp())

    try:
        result = upload_video(
            {**target, "local_path": local_path},
            upload_youtube=yt_allowed,
            upload_instagram=True,
        )
    except Exception as e:
        error_msg = f"Upload crashed for tweet {target['tweet_id']}: {e}"
        logger.error(error_msg)
        _print_summary(success=False, remaining=remaining + 1, target=target)
        if local_path:
            cleanup_video(local_path)
        generate_dashboard(
            status="Error",
            queue_remaining=remaining + 1,
            last_tweet_id=target["tweet_id"],
            last_author=target.get("author"),
            last_timestamp=timestamp(),
            error_message=error_msg,
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
        "[%s] Upload results — YouTube: %s | Instagram: %s",
        timestamp(),
        f"✅ {yt_id}" if yt_ok else "❌ Failed",
        f"✅ {ig_id}" if ig_ok else "❌ Failed",
    )

    # ------------------------------------------------------------------
    # STEP 5: Cleanup + State Update
    # ------------------------------------------------------------------
    logger.info("[%s] STEP 5 — Cleanup & state update...", timestamp())

    # Clean up local file IMMEDIATELY after uploads
    if local_path:
        cleanup_video(local_path)

    # Only save ID if AT LEAST ONE upload succeeded
    if yt_ok or ig_ok:
        save_processed_id(target["tweet_id"])
        logger.info(
            "✅ Tweet %s marked as processed.", target["tweet_id"]
        )
    else:
        error_msg = (
            f"BOTH uploads failed for tweet {target['tweet_id']}. "
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
) -> None:
    """Prints a clean end-of-run summary."""
    print(f"\n{'=' * 65}")
    print(f"  {'✅' if success else '❌'} PIPELINE {'COMPLETE' if success else 'FAILED'} — {timestamp()}")
    print(f"{'=' * 65}")
    print(f"  Tweet ID : {target['tweet_id']}")
    print(f"  Author   : {target['author']}")
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
