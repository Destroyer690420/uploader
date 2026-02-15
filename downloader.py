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
import subprocess
import json
import time
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
# 0. Helpers
# ===================================================================

def ensure_netscape_cookies(json_path, txt_path):
    """
    Converts a JSON cookie file (from EditThisCookie) to Netscape format
    required by yt-dlp.
    """
    if not os.path.exists(json_path):
        return None

    # If TXT exists and is newer than JSON, use it
    if os.path.exists(txt_path):
        if os.path.getmtime(txt_path) > os.path.getmtime(json_path):
            return txt_path
            
    logger.info("Converting JSON cookies to Netscape format...")
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)

        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get('domain', '')
                # Netscape format: domain, flag, path, secure, expiration, name, value
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = c.get('path', '/')
                secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                expiration = str(int(c.get('expirationDate', time.time() + 3600)))
                name = c.get('name', '')
                value = c.get('value', '')
                
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
        
        return txt_path
    except Exception as e:
        logger.error(f"Cookie conversion failed: {e}")
        return None


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
        Tuple (filepath, caption), or (None, None) if download failed.
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

    # Inject cookies for authenticated downloads (IG Reels, Twitter videos)
    IG_COOKIES_PATH = str(BASE_DIR / "public" / "ig_cookies.json")
    IG_COOKIES_TXT = str(BASE_DIR / 'public' / 'ig_cookies.txt')
    x_cookies = str(BASE_DIR / "public" / "cookies.json")

    # Handle Instagram cookies with conversion
    if "instagram.com" in video_url.lower():
        cookie_file = ensure_netscape_cookies(IG_COOKIES_PATH, IG_COOKIES_TXT)
        if cookie_file:
            logger.info("Using converted Netscape cookies.")
            ydl_opts['cookiefile'] = cookie_file

    elif ("twitter.com" in video_url.lower() or "x.com" in video_url.lower()) and os.path.exists(x_cookies):
        ydl_opts["cookiefile"] = x_cookies
        logger.info("Using X cookies for Twitter download.")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # ORIGINAL: info = ydl.extract_info(video_url, download=True)
            # CHANGED: fetch metadata AND download
            info = ydl.extract_info(video_url, download=True)

            # Extract caption/description
            caption = info.get('description') or info.get('title') or ''

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
                return filepath, caption
            else:
                logger.error(
                    "Download reported success but file not found for tweet %s",
                    tweet_id,
                )
                return None, None

    except yt_dlp.utils.DownloadError as e:
        logger.error(
            "⚠️  yt-dlp download error for tweet %s: %s", tweet_id, e
        )
        return None, None
    except Exception as e:
        logger.error(
            "⚠️  Unexpected error downloading tweet %s: %s", tweet_id, e
        )
        return None, None


def _find_downloaded_file(output_dir: str, tweet_id: str) -> str | None:
    """Fallback: find a file matching the tweet_id in the output directory."""
    for ext in ("mp4", "mkv", "webm", "mov", "avi"):
        candidate = os.path.join(output_dir, f"{tweet_id}.{ext}")
        if os.path.exists(candidate):
            return candidate
    return None



# ===================================================================
# 1b. Convert video to 9:16 vertical (for YouTube Shorts)
# ===================================================================

def convert_to_vertical(filepath: str) -> str | None:
    """
    Converts a video to 9:16 (1080x1920) using ffmpeg.
    
    If the video is already vertical (height > width), it just scales it.
    If landscape/square, it creates a blurred background fill effect.
    
    Returns the path to the converted file, or None on failure.
    """
    if not os.path.exists(filepath):
        logger.error("convert_to_vertical: file not found — %s", filepath)
        return None

    # Probe video dimensions
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                filepath,
            ],
            capture_output=True, text=True, timeout=15,
        )
        dims = probe.stdout.strip().split("x")
        width, height = int(dims[0]), int(dims[1])
        logger.info("Video dimensions: %dx%d", width, height)
    except Exception as e:
        logger.warning("Could not probe dimensions (%s), converting anyway.", e)
        width, height = 1920, 1080  # assume landscape

    # Build output path
    base, ext = os.path.splitext(filepath)
    output_path = f"{base}_vertical.mp4"

    # ffmpeg filter: blurred background + centered original
    # Works for any input aspect ratio
    vf_filter = (
        "split[original][blur];"
        "[blur]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=25:5[bg];"
        "[original]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )

    cmd = [
        "ffmpeg", "-y", "-i", filepath,
        "-vf", vf_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info("Converting to 9:16 vertical format...")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            logger.error("ffmpeg conversion failed:\n%s", result.stderr[-500:])
            return None
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg conversion timed out (300s).")
        return None
    except FileNotFoundError:
        logger.error("ffmpeg not found! Install ffmpeg to enable 9:16 conversion.")
        return None

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info("✅ Converted to vertical: %.1f MB → %s", size_mb, output_path)

        # Delete original, keep only vertical version
        os.remove(filepath)
        return output_path

    logger.error("Converted file not found at %s", output_path)
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

        local_path, caption = download_video(video_url, tweet_id, output_dir)

        result = {**entry, "local_path": local_path, "caption_from_download": caption}
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

        local_path, caption = download_video(
            test_entry["video_url"], test_entry["tweet_id"]
        )

        if local_path:
            print(f"\n{'='*60}")
            print(f"  ✅ Test download successful!")
            print(f"  File: {local_path}")
            print(f"  Caption: {caption[:50]}...")
            print(f"  Size: {os.path.getsize(local_path) / (1024*1024):.1f} MB")
            print(f"{'='*60}\n")

            # Prompt before cleanup
            answer = input("  Delete test file? [y/N]: ").strip().lower()
            if answer == "y":
                cleanup_video(local_path)
        else:
            print("\n  ❌ Test download failed.\n")

    asyncio.run(_test())
