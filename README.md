# 🤖 Auto-Post Pipeline

> Automated multi-source → YouTube + Instagram pipeline powered by GitHub Actions.

---

## 📊 Dashboard

| Metric | Value |
|---|---|
| **Status** | ⚪ **Idle** |
| **Queue** | **0** video(s) waiting |
| **Last Run** | `2026-02-15 11:14:09 UTC` |

---

## 🎬 Last Action

| Field | Value |
|---|---|
| **Timestamp** | `2026-02-15 16:44:09` |
| **Source** | `instagram` |
| **ID** | `discord_1472531870502621288` |
| **Author** | @mac04693 |
| **YouTube** | ❌ Failed |
| **Instagram** | ✅ Media ID `18098071342741616` |

---

## 📋 Error Log

_No recent errors._

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

<sub>Last updated: 2026-02-15 11:14:09 UTC · Powered by GitHub Actions</sub>
