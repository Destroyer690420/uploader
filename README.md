# 🤖 Auto-Post Pipeline

> Automated multi-source → YouTube + Instagram pipeline powered by GitHub Actions.

---

## 📊 Dashboard

| Metric | Value |
|---|---|
| **Status** | ⚪ **Idle** |
| **Queue** | **0** video(s) waiting |
| **Last Run** | `2026-02-15 09:58:53 UTC` |

---

## 🎬 Last Action

| Field | Value |
|---|---|
| **Timestamp** | `2026-02-15 09:58:53` |
| **Source** | `IG DM` |
| **ID** | `ig_3823910365072393976` |
| **Author** | @lonelly.fanss (via IG DM) |
| **YouTube** | ❌ Failed |
| **Instagram** | ✅ Media ID `18329852065169762` |

---

## 📋 Error Log

_No recent errors._

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

<sub>Last updated: 2026-02-15 09:58:53 UTC · Powered by GitHub Actions</sub>
