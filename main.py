"""
main.py — Multi-Source Pipeline Orchestrator

Designed for GitHub Actions: performs exactly ONE upload cycle and exits.
No time.sleep() — the cron schedule handles spacing between runs.

Sources (checked in order):
  1. Instagram DMs — shared Reels on the worker account
  2. X Bookmarks — bookmarked video tweets

Flow:
  1. Check IG DMs for a shared Reel (source priority)
  2. If no Reel, scrape X bookmarks for new videos
  3. Pick a single video (oldest for X, latest for IG)
  4. Download → Convert to vertical → Upload (YouTube + Instagram) → Cleanup
  5. Save state + Generate README dashboard
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
# Instagram DM Source — check for shared Reels
# ===================================================================

def _load_processed_ids() -> set:
    """Load already-processed IDs from processed_ids.txt."""
    ids_file = str(BASE_DIR / "processed_ids.txt")
    if not os.path.exists(ids_file):
        return set()
    with open(ids_file, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _try_ig_dm_source() -> dict | None:
    """
    Attempts to find a Reel shared via Instagram DMs.

    Uses ig_scraper.get_oldest_unread_reel() which:
      - Loads cookies, builds session
      - Fetches unread inbox
      - Filters for clip/media_share from other users
      - Sorts oldest-first
      - Marks as seen BEFORE returning (prevents infinite loop)

    Loop Protection:
      If the returned ID is already in processed_ids.txt, it means
      mark-as-seen worked previously but the upload failed or the ID
      was already saved. We skip it to prevent re-uploading.

    Returns:
        A dict with keys: source, media_pk, caption, reel_url, tweet_id
        or None if no Reel found or IG is not configured.
    """
    ig_cookies_path = str(BASE_DIR / "public" / "ig_cookies.json")
    if not os.path.exists(ig_cookies_path):
        logger.info("[Source: IG DM] ig_cookies.json not found — skipping IG source.")
        return None

    try:
        from ig_scraper import get_oldest_unread_reel
    except ImportError as e:
        logger.warning("[Source: IG DM] ig_scraper module not available: %s", e)
        return None

    logger.info("[Source: IG DM] Checking for shared Reels in DMs...")

    reel_info = get_oldest_unread_reel(ig_cookies_path)
    if reel_info is None:
        logger.info("[Source: IG DM] No Reels found in DMs (or mark-as-seen failed).")
        return None

    # --- Loop Protection ---
    reel_id = reel_info["tweet_id"]  # e.g. "ig_1234567890"
    processed = _load_processed_ids()
    if reel_id in processed:
        logger.warning(
            "⚠️  [Source: IG DM] LOOP GUARD: Reel %s is already in processed_ids.txt! "
            "Mark-as-seen may have failed previously. Skipping to prevent infinite re-upload.",
            reel_id,
        )
        return None

    media_pk = reel_info["media_pk"]
    caption = reel_info.get("caption", "")
    sender = reel_info.get("sender", "unknown")
    reel_url = reel_info.get("reel_url", "")

    logger.info(
        "[Source: IG DM] ✅ Found Reel! shortcode=%s from @%s (marked as seen)",
        reel_info.get("shortcode", "?"), sender,
    )

    # Download the video directly from the reel URL
    temp_dir = str(BASE_DIR / "temp_videos")
    os.makedirs(temp_dir, exist_ok=True)
    local_path = os.path.join(temp_dir, f"ig_{media_pk}.mp4")

    try:
        logger.info("[Source: IG DM] Downloading reel video...")
        import requests as req
        resp = req.get(reel_url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        file_size = os.path.getsize(local_path) / (1024 * 1024)
        logger.info("[Source: IG DM] Downloaded %.1f MB → %s", file_size, local_path)
    except Exception as e:
        logger.error("[Source: IG DM] Download failed: %s", e)
        return None

    return {
        "source": "IG DM",
        "media_pk": media_pk,
        "tweet_id": reel_id,
        "tweet_text": caption,
        "author": f"@{sender} (via IG DM)",
        "video_url": reel_url,
        "local_path": local_path,
    }


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
    source: str = "X",
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

1. **Checks** Instagram DMs for shared Reels (priority source)
2. **Falls back** to X bookmarks for new videos
3. **Downloads** the video (instagrapi / yt-dlp)
4. **Converts** to 9:16 vertical format
5. **Uploads** to YouTube (unlisted) + Instagram (Reel)
6. **Updates** this dashboard automatically

| Module | Purpose |
|---|---|
| `ig_scraper.py` | Monitor IG DMs for shared Reels |
| `scraper.py` | Fetch X bookmarks, extract video URLs |
| `downloader.py` | Download videos (yt-dlp + instagrapi) |
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
      1. Check IG DMs → 2. Fallback to X Bookmarks
      3. Download → 4. Convert → 5. Upload → 6. Cleanup
      7. Generate README dashboard
    """
    print("\n" + "=" * 65)
    print(f"  🚀 PIPELINE START — {timestamp()}")
    print("=" * 65)

    error_msg = None
    source = "X"
    target = None
    remaining = 0

    # ------------------------------------------------------------------
    # STEP 1: Try Instagram DMs first (priority source)
    # ------------------------------------------------------------------
    logger.info("[%s] STEP 1 — Checking Instagram DMs...", timestamp())

    ig_result = _try_ig_dm_source()

    if ig_result:
        source = "IG DM"
        target = ig_result
        logger.info(
            "[%s] [Source: IG DM] Using Reel %s from %s",
            timestamp(), target["media_pk"], target["author"],
        )

    # ------------------------------------------------------------------
    # STEP 2: Fallback to X Bookmarks if no IG Reel
    # ------------------------------------------------------------------
    if target is None:
        logger.info("[%s] STEP 2 — No IG Reel found. Scraping X bookmarks...", timestamp())

        try:
            all_videos = await fetch_bookmarked_videos(auto_save=False)
        except Exception as e:
            error_msg = f"Fatal scraper error: {e}"
            logger.error(error_msg)
            generate_dashboard(status="Error", error_message=error_msg, source=source)
            sys.exit(1)

        if not all_videos:
            logger.info("No new content from any source. Exiting gracefully.")
            print(f"\n  ✅ No new videos to process. Pipeline complete at {timestamp()}")
            print(f"  📊 Queue: 0 videos remaining.\n")
            generate_dashboard(status="Idle", queue_remaining=0, source=source)
            return

        logger.info(
            "[%s] [Source: X] Scraper found %d unprocessed video(s).",
            timestamp(), len(all_videos),
        )

        # Pick the OLDEST unprocessed video
        source = "X"
        video = all_videos[-1]  # bookmarks are newest-first, so last = oldest
        remaining = len(all_videos) - 1

        logger.info(
            "[%s] [Source: X] Selected oldest video: tweet %s by %s",
            timestamp(), video["tweet_id"], video["author"],
        )

        # Download
        logger.info("[%s] [Source: X] Downloading video...", timestamp())
        local_path = None
        try:
            local_path = download_video(video["video_url"], video["tweet_id"])
        except Exception as e:
            error_msg = f"[Source: X] Download failed for tweet {video['tweet_id']}: {e}"
            logger.error(error_msg)

        if not local_path:
            error_msg = error_msg or f"[Source: X] Download returned None for tweet {video['tweet_id']}"
            logger.error(
                "❌ [Source: X] Download failed for tweet %s. "
                "ID NOT saved — will retry next run.",
                video["tweet_id"],
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
        if source == "X":
            logger.info("✅ [Source: X] Tweet %s marked as processed.", target["tweet_id"])
        else:
            # For IG DMs: mark-as-seen was already done in ig_scraper
            # before returning the reel. Just save the ID.
            logger.info("✅ [Source: IG DM] Reel %s saved to processed_ids.", target["tweet_id"])
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
    source: str = "X",
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
