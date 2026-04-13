<h1 align="center">Instalaz</h1>

<p align="center">
  <strong>Let your content flow to Instagram the way it should.</strong><br>
  Turn 4K videos and photos into Story, Reel and Post formats automatically. Run your direct messages in the same window — one studio for everything.
</p>

<p align="center">
  <a href="https://python.org"><img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-1c0a2e?style=for-the-badge&labelColor=0b0212&color=ec4899"></a>
  <a href="https://flask.palletsprojects.com"><img alt="Flask" src="https://img.shields.io/badge/Flask-3.x-1c0a2e?style=for-the-badge&labelColor=0b0212&color=ec4899"></a>
  <a href="https://github.com/subzeroid/instagrapi"><img alt="instagrapi" src="https://img.shields.io/badge/instagrapi-2.3.0-1c0a2e?style=for-the-badge&labelColor=0b0212&color=f97316"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-MIT-1c0a2e?style=for-the-badge&labelColor=0b0212&color=f97316"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/landing_page_new.png" alt="Instalaz — landing" width="860">
</p>

---

## Why Instalaz?

Instalaz is a self-hosted Flask application built on top of `instagrapi`. From a single panel it gives you:

- **Upload studio** — automatic resize, crop, compression and queueing for Story (1080×1920), Reel (1080×1920) and Post (1080×1350).
- **Inbox** — direct inbox + pending requests, thread read/write, photo/video sharing, starting new conversations.
- **CDN bridge that never leaks to the browser** — Instagram media is served through your own server instead of exposing signed CDN URLs.
- **Safety reflexes** — per-IP login throttling, per-account daily/hourly upload limits, optional proxy, rate limiting backed by Redis.

After installation the app runs at `http://localhost:5000`; the dark-mode Tailwind + Alpine UI uses a single responsive layout for mobile and desktop.

---

## Highlights

### Content publishing
- **Multi-format** — images (`jpg/jpeg/png/heic/heif/raw/tiff/bmp`) and video (`mp4/mov/avi/mkv/webm/m4v`); 2 GB per request.
- **4K-aware processor** — EXIF orientation, sharpening, progressive JPEG; auto crop/resize to the Story/Reel/Post target.
- **Video pipeline** — FFmpeg first (`libx264`, CRF 23, `slow` preset, 10 Mbps); MoviePy fallback when FFmpeg is missing.
- **Queue** — a background worker publishes at a human-paced 3–15 min per-account cadence.
- **Watermark (optional)** — text stamping via `MediaProcessor.add_watermark`.

### Direct messages
- Inbox + pending requests, unread badge, last-message preview.
- Opens text, photo, video, voice notes, post/reel reshares (`xma_share`) and link cards.
- Send text or photo/video into a thread, start new conversations (multi-recipient); existing threads are reused via `direct_thread_by_participants`.
- ~5 s message polling on the active thread, ~15 s thread-list polling, automatic seen-marking.
- All Instagram CDN media is served through a server-side proxy (`/api/dm/media-proxy`).

### Instagram compatibility layer
- Saved sessions are refreshed with a current Instagram Android UA on every app boot — this avoids the `HTTP 467 Unsupported` response Instagram returns to stale clients.
- A `MediaXma.video_url` shim keeps inbox parsing alive when share cards arrive without a `target_url`.
- 2FA-supported login; even if the post-login flow returns 400, the session is accepted as long as `sessionid` landed.

### Security & limits
- Per-IP login throttling (5 attempts / hour), per-account 15 / hour and 50 / day upload limits, 3 min minimum interval.
- Optional Redis cache (`REDIS_URL`), transparent in-memory fallback when Redis is unreachable.
- Optional outbound proxy (`PROXY_URL`).
- Host whitelist on the media proxy (`cdninstagram.com`, `fbcdn.net`, `instagram.com`) — reduces SSRF exposure.

---

## Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/dashboard_new.png" alt="Dashboard" width="820">
</p>
<p align="center"><em>Dashboard — account status, quick actions, queue feed, stats and pro tips.</em></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/upload_page_new.png" alt="New content" width="820">
</p>
<p align="center"><em>New content — content type picker, drag-and-drop media, caption and queue-add.</em></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/queue_new.png" alt="Queue" width="820">
</p>
<p align="center"><em>Queue — live status (pending → processing → uploading → completed/failed).</em></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/can61cebi/Instalaz/refs/heads/main/images/messages_new.png" alt="Messages" width="820">
</p>
<p align="center"><em>Messages — inbox + requests, thread detail and new-conversation flow.</em></p>

---

## Tech stack

| Layer | Components |
|-------|-----------|
| Backend | Python 3.10+, Flask, Flask-CORS |
| Instagram | `instagrapi` 2.3.0 (subzeroid fork) + custom compatibility patches |
| Media | FFmpeg, MoviePy, Pillow, OpenCV, NumPy |
| Cache | Redis (optional), in-memory fallback |
| Frontend | Jinja2, Tailwind CSS (CDN), Alpine.js, SweetAlert2, Font Awesome |

