# 🤖 Auto-Post Pipeline

> Automated multi-source → YouTube + Instagram pipeline powered by GitHub Actions.

---

## 📊 Dashboard

| Metric | Value |
|---|---|
| **Status** | ⚪ **Idle** |
| **Queue** | **0** video(s) waiting |
| **Last Run** | `2026-02-15 06:14:24 UTC` |

---

## 🎬 Last Action

_No videos processed yet._

---

## 📋 Error Log

_No recent errors._

---

## ⚙️ How It Works

1. **Checks** Instagram Saved posts for new videos (priority source)
2. **Falls back** to X bookmarks for new video tweets
3. **Downloads** the video (yt-dlp)
4. **Converts** to 9:16 vertical format
5. **Uploads** to YouTube (unlisted) + Instagram (Reel)
6. **Updates** this dashboard automatically

| Module | Purpose |
|---|---|
| `scraper.py` | Fetch X bookmarks, extract video URLs |
| `ig_scraper.py` | Fetch IG Saved posts (instaloader) |
| `downloader.py` | Download videos (yt-dlp) |
| `uploader.py` | Upload to YouTube + Instagram |
| `main.py` | Multi-source orchestrator |

---

<sub>Last updated: 2026-02-15 06:14:24 UTC · Powered by GitHub Actions</sub>
