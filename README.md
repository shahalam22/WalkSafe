# WalkSafe

A real-time visual navigation assistant for blind and low-vision pedestrians. WalkSafe processes live smartphone camera input using state-of-the-art computer vision models to detect obstacles, estimate depth, track motion, and deliver spoken navigation guidance.

---

## Overview

WalkSafe combines three deep learning models in a unified pipeline to help pedestrians navigate safely:

- **Apple DepthPro** — monocular dense depth estimation
- **YOLOv8** — real-time object detection and multi-frame tracking
- **RAFT-Small** — optical flow estimation for ego-motion analysis

The phone opens a web page served by the same server; there is no app to install. It speaks navigation commands (stop, walk forward, step left, turn right, etc.) using the browser's built-in Web Speech API and logs every decision to a local SQLite database for research and analysis.

---

## Features

| Feature | Description |
|---|---|
| Depth Estimation | Dense per-pixel depth map, never more than 0.4 s old |
| Object Detection | Detects people, vehicles, and obstacles with confidence filtering |
| Motion Tracking | Per-session ByteTrack; speeds fitted over 2 s of timestamped history |
| Time-to-Collision | Calculates TTC for every tracked agent |
| Openings | Openings at body height, measured in metres against the user's width |
| Ego Motion Analysis | Walking speed, sideways steps and turns from optical flow and metric depth |
| Navigation Commands | Spoken guidance: `walk_forward`, `stop`, `step_left`, `step_right`, `turn_left`, `turn_right`, `yield`, `slow_down` |
| Phone page | One large start/stop control, checks on the phone, earcon + speech + vibration |
| On-phone stop | Expansion check on a 96×72 copy: time to contact from how fast the image grows; no model, no network; overrides the server |
| Session Logging | All frames, agents, gaps, and decisions recorded to SQLite |
| Analytics Dashboard | Per-session metrics, command histograms, speed profiles, and risk distributions |

---

## Architecture

```
walksafe/
  __main__.py           # python -m walksafe: loads models, launches Gradio
  config.py             # every tunable threshold (dataclasses, optional YAML override)
  pipeline.py           # one frame through perception -> interpretation -> decision
  session.py            # per-user state carried between frames
  decision.py           # nine-command vocabulary and the decision rules
  perception/           # DepthPro, YOLOv8 + ByteTrack, RAFT-Small behind small Protocols
  interpretation/       # agents (motion, TTC, risk), ego motion, openings
  storage/              # SQLite schema, async writer, dashboard queries
  ui/                   # Gradio navigation tab, fusion panel, dashboard
tests/                  # pytest, CPU only, fake models
```

---

## Navigation Decision Logic

The models measure, the rules decide. Each cycle, [walksafe/decision.py](walksafe/decision.py)
tries these rules in order and the first that matches gives the one command:

| Rule | When | Command |
|---|---|---|
| R1 | An agent at **critical** risk | `stop` |
| R2 | No opening is as wide as shoulder width + clearance margin | `stop` |
| R3 | A crossing agent will reach the user's path within 3 s | `yield` |
| R4 / R5 | An approaching agent with TTC < 2 s / < 4 s | `stop` / `yield` |
| R6 | Any agent in the user's path closer than 3 m | `slow_down` |
| R7 | The best opening is straight ahead | `walk_forward` (`walk_forward_slow` if tight or someone is approaching) |
| R8 | The best opening is beside the path (≤ 1 m off centre) | `step_left` / `step_right` |
| R9 | The best opening is further to the side | `turn_left` / `turn_right` |
| R10 | The path could not be measured (frame rejected) | `slow_down` |

When confidence is low (unsteady depth, or a close agent not yet tracked),
`walk_forward` becomes `walk_forward_slow` and steps or turns become `slow_down`.

Agent motion is one of `approaching`, `receding`, `crossing_left`, `crossing_right`,
`static`, or `new` (not enough track history yet). Speeds and TTC are fitted
against frame capture times, so they do not depend on the frame rate.

