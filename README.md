# 🤖 Auto-Post Pipeline

> Automated Bookmark → YouTube + Instagram pipeline powered by GitHub Actions.

---

## 📊 Dashboard

| Metric | Value |
|---|---|
| **Status** | ⚪ **Idle** |
| **Queue** | **18** video(s) waiting |
| **Last Run** | `2026-02-14 18:37:27 UTC` |

---

## 🎬 Last Action

| Field | Value |
|---|---|
| **Timestamp** | `2026-02-14 18:37:27` |
| **Tweet ID** | `2022634319899169135` |
| **Author** | @dictator_jii |
| **YouTube** | ❌ Failed |
| **Instagram** | ✅ Media ID `18074193926453278` |

---

## 📋 Error Log

_No recent errors._

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

<sub>Last updated: 2026-02-14 18:37:27 UTC · Powered by GitHub Actions</sub>
