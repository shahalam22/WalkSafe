# WalkSafe

A real-time visual navigation assistant for blind and low-vision pedestrians. WalkSafe processes live smartphone camera input using state-of-the-art computer vision models to detect obstacles, estimate depth, track motion, and deliver spoken navigation guidance.

---

## Overview

WalkSafe combines three deep learning models in a unified pipeline to help pedestrians navigate safely:

- **Apple DepthPro** — monocular dense depth estimation
- **YOLOv8** — real-time object detection and multi-frame tracking
- **RAFT-Small** — optical flow estimation for ego-motion analysis

WalkSafe is a web app with two kinds of users:

- **Blind user** — opens WalkSafe from the phone's home screen (or "Hey Google, open WalkSafe"),
  taps anywhere to start, and hears spoken commands (stop, walk forward, step left, …).
  Tapping again or shaking the phone stops it. No sight is needed at any step.
- **Admin** — adds blind users, sets up their phones once, saves the current server address,
  and reviews every session's data on a dashboard (charts and CSV export).

The vision models run on a GPU server (Google Colab). The app page is a static installable web app
(PWA) at a fixed address. Sign-in and all session data live in **Supabase** (Postgres + Auth).

---

## Features

| Feature | Description |
|---|---|
| Depth Estimation | Dense per-pixel depth map, computed in a background thread so a slow depth model never holds up a frame |
| Object Detection | Detects people, vehicles, and obstacles with confidence filtering |
| Motion Tracking | 8-frame trajectory history per agent with motion classification |
| Time-to-Collision | Calculates TTC for every tracked agent |
| Gap Detection | Identifies and measures safe walking corridors (left, ahead, right) |
| Ego Motion Analysis | Detects user action (still, walking, turning) and speed via optical flow |
| Navigation Commands | Spoken guidance: `walk_forward`, `stop`, `step_left`, `step_right`, `turn_left`, `turn_right`, `yield`, `slow_down` |
| Vision-free control | Full-screen start/stop button (TalkBack-friendly), shake to stop, everything spoken, screen kept awake and black |
| Demo view | Optional on-screen camera + fusion panel (depth / flow / detections / advisory strip) for presentations |
| Accounts | Admin and blind-user roles with Supabase Auth; phones stay signed in |
| Session Logging | Every frame, agent, gap, and decision written to Supabase in the background |
| Admin Dashboard | Per-user and per-session metrics, command / risk / action charts, speed profile, CSV export |

---

## Architecture

```
Phone (Chrome, installed PWA)          Colab GPU server                    Supabase
┌──────────────────────────┐  frames  ┌───────────────────────────┐ rows  ┌─────────────────┐
│ web/  guidance screen     │ ───────▶ │ app.py  FastAPI + tunnel   │ ────▶ │ Postgres tables │
│       admin dashboard     │ ◀─────── │ pipeline/  DepthPro, YOLO, │       │ Auth (logins)   │
│       speech, camera      │ command  │            RAFT, decisions │       │                 │
└──────────────────────────┘          └───────────────────────────┘       └─────────────────┘
          │  sign-in, server address, dashboard data (read directly)              ▲
          └────────────────────────────────────────────────────────────────────────┘
```

```
app.py                  # Entry point — loads models, starts the API, opens the tunnel
config.py               # Thresholds and parameters (CFG) and server settings (SERVER)
models.py               # Model loading (DepthPro, YOLO, RAFT)
state.py                # Thread-safe shared pipeline state

pipeline/
  processor.py          # Full per-frame pipeline orchestration (+ background depth)
  depth.py              # DepthPro inference + depth map extraction
  detection.py          # YOLOv8 detection, tracking, risk assessment
  flow.py               # RAFT optical flow + ego motion classification
  gaps.py               # Navigable gap detection from depth
  suggestion.py         # Navigation decision logic
  fusion.py             # Visualization panel + advisory strip rendering

audio/speaker.py        # Command → spoken phrase

server/
  api.py                # HTTP API: sessions, frames, admin user management
  auth.py               # Checks Supabase login tokens (public keys, no call per frame)
  supa.py               # Supabase REST + Auth admin client (secret key)
  tunnel.py             # Public HTTPS address (cloudflared, or Gradio as fallback)

storage/writer.py       # Background batch writer to Supabase (never blocks guidance)

supabase/schema.sql     # Tables, row level security, dashboard functions

web/                    # The app (static PWA): sign-in, guidance screen, admin dashboard
scripts/dev_server.py   # Run the server without a GPU (made-up commands) to try the app
tests/                  # Server tests (no GPU needed)
```

