"""
downloader.py — Video Downloader Module

Takes video URLs (from scraper.py) and downloads them locally using yt-dlp
into a `temp_videos/` folder. Provides a cleanup function to remove files
after they've been uploaded.

Usage (standalone test):
    python downloader.py
"""

import logging
import os
import shutil
from pathlib import Path

import yt_dlp

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
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DOWNLOAD_DIR = str(BASE_DIR / "temp_videos")


# ===================================================================
# 1. Download a single video
# ===================================================================

def download_video(
    video_url: str,
    tweet_id: str,
    output_dir: str = DEFAULT_DOWNLOAD_DIR,
) -> str | None:
    """
    Downloads a video from the given URL into `output_dir`.

    Args:
        video_url:  Direct video URL (e.g. from scraper's get_video_url).
        tweet_id:   Tweet ID — used as the output filename for uniqueness.
        output_dir: Directory to save into (created if it doesn't exist).

    Returns:
        Absolute path to the downloaded file, or None if download failed.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Output template: <output_dir>/<tweet_id>.%(ext)s
    output_template = os.path.join(output_dir, f"{tweet_id}.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "best[ext=mp4]/best",       # Prefer mp4, fallback to best
        "quiet": True,                         # Suppress yt-dlp console spam
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,                  # Timeout for slow connections
        "retries": 3,                          # Retry on transient failures
        "merge_output_format": "mp4",          # If merging streams, output mp4
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

            # Determine the actual filename yt-dlp wrote
            if info and "requested_downloads" in info:
                filepath = info["requested_downloads"][0]["filepath"]
            else:
                # Fallback: look for the file with a common extension
                filepath = _find_downloaded_file(output_dir, tweet_id)

            if filepath and os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                logger.info(
                    "✅ Downloaded tweet %s — %.1f MB → %s",
                    tweet_id, size_mb, filepath,
                )
                return filepath
            else:
                logger.error(
                    "Download reported success but file not found for tweet %s",
                    tweet_id,
                )
                return None

    except yt_dlp.utils.DownloadError as e:
        logger.error(
            "⚠️  yt-dlp download error for tweet %s: %s", tweet_id, e
        )
        return None
    except Exception as e:
        logger.error(
            "⚠️  Unexpected error downloading tweet %s: %s", tweet_id, e
        )
        return None


def _find_downloaded_file(output_dir: str, tweet_id: str) -> str | None:
    """Fallback: find a file matching the tweet_id in the output directory."""
    for ext in ("mp4", "mkv", "webm", "mov", "avi"):
        candidate = os.path.join(output_dir, f"{tweet_id}.{ext}")
        if os.path.exists(candidate):
            return candidate
    return None


# ===================================================================
# 2. Batch download — process the list from scraper
# ===================================================================

def download_all(
    video_entries: list[dict],
    output_dir: str = DEFAULT_DOWNLOAD_DIR,
) -> list[dict]:
    """
    Downloads all videos from a list of scraper entries.

    Args:
        video_entries: List of dicts from scraper.fetch_bookmarked_videos(),
                       each with keys: tweet_id, video_url, tweet_text, author.
        output_dir:    Directory to save videos into.

    Returns:
        The same list, with a new `local_path` key added to each entry.
        Entries that failed to download will have local_path = None.
    """
    results = []

    for entry in video_entries:
        tweet_id = entry["tweet_id"]
        video_url = entry["video_url"]

        logger.info(
            "⬇️  Downloading tweet %s by %s ...",
            tweet_id, entry.get("author", "unknown"),
        )

        local_path = download_video(video_url, tweet_id, output_dir)

        result = {**entry, "local_path": local_path}
        results.append(result)

    # Summary
    success = sum(1 for r in results if r["local_path"])
    failed = len(results) - success
    logger.info(
        "Download batch complete: %d succeeded, %d failed out of %d.",
        success, failed, len(results),
    )

    return results


# ===================================================================
# 3. Cleanup — delete a single file or the entire temp folder
# ===================================================================

def cleanup_video(filepath: str) -> bool:
    """
    Deletes a single downloaded video file.

    Returns True if the file was deleted, False otherwise.
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info("🗑️  Cleaned up: %s", filepath)
            return True
        else:
            logger.warning("Cleanup: file not found — %s", filepath)
            return False
    except Exception as e:
        logger.error("Cleanup error for %s: %s", filepath, e)
        return False


def cleanup_all(output_dir: str = DEFAULT_DOWNLOAD_DIR) -> bool:
    """
    Removes the entire temp_videos directory and all its contents.

    Returns True if cleanup succeeded, False otherwise.
    """
    try:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            logger.info("🗑️  Cleaned up entire directory: %s", output_dir)
            return True
        else:
            logger.info("Cleanup: directory already gone — %s", output_dir)
            return True
    except Exception as e:
        logger.error("Cleanup error for directory %s: %s", output_dir, e)
        return False


# ===================================================================
# 4. CLI entry point — standalone test
# ===================================================================

if __name__ == "__main__":
    import asyncio
    from scraper import fetch_bookmarked_videos

    async def _test():
        logger.info("🚀 Downloader test — fetching videos from scraper...")

        videos = await fetch_bookmarked_videos()
        if not videos:
            logger.info("No videos from scraper. Nothing to download.")
            return

        # Download only the first video as a test
        test_entry = videos[0]
        logger.info(
            "Test: downloading 1 of %d videos — tweet %s",
            len(videos), test_entry["tweet_id"],
        )

        local_path = download_video(
            test_entry["video_url"], test_entry["tweet_id"]
        )

        if local_path:
            print(f"\n{'='*60}")
            print(f"  ✅ Test download successful!")
            print(f"  File: {local_path}")
            print(f"  Size: {os.path.getsize(local_path) / (1024*1024):.1f} MB")
            print(f"{'='*60}\n")

            # Prompt before cleanup
            answer = input("  Delete test file? [y/N]: ").strip().lower()
            if answer == "y":
                cleanup_video(local_path)
        else:
            print("\n  ❌ Test download failed.\n")

    asyncio.run(_test())
