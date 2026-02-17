"""
uploader.py — Video Upload Module (YouTube + Instagram)

Handles posting downloaded videos to:
  • YouTube  (Data API v3) — direct file upload, defaults to 'unlisted'
  • Instagram (Graph API)  — resumable direct file upload for Reels

Required environment variables (set in .env or GitHub Secrets):
  YouTube:   YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  Instagram: IG_USER_ID, IG_ACCESS_TOKEN

Usage (standalone test):
    python uploader.py
"""

import logging
import os
import re
import time

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging & Env
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

load_dotenv()  # reads .env file if present


# ===================================================================
#  Caption / Title helpers
# ===================================================================

def clean_caption(text: str, author: str = "") -> str:
    """
    Strips URLs and whitespace from tweet text.
    If nothing remains, generates a sensible fallback caption.
    """
    # Remove all URLs (http/https and t.co links)
    cleaned = re.sub(r"https?://\S+", "", text).strip()

    # Remove leftover whitespace artifacts
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if cleaned:
        return cleaned

    # Fallback: generate a caption from author
    if author:
        return f"🎬 Video by {author}"
    return "🎬 Check out this video!"


def make_title(text: str, author: str = "", max_len: int = 100) -> str:
    """
    Creates a YouTube-friendly title from tweet text.
    Falls back to author-based title if text is just URLs.
    """
    clean = clean_caption(text, author)

    if len(clean) > max_len:
        return clean[: max_len - 3] + "..."
    return clean


# ===================================================================
#  YOUTUBE — Data API v3
# ===================================================================

YT_TOKEN_URL = "https://oauth2.googleapis.com/token"
YT_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


def _get_youtube_access_token() -> str | None:
    """
    Exchanges a refresh token for a fresh access token using
    the YouTube/Google OAuth2 token endpoint.
    """
    client_id = os.getenv("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET")
    refresh_token = os.getenv("YT_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        logger.error(
            "Missing YouTube credentials. Set YT_CLIENT_ID, "
            "YT_CLIENT_SECRET, and YT_REFRESH_TOKEN."
        )
        return None

    resp = requests.post(YT_TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })

    if resp.status_code != 200:
        logger.error("YouTube token refresh failed: %s", resp.text)
        return None

    token = resp.json().get("access_token")
    logger.info("YouTube access token obtained successfully.")
    return token


