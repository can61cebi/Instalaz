# Instalaz — Instagram Content & Direct Message Manager

A self-hosted Flask application that wraps [`instagrapi`](https://github.com/subzeroid/instagrapi) to upload optimized 4K media (Posts, Stories, Reels) and manage Instagram direct messages from a single web UI.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)](https://flask.palletsprojects.com)
[![instagrapi](https://img.shields.io/badge/instagrapi-2.3.0-E4405F.svg)](https://github.com/subzeroid/instagrapi)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Features

### Content publishing
- **Multi-format upload** — images (`jpg`, `jpeg`, `png`, `heic`, `heif`, `raw`, `tiff`, `bmp`) and video (`mp4`, `mov`, `avi`, `mkv`, `webm`, `m4v`); 2 GB per request.
- **4K-aware processing** — automatic resize/crop for Story (1080×1920), Reel (1080×1920) and Post (1080×1350); EXIF orientation, sharpening, progressive JPEG output.
- **Video pipeline** — FFmpeg first (`libx264`, CRF 23, `slow` preset, 10 Mbps), MoviePy fallback when FFmpeg is unavailable.
- **Background queue** — uploads are queued and processed by a worker thread; per-account human-paced timing (3–15 min between uploads, randomized) to reduce account-action flags.
- **Optional watermarking** — text watermarks at configurable positions (`MediaProcessor.add_watermark`).

### Direct messages (chat)
- Inbox + pending requests, unread badge, last-message preview.
- Open a thread to view text, photos, videos, voice notes, post/reel reshares (incl. `xma_share`) and link previews.
- Send text or upload a photo/video into an existing thread.
- Start a new conversation by username (single or group); existing threads are reused via `direct_thread_by_participants`.
- ~5 s message polling on the active thread, ~15 s thread-list polling, automatic seen-marking.
- All Instagram CDN media is served through a server-side proxy (`/api/dm/media-proxy`), so signed CDN tokens never reach the browser.

### Authentication & safety
- Persistent Instagram sessions (via `Client.dump_settings`) with **2FA** support.
- Per-IP login throttling (5 attempts / hour), per-account upload throttling (15 / hour, 50 / day, 3 min minimum interval).
- Optional Redis cache (`REDIS_URL`); transparent in-memory fallback when Redis is not running.
- Optional outbound proxy via `PROXY_URL`.
- Tailwind + Alpine.js UI with dark mode.

---

## Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/image2.png" alt="Dashboard" width="600">
</p>
<p align="center"><em>Dashboard</em></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/image3.png" alt="Upload" width="600">
</p>
<p align="center"><em>Upload</em></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/image4.png" alt="Queue" width="600">
</p>
<p align="center"><em>Queue</em></p>

---

## Tech stack

| Layer | Components |
|-------|-----------|
| Backend | Python 3.10+, Flask, Flask-CORS |
| Instagram | `instagrapi` 2.3.0 (subzeroid fork) |
| Media | FFmpeg, MoviePy, Pillow, OpenCV, NumPy |
| Cache | Redis (optional), in-memory fallback |
| Frontend | Jinja2, Tailwind CSS (CDN), Alpine.js, SweetAlert2, Font Awesome |

---

## Installation

### Prerequisites

- Python 3.10+
- FFmpeg on `PATH`
- Redis (optional)

### Setup

```bash
git clone https://github.com/can61cebi/Instalaz.git
cd Instalaz

pip install flask flask-cors instagrapi moviepy pillow opencv-python numpy redis requests
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session secret. Auto-generated if unset. |
| `REDIS_URL` | Redis connection (default `redis://localhost:6379/0`). Falls back to in-memory if unreachable. |
| `PROXY_URL` | Outbound HTTP proxy passed to `instagrapi.Client.set_proxy`. Optional. |

### Run

```bash
python app.py
```

The app listens on `http://localhost:5000`.

---

## Usage

1. Open `http://localhost:5000` and log in with your Instagram credentials (2FA prompt is shown when required).
2. **Upload** — drag & drop into the upload page, pick a target type (Post / Story / Reel), and let the queue worker publish it.
3. **Queue** — track per-task status (pending → processing → uploading → completed/failed) with live polling.
4. **Mesajlar (Messages)** — open the paper-plane icon in the top bar:
   - Pick a thread on the left to read the conversation.
   - Send text or attach a photo/video from the composer.
   - Hit *Yeni Mesaj* to search a username and start a new conversation (multi-recipient supported).

---

## HTTP API

All API routes require an authenticated session.

### Auth & account
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/login` | Login (supports `verification_code` for 2FA) |
| `POST` | `/api/logout` | Destroy session |
| `GET`  | `/api/user/stats` | Followers, following, post & queue counts |
| `POST` | `/api/user/refresh` | Refresh cached profile info |
| `GET`  | `/api/system/status` | Worker / queue / Redis state |
| `GET`  | `/api/search/user/<q>` | Username search |
| `GET`  | `/api/search/location/<q>` | Location search |

### Uploads
| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/upload` | Upload page / submit files |
| `GET`  | `/upload/status/<task_id>` | Status of a single queued task |
| `GET`  | `/queue` | Queue page |
| `GET`  | `/api/queue/count` | Pending count |
| `GET`  | `/api/queue/tasks` | Task list with statuses |

### Direct messages
| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/messages` | Chat UI |
| `GET`  | `/api/dm/threads` | Inbox + pending threads |
| `GET`  | `/api/dm/threads/<thread_id>` | Thread detail + recent messages |
| `GET`  | `/api/dm/threads/<thread_id>/messages?after_id=` | Polling endpoint, returns messages newer than `after_id` |
| `POST` | `/api/dm/threads/<thread_id>/seen` | Mark thread as seen |
| `POST` | `/api/dm/threads/<thread_id>/send` | Send text (`{"text": "..."}`) |
| `POST` | `/api/dm/threads/<thread_id>/upload` | `multipart/form-data` with `file` (+ optional `text`) |
| `POST` | `/api/dm/new` | Start a chat: `usernames` (comma-separated), `text`, optional `file` |
| `GET`  | `/api/dm/search?q=` | DM-targeted user search |
| `GET`  | `/api/dm/media-proxy?url=` | Whitelisted CDN proxy for `*.cdninstagram.com`, `*.fbcdn.net`, `*.instagram.com` |

---

## Project layout

```
Instalaz/
├── app.py                  # Flask app, Instagram manager, media processor, DM API
├── templates/
│   ├── base.html           # Layout, nav, Alpine stores (queue + dm unread)
│   ├── index.html          # Landing
│   ├── login.html          # Login + 2FA
│   ├── dashboard.html      # Account overview
│   ├── upload.html         # Upload UI
│   ├── queue.html          # Live queue status
│   ├── messages.html       # Chat (DM) UI
│   └── 404.html / 500.html
├── static/                 # Default avatars, sample thumbnails
├── images/                 # README screenshots
├── uploads/                # Persisted user uploads (gitignored)
├── temp/                   # Working files for processing (gitignored)
└── sessions/               # Persisted instagrapi session JSON (gitignored)
```

---

## Configuration

Tunable constants live in `Config` at the top of `app.py`. Key values:

| Constant | Default | Notes |
|----------|---------|-------|
| `MAX_CONTENT_LENGTH` | 2 GB | Per-request upload size |
| `STORY_DURATION_LIMIT` | 15 s | Story trim |
| `REEL_MAX_DURATION` | 90 s | Reel trim |
| `VIDEO_BITRATE` / `VIDEO_CRF` / `VIDEO_PRESET` | `10M` / `23` / `slow` | FFmpeg encoding |
| `RATE_LIMIT_UPLOADS` | 15 / hour | Per account |
| `DAILY_UPLOAD_LIMIT` | 50 / day | Per account |
| `MIN_UPLOAD_INTERVAL` | 180 s | Minimum gap between uploads |
| `DM_MAX_MEDIA_SIZE` | 100 MB | DM photo/video upload cap |
| `DM_PROXY_ALLOWED_HOSTS` | `cdninstagram.com`, `fbcdn.net`, `instagram.com` | Hosts allowed through `/api/dm/media-proxy` |

---

## Security notes

- `sessions/instagram_sessions.json` contains live Instagram cookies and device data. **Never commit it.** It is gitignored by default.
- Avoid exposing this app on a public network without an additional auth layer — there is no multi-tenant access control.
- The CDN proxy enforces a host whitelist; do not loosen it without understanding SSRF implications.

---

## License

MIT — see [LICENSE](LICENSE).

## Contact

- Email: [can@cebi.tr](mailto:can@cebi.tr)
- Issues: [GitHub Issues](https://github.com/can61cebi/Instalaz/issues)