| Risk | Condition |
|---|---|
| Critical | TTC < 1.0 s, or closer than 1.0 m and approaching |
| High | TTC < 2.0 s |
| Moderate | TTC < 4.0 s |
| Low | All other cases |

---

## Requirements

- Python 3.10+
- CUDA-capable GPU strongly recommended (CPU fallback is very slow)
- ~4 GB VRAM for DepthPro + RAFT + YOLO loaded together

Install dependencies:

```bash
pip install -r requirements.txt
```

Key packages:

```
transformers>=4.52.0        # DepthPro
ultralytics>=8.3.0          # YOLOv8
torchvision>=0.15.0         # RAFT optical flow
gradio>=4.0.0               # Web UI
opencv-python-headless>=4.8.0
torch>=2.0.0
pandas>=2.0.0
matplotlib>=3.7.0
```

---

## Running the App

```bash
python -m walksafe
```

This loads the models, starts the server, opens a public HTTPS tunnel and logs
`WalkSafe is live at <url>`. One URL serves everything:

| Path | What |
|---|---|
| `/api/session`, `/api/session/end`, `/api/frame` | The phone API (see below) |
| `/dashboard` | Gradio dashboard, behind a login (`walksafe` / `WALKSAFE_DASHBOARD_PASSWORD`, or a generated password that is logged) |
| `/healthz` | Health check |

On first run, DepthPro and RAFT weights are downloaded automatically from Hugging Face and the `ultralytics` model hub.

### Phone API

`POST /api/session` with `{"purpose": "walk", "profile": {...}}` returns
`{"session_id"}`; it is refused (403) without consent to send images, and a
`walk` session also needs `depth_check_passed` and `direction_test_passed`.
`POST /api/setup/depth` (multipart `session_id`, `known_distance_m`, `image`, in a
`setup` session) returns `{"measured_m", "depth_scale", "error_frac", "passed", "fov_deg"}`.
`POST /api/frame` takes multipart fields `session_id`, `seq`, `capture_ts`
(phone clock, ms) and `image` (JPEG, 518 px wide) and returns

```json
{"seq": 42, "capture_ts": 1759400000123.4, "command": "step_right",
 "detail": "opening on your right", "phrase": "Step right", "reason": "R8 opening_beside width=1.10m ...",
 "confidence": 0.82, "level": "L0", "ego_action": "walking_forward",
 "server_ms": 412.0, "timings": {"quality": 2.1, "depth": 300.4, "detection": 25.0, "flow": 80.2, "rules": 1.3}}
```

Frames older than the last one handled are refused (409); a frame that arrives
while the session is still busy is refused (429) rather than queued; a fault
returns 500 `{"error": "pipeline_fault"}` and the session carries on.

---

## Usage

### On the phone

1. Open the public URL in Chrome on Android (Safari on iOS also works, without vibration).
2. Press **Start guidance**, the large button that fills most of the screen. The first time,
   it runs the spoken setup below; nothing is sent to the server without consent.
3. Allow camera access and hold the phone at chest height, camera pointing ahead.
4. WalkSafe plays a short sound and speaks only when the command changes. A `stop`
   interrupts anything being said and also vibrates.
5. **Mute guidance**, **Detail** (brief, normal, detailed) and **Speech rate** can be
   changed at any time; all are ordinary controls that work with TalkBack and VoiceOver.
6. Press the large button again to stop.

The page checks each frame on the phone (too dark, too bright, blurred) and does not
send unusable ones. It also runs the **expansion check** at about 12 fps: blocks on a
grid are matched between frames, the mean motion is removed, and the remaining
outward growth in the centre gives a time to contact. Below 1.5 s for three frames
in a row, the phone says `stop` at once, and no server command is spoken until the
scene stops closing in. It keeps one request in flight and always sends the newest frame;
results older than 2 s, or older than one already handled, are dropped.

### First-time setup (FR-23)

Spoken, answered with buttons, and usable with TalkBack or VoiceOver:

1. **Limits.** WalkSafe does not replace a cane or guide dog and cannot detect kerbs or
   steps. The user confirms they understand.