def upload_to_youtube(
    filepath: str,
    title: str = "Uploaded Video",
    description: str = "",
    privacy: str = "public",
    category_id: str = "22",          # "People & Blogs"
    tags: list[str] | None = None,
) -> str | None:
    """
    Uploads a local video file to YouTube via the Data API v3
    using resumable upload.

    Returns:
        YouTube video ID on success, or None on failure.
    """
    if not os.path.exists(filepath):
        logger.error("File not found: %s", filepath)
        return None

    access_token = _get_youtube_access_token()
    if not access_token:
        return None

    # --- Step 1: Initiate resumable upload ---
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
        "X-Upload-Content-Type": "video/*",
        "X-Upload-Content-Length": str(os.path.getsize(filepath)),
    }

    init_resp = requests.post(
        f"{YT_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers=headers,
        json=metadata,
    )

    if init_resp.status_code not in (200, 308):
        logger.error("YouTube upload init failed: %s", init_resp.text)
        return None

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        logger.error("No upload URL in YouTube response headers.")
        return None

    logger.info("YouTube resumable upload initiated.")

    # --- Step 2: Upload the file ---
    file_size = os.path.getsize(filepath)
    with open(filepath, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/*",
                "Content-Length": str(file_size),
            },
            data=f,
        )

    if upload_resp.status_code not in (200, 201):
        logger.error("YouTube file upload failed: %s", upload_resp.text)
        return None

    video_id = upload_resp.json().get("id")
    logger.info(
        "✅ YouTube upload complete — ID: %s | https://youtu.be/%s",
        video_id, video_id,
    )
    return video_id


# ===================================================================
#  INSTAGRAM — Graph API (Reels) via Resumable Upload
# ===================================================================

IG_GRAPH_URL = "https://graph.facebook.com/v21.0"
IG_RUPLOAD_URL = "https://rupload.facebook.com/ig-api/v21.0/video-upload"

# Polling constants
IG_POLL_INTERVAL = 5      # seconds between status checks
IG_POLL_MAX_WAIT = 300    # max seconds to wait for container


def upload_to_instagram(
    filepath: str,
    caption: str = "",
    share_to_feed: bool = True,
) -> str | None:
    """
    Publishes a local video file as an Instagram Reel using the
    Graph API's resumable upload protocol.

    Flow:
      1. Initialize upload session (upload_type=resumable)
      2. Upload video binary to rupload.facebook.com
      3. Poll container status until FINISHED
      4. Publish the container

    Args:
        filepath:      Absolute path to the local video file.
        caption:       Caption text (max 2200 chars).
        share_to_feed: Also show in the main feed (not just Reels tab).

    Returns:
        Instagram media ID on success, or None on failure.
    """
    ig_user_id = os.getenv("IG_USER_ID")
    access_token = os.getenv("IG_ACCESS_TOKEN")

    if not ig_user_id or not access_token:
        logger.error(
            "Missing Instagram credentials. "
            "Set IG_USER_ID and IG_ACCESS_TOKEN."
        )
        return None

    if not os.path.exists(filepath):
        logger.error("Instagram upload: file not found — %s", filepath)
        return None

    file_size = os.path.getsize(filepath)

    # --- Step 1: Create Reels container with upload_type=resumable ---
    create_resp = requests.post(
        f"{IG_GRAPH_URL}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:2200],
            "share_to_feed": str(share_to_feed).lower(),
            "like_and_view_counts_disabled": "1",
            "access_token": access_token,
        },
    )

    if create_resp.status_code != 200:
        logger.error("IG container creation failed: %s", create_resp.text)
        return None

    resp_data = create_resp.json()
    container_id = resp_data.get("id")
    upload_uri = resp_data.get("uri")

    if not container_id:
        logger.error("No container ID in Instagram response.")
        return None

    logger.info("Instagram container created: %s", container_id)

    # --- Step 2: Upload video file directly ---
    if upload_uri:
        # Use the URI returned by the API
        ig_upload_url = upload_uri
    else:
        # Fallback: construct the rupload URL
        ig_upload_url = f"{IG_RUPLOAD_URL}/{container_id}"

    logger.info("Uploading video file (%d bytes) to Instagram...", file_size)

    with open(filepath, "rb") as f:
        upload_resp = requests.post(
            ig_upload_url,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
            data=f,
        )

    if upload_resp.status_code != 200:
        logger.error("IG file upload failed (%d): %s",
                      upload_resp.status_code, upload_resp.text)
        return None

    logger.info("Instagram file upload complete — waiting for processing...")

    # --- Step 3: Poll until container is ready ---
    elapsed = 0
    while elapsed < IG_POLL_MAX_WAIT:
        time.sleep(IG_POLL_INTERVAL)
        elapsed += IG_POLL_INTERVAL

        status_resp = requests.get(
            f"{IG_GRAPH_URL}/{container_id}",
            params={
                "fields": "status_code,status",
                "access_token": access_token,
            },
        )

        if status_resp.status_code != 200:
            logger.warning("IG status check error: %s", status_resp.text)
            continue

        status = status_resp.json()
        status_code = status.get("status_code")

        if status_code == "FINISHED":
            logger.info("Instagram container ready.")
            break
        elif status_code == "ERROR":
            logger.error(
                "Instagram container processing failed: %s",
                status.get("status", "unknown error"),
            )
            return None
        else:
            logger.debug(
                "IG container status: %s (waited %ds)", status_code, elapsed
            )
    else:
        logger.error(
            "Instagram container timed out after %ds.", IG_POLL_MAX_WAIT
        )
        return None

    # --- Step 4: Publish ---
    publish_resp = requests.post(
        f"{IG_GRAPH_URL}/{ig_user_id}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": access_token,
        },
    )

    if publish_resp.status_code != 200:
        logger.error("IG publish failed: %s", publish_resp.text)
        return None

    media_id = publish_resp.json().get("id")
    logger.info("✅ Instagram Reel published — media ID: %s", media_id)

    # --- Step 5: Hide Like Count ---
    try:
        hide_resp = requests.post(
            f"{IG_GRAPH_URL}/{media_id}",
            params={
                "like_and_view_counts_disabled": "true",
                "access_token": access_token,
            },
        )
        if hide_resp.status_code == 200:
            logger.info("🙈 Like count hidden for media %s", media_id)
        else:
            logger.warning("⚠️ Failed to hide like count: %s", hide_resp.text)
    except Exception as e:
        logger.warning("⚠️ Exception hiding like count: %s", e)

    return media_id


# ===================================================================
#  Convenience — upload to both platforms
# ===================================================================

def upload_video(
    entry: dict,
    upload_youtube: bool = True,
    upload_instagram: bool = True,
) -> dict:
    """
    Uploads a video entry (from downloader) to YouTube and/or Instagram.

    Args:
        entry: Dict with keys: tweet_id, video_url, tweet_text, author,
               local_path (from downloader).
        upload_youtube:   Whether to upload to YouTube.
        upload_instagram: Whether to upload to Instagram.

    Returns:
        The same dict with added keys: youtube_id, instagram_id
        (None if upload was skipped or failed).
    """
    result = {**entry, "youtube_id": None, "instagram_id": None}

    raw_text = entry.get("tweet_text", "")
    author = entry.get("author", "")
    local_path = entry.get("local_path")

    # Smart caption & title
    caption = clean_caption(raw_text, author)
    title = make_title(raw_text, author)

    # --- YouTube (uses local file) ---
    if upload_youtube:
        if local_path and os.path.exists(local_path):
            result["youtube_id"] = upload_to_youtube(
                filepath=local_path,
                title=title,
                description=f"Originally posted by {author}\n\n{caption}",
            )
        else:
            logger.warning(
                "Skipping YouTube for tweet %s — no local file.",
                entry.get("tweet_id"),
            )

    # --- Instagram (uses local file via resumable upload) ---
    if upload_instagram:
        if local_path and os.path.exists(local_path):
            # Use the ORIGINAL caption from the source Reel
            ig_caption = raw_text.strip() if raw_text.strip() else caption
            result["instagram_id"] = upload_to_instagram(
                filepath=local_path,
                caption=ig_caption,
            )
        else:
            logger.warning(
                "Skipping Instagram for tweet %s — no local file.",
                entry.get("tweet_id"),
            )

    return result


# ===================================================================
#  CLI entry point — standalone test
# ===================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  Uploader Module — Configuration Check")
    print("=" * 60)

    # Check YouTube credentials
    yt_ok = all([
        os.getenv("YT_CLIENT_ID"),
        os.getenv("YT_CLIENT_SECRET"),
        os.getenv("YT_REFRESH_TOKEN"),
    ])
    print(f"\n  YouTube credentials:  {'✅ Set' if yt_ok else '❌ Missing'}")
    if not yt_ok:
        print("    → Set YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN")

    # Check Instagram credentials
    ig_ok = all([
        os.getenv("IG_USER_ID"),
        os.getenv("IG_ACCESS_TOKEN"),
    ])
    print(f"  Instagram credentials: {'✅ Set' if ig_ok else '❌ Missing'}")
    if not ig_ok:
        print("    → Set IG_USER_ID and IG_ACCESS_TOKEN")

    # Check YouTube token exchange
    if yt_ok:
        print("\n  Testing YouTube token exchange...")
        token = _get_youtube_access_token()
        print(f"  YouTube token: {'✅ Valid' if token else '❌ Failed'}")

    # Test caption cleaning
    print("\n  Caption cleaning tests:")
    tests = [
        ("https://t.co/abc123", "@user"),
        ("Check this out! https://t.co/xyz", "@author"),
        ("", "@creator"),
        ("Great content 🔥", ""),
    ]
    for text, auth in tests:
        print(f"    '{text}' → '{clean_caption(text, auth)}'")

    print()