---

## Installation

### Prerequisites
- Python 3.10+
- FFmpeg on `PATH`
- Redis (optional)

### Steps
```bash
git clone https://github.com/can61cebi/Instalaz.git
cd Instalaz
pip install flask flask-cors instagrapi moviepy pillow opencv-python numpy redis requests
python app.py
```

The app listens on `http://localhost:5000`.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session secret. Auto-generated when empty. |
| `REDIS_URL` | Redis connection (default `redis://localhost:6379/0`). Falls back to in-memory when unreachable. |
| `PROXY_URL` | Outbound HTTP proxy forwarded to `instagrapi.Client.set_proxy`. Optional. |

---

## Usage flow

1. Open `http://localhost:5000` → sign in with Instagram username/password (the 2FA prompt appears when needed).
2. On **New content**, pick Story / Reel / Post, drop the media, add a caption, hit *Add to queue*.
3. On **Queue**, track the worker's tasks live.
4. On **Messages**, open the inbox, pick a thread, send text or photo/video. Use *New message* to start a conversation by username.

---

## HTTP API

All endpoints require an authenticated session.

### Auth & account
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/login` | Supports `verification_code` for 2FA |
| `POST` | `/api/logout` | Destroy session |
| `GET`  | `/api/user/stats` | Followers, following, post & queue counts |
| `POST` | `/api/user/refresh` | Refresh cached profile |
| `GET`  | `/api/system/status` | Worker / queue / Redis state |
| `GET`  | `/api/search/user/<q>` | Username search |
| `GET`  | `/api/search/location/<q>` | Location search |

### Uploads
| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/upload` | Upload page / submit |
| `GET`  | `/upload/status/<task_id>` | Single task status |
| `GET`  | `/queue` | Queue page |
| `GET`  | `/api/queue/count` | Pending count |
| `GET`  | `/api/queue/tasks` | Task list with statuses |

### Direct messages
| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/messages` | Chat UI |
| `GET`  | `/api/dm/threads` | Inbox + pending threads |
| `GET`  | `/api/dm/threads/<thread_id>` | Thread detail + recent messages |
| `GET`  | `/api/dm/threads/<thread_id>/messages?after_id=` | Messages newer than `after_id` |
| `POST` | `/api/dm/threads/<thread_id>/seen` | Mark as seen |
| `POST` | `/api/dm/threads/<thread_id>/send` | `{"text": "..."}` |
| `POST` | `/api/dm/threads/<thread_id>/upload` | `multipart/form-data` + `file` (+ optional `text`) |
| `POST` | `/api/dm/new` | `usernames`, `text`, optional `file` |
| `GET`  | `/api/dm/search?q=` | DM-targeted user search |
| `GET`  | `/api/dm/media-proxy?url=` | Whitelisted proxy for `cdninstagram.com`, `fbcdn.net`, `instagram.com` |

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
│   ├── upload.html         # New content
│   ├── queue.html          # Queue
│   ├── messages.html       # Messages (DM)
│   └── 404.html / 500.html
├── static/                 # Default avatars, sample assets
├── images/                 # README screenshots
├── uploads/                # User uploads (gitignored)
├── temp/                   # Processing scratch files (gitignored)
└── sessions/               # instagrapi session JSON (gitignored)
```

---

## Configuration

Tunable constants live in the `Config` class at the top of `app.py`.

| Constant | Default | Note |
|----------|---------|------|
| `MAX_CONTENT_LENGTH` | 2 GB | Per-request upload |
| `STORY_DURATION_LIMIT` | 15 s | Story trim |
| `REEL_MAX_DURATION` | 90 s | Reel trim |
| `VIDEO_BITRATE` / `VIDEO_CRF` / `VIDEO_PRESET` | `10M` / `23` / `slow` | FFmpeg encoding |
| `RATE_LIMIT_UPLOADS` | 15 / hour | Per account |
| `DAILY_UPLOAD_LIMIT` | 50 / day | Per account |
| `MIN_UPLOAD_INTERVAL` | 180 s | Minimum gap between uploads |
| `DM_MAX_MEDIA_SIZE` | 100 MB | DM photo/video cap |
| `DM_PROXY_ALLOWED_HOSTS` | `cdninstagram.com`, `fbcdn.net`, `instagram.com` | `/api/dm/media-proxy` host whitelist |

---

## Security notes

- `sessions/instagram_sessions.json` contains live Instagram cookies and device data. **Never commit it.** It is gitignored by default.
- Do not expose this app on a public network without an additional auth layer — there is no multi-tenant access control.
- When widening the CDN proxy whitelist, weigh the SSRF impact.

---

## License

MIT — see [LICENSE](LICENSE).

## Contact

- Email: [can@cebi.tr](mailto:can@cebi.tr)
- Issues: [GitHub Issues](https://github.com/can61cebi/Instalaz/issues)