2. **Consent** to send camera images. Declining gives phone-only mode (obstacle
   warnings from the expansion check) and skips the server checks.
3. **How the phone is held** (chest strap or hand). Where the browser reports
   orientation, the phone is asked to be held level.
4. **Depth check.** The user stands facing a flat wall at a chosen distance (a cane
   length is a good measure); the server measures it. More than 25 % off fails setup;
   otherwise the ratio becomes the depth scale. DepthPro's own field-of-view estimate is
   used when plausible, otherwise the standard 70°.
5. **Direction test.** After a tone, the user steps left; the server's ego-motion
   estimate must say `stepping_left`. If it says `stepping_right`, left and right are
   reversed and WalkSafe refuses to run (NFR-6).
6. **Shoulder width** (narrow, average, broad), used to judge openings (FR-8).

The profile is kept in the browser's storage and sent when a session starts; the
server refuses a walking session unless both checks passed. **Run setup again** is in
the settings.

### Capability levels

The page never fails silently (FR-18, FR-19, NFR-7). It tracks what is working and
speaks every change with its cause, repeats a reduced level every minute, and
announces recovery:

| Level | When | What the user gets |
|---|---|---|
| L0 | Everything working | Full guidance |
| L1 | Frames too dark, bright or blurred, or the server unsure of the view | Cautious commands only |
| L2 | No answer from the server for 2 s, or images not being sent | Obstacle warnings from the phone only |
| L3 | The on-phone obstacle check cannot see or has stopped | Guidance stopped; no commands |
| L4 | Battery nearly empty, or the user ends the session | Shutdown announced with the reason |

A fault must last 1 s before the level drops and be gone 3 s before it recovers.
Battery warnings come at 20 % and 10 % where the browser reports the battery
(Chrome on Android). If the user declines to send images, WalkSafe runs in
phone-only mode at L2.

### Dashboard

Open `/dashboard`, log in, press **Refresh**, then select a session to view:

- Total frames, average speed, agent encounters, critical events
- Navigation command distribution
- Agent risk level distribution
- Ego action histogram
- Speed profile over time

---

## Configuration

Every tunable value is in [walksafe/config.py](walksafe/config.py), grouped into
frozen dataclasses. Point `WALKSAFE_CONFIG` at a YAML file to override values:

```yaml
agents:
  ttc_critical_s: 1.5
```

| Section | Examples |
|---|---|
| `profile` | camera field of view, shoulder width, clearance margin, depth scale (defaults until the phone sends the user's setup) |
| `models` | model ids, YOLO confidence, agent classes, depth age cap (0.4 s) |
| `agents` | speed-fit window, motion thresholds, TTC and risk thresholds |
| `ego` | thresholds for walking, stepping and turning |
| `openings` | body-height band, look-ahead distance (3.5 m) |
| `decision` | crossing time, step-versus-turn offset, low-confidence threshold |
| `quality` | dark, bright and blur limits; confidence scores |

---

## Database Schema

Sessions are stored in `walksafe.db` (created automatically).

**`sessions`** — one row per run  
**`frames`** — per-frame decision, ego state, and summary counts  
**`agents`** — every tracked detection (position, distance, TTC, risk, motion)  
**`gaps`** — every detected navigable gap (direction, width, distance)

The async batch writer flushes every 50 frames or 5 seconds, so the vision pipeline is never blocked by I/O.

---

## Deployment on Google Colab

WalkSafe runs well on a free Colab GPU runtime. Expected throughput is approximately 1–2 FPS on a T4 GPU with all three models active.

Open [run_on_colab.ipynb](run_on_colab.ipynb) in Colab and run its three cells
(clone, install, run). The last cell prints the public URL.

---

## Acknowledgements

- [Apple DepthPro](https://huggingface.co/apple/DepthPro-hf) — monocular metric depth estimation
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) — real-time object detection
- [RAFT](https://github.com/princeton-vl/RAFT) (via `torchvision`) — optical flow estimation
- [Gradio](https://www.gradio.app/) — web UI framework