### API

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/health` | anyone | Is the server up and are the models loaded |
| POST | `/api/session/start` | signed in | Start a guidance session (ends any running one) |
| POST | `/api/frame?session_id=…&view=0\|1` | signed in | One JPEG frame in, the command out (and the fusion panel when `view=1`) |
| POST | `/api/session/stop` | signed in | End the session |
| POST | `/api/admin/users` | admin | Add a blind user |
| PATCH | `/api/admin/users/{id}` | admin | New password, turn on/off, rename |
| DELETE | `/api/admin/users/{id}` | admin | Remove a blind user (their sessions are kept) |

The models are shared, so one guidance session runs at a time. A session with no frames for 60 s is closed.

**Interactive API docs:** open `<server address>/docs` (Swagger UI) or `/redoc`; the OpenAPI schema is at
`/openapi.json`. To try the protected calls, press **Authorize** and paste a Supabase `access_token`
(sign in with `POST <supabase-url>/auth/v1/token?grant_type=password`, header `apikey: <publishable key>`).
Turn the docs off with `SERVER["api_docs"] = False` in [config.py](config.py).

---

## Navigation Decision Logic

The suggestion engine evaluates every frame in priority order:

1. Any agent with **critical** risk (TTC < 1 s or distance < 1 m and approaching) → **stop**
2. No navigable gap found → **stop**
3. Crossing agent with TTC < 3 s → **yield**
4. Approaching agent with low TTC → **stop** or **yield**
5. Approaching agent within close range → **slow\_down**
6. Route toward the best available gap → **step / turn** based on direction and width
7. Fallback → **slow\_down**

Risk levels assigned to each tracked agent:

| Risk | Condition |
|---|---|
| Critical | TTC < 1.0 s or (dist < 1.0 m and approaching) |
| High | TTC < 2.0 s |
| Moderate | TTC < 4.0 s or erratic motion |
| Low | All other cases |

---

## Running WalkSafe

### 1. Supabase (once)

1. Run [supabase/schema.sql](supabase/schema.sql) in the Supabase SQL Editor (safe to run again).
2. Authentication → Sign In / Providers: turn **off** "Allow new users to sign up".
3. Create the admin in Authentication → Users, then mark it admin (see the end of `schema.sql`).

### 2. The server (each time, on Colab)

Open [run_on_colab.ipynb](run_on_colab.ipynb) in Colab with a **T4 GPU**, add the secret
`SUPABASE_SECRET_KEY`, and run all cells. The last cell prints:

```
WalkSafe server address:  https://<random>.trycloudflare.com
```

Paste that address in the app: **Admin → Server → Save**. Every phone reads it when WalkSafe starts.
The address changes every time the notebook starts; the manual step goes away once the server has a
permanent home.

### 3. The app page

`web/` is a static site, published to a separate public repo with GitHub Pages so it has a fixed
address (this repo stays private; the page holds only public values):

```bash
scripts/publish_web.sh          # → https://shahalam22.github.io/walksafe-app/
```

Run it again after changing anything in `web/`. The server also serves the app at its own address,
which is handy for testing but changes every run.

### 4. Setting up a blind user's phone

Admin → **Phone setup** lists the steps: add the user, sign in on their Android phone in Chrome,
allow the camera, test the voice, and install the app to the home screen.

### Browser limits

A web page cannot use the camera while the screen is off, so WalkSafe keeps the screen awake and black
while guiding. If the screen does turn off, guidance stops, and it starts again by itself when the
screen comes back on.

---

## Configuration

All parameters are in [config.py](config.py). Key values:

| Parameter | Default | Description |
|---|---|---|
| `yolo_conf` | 0.35 | Detection confidence threshold |
| `depth_in_background` | True | Compute depth in its own thread; frames use the newest depth map |
| `depth_every_n_frames` | 5 | Frames between depth runs when `depth_in_background` is off |
| `resize_width` | 518 | Input resize width (14-pixel aligned) |
| `gap_min_width_px` | 50 | Minimum gap width to consider navigable |
| `motion_window` | 8 | Agent trajectory history in frames |
| `ttc_emergency` | 1.0 | TTC threshold for critical risk (seconds) |
| `ttc_critical` | 2.0 | TTC threshold for high risk (seconds) |
| `ttc_urgent` | 4.0 | TTC threshold for moderate risk (seconds) |
| `fov_deg` | 70 | Estimated camera horizontal field of view |
| `SERVER["tunnel"]` | cloudflared | `cloudflared`, `gradio` or `none` (also `WALKSAFE_TUNNEL`) |

---

## Database (Supabase)

Defined in [supabase/schema.sql](supabase/schema.sql):

**`profiles`** — one row per account: role (`admin` / `blind`), name, active flag  
**`sessions`** — one row per walk: user, start, end, frame count, how it ended  
**`frames`** — per-frame decision, ego state, and summary counts  
**`agents`** — every tracked detection (position, distance, TTC, risk, motion)  
**`gaps`** — every detected navigable gap (direction, width, distance)  
**`app_config`** — the current server address

The server writes with the secret key from a background thread (batches of 50 frames or every 5 s).
The admin dashboard reads directly with the admin's login; row level security lets only admins read
session data. No camera images are stored.

---

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests                  # server tests, no GPU needed
python scripts/dev_server.py            # app + API on http://localhost:8000 with made-up commands
```

Put `SUPABASE_SECRET_KEY=…` in a `.env` file to have the dev server log to Supabase and manage users.

---

## Acknowledgements

- [Apple DepthPro](https://huggingface.co/apple/DepthPro-hf) — monocular metric depth estimation
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) — real-time object detection
- [RAFT](https://github.com/princeton-vl/RAFT) (via `torchvision`) — optical flow estimation
- [FastAPI](https://fastapi.tiangolo.com/) — server
- [Supabase](https://supabase.com/) — database and sign-in
- [cloudflared](https://github.com/cloudflare/cloudflared) — tunnel from Colab
