# WalkSafe

A real-time visual navigation assistant for blind and low-vision pedestrians. WalkSafe processes live smartphone camera input using state-of-the-art computer vision models to detect obstacles, estimate depth, track motion, and deliver spoken navigation guidance.

---

## Overview

WalkSafe combines three deep learning models in a unified pipeline to help pedestrians navigate safely:

- **Apple DepthPro** — monocular dense depth estimation
- **YOLOv8** — real-time object detection and multi-frame tracking
- **RAFT-Small** — optical flow estimation for ego-motion analysis

The system runs in a Gradio web app accessible from any smartphone browser. It speaks navigation commands (stop, walk forward, step left, turn right, etc.) using the browser's built-in Web Speech API and logs every decision to a local SQLite database for research and analysis.

---

## Features

| Feature | Description |
|---|---|
| Depth Estimation | Dense per-pixel depth map updated every 5 frames |
| Object Detection | Detects people, vehicles, and obstacles with confidence filtering |
| Motion Tracking | 8-frame trajectory history per agent with motion classification |
| Time-to-Collision | Calculates TTC for every tracked agent |
| Gap Detection | Identifies and measures safe walking corridors (left, ahead, right) |
| Ego Motion Analysis | Detects user action (still, walking, turning) and speed via optical flow |
| Navigation Commands | Spoken guidance: `walk_forward`, `stop`, `step_left`, `step_right`, `turn_left`, `turn_right`, `yield`, `slow_down` |
| Fusion Visualization | Side-by-side camera / depth / flow / detection panel with annotated advisory strip |
| Session Logging | All frames, agents, gaps, and decisions recorded to SQLite |
| Analytics Dashboard | Per-session metrics, command histograms, speed profiles, and risk distributions |

---

## Architecture

```
app.py                  # Entry point — loads models, launches Gradio
config.py               # All tunable thresholds and parameters
models.py               # Model loading (DepthPro, YOLO, RAFT, speaker, DB)
state.py                # Thread-safe shared application state

pipeline/
  depth.py              # DepthPro inference + depth map extraction
  detection.py          # YOLOv8 detection, tracking, risk assessment
  flow.py               # RAFT optical flow + ego motion classification
  gaps.py               # Navigable gap detection from depth + detections
  suggestion.py         # Navigation decision logic
  fusion.py             # Visualization panel + advisory strip rendering

audio/
  speaker.py            # Web Speech API TTS interface

ui/
  layout.py             # Gradio layout (Navigation + Dashboard tabs)
  processor.py          # Full per-frame pipeline orchestration
  dashboard.py          # Analytics dashboard with charts

storage/
  schema.py             # SQLite schema (sessions, frames, agents, gaps)
  writer.py             # Async batch writer (non-blocking, 50-frame flush)
  queries.py            # SQL queries for dashboard
```

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

## Requirements

- Python 3.9+
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
python app.py
```

Gradio will print a local URL (and a public share link). Open the link on the device whose camera you want to use — typically a smartphone.

On first run, DepthPro and RAFT weights are downloaded automatically from Hugging Face and the `ultralytics` model hub.

---

## Usage

### Navigation Tab

1. Open the Gradio URL in your phone browser.
2. Grant camera permission when prompted.
3. Hold the phone in front of you, camera pointing ahead.
4. The app streams frames to the server and returns:
   - A fused visualization (camera + depth + flow + detections)
   - A color-coded advisory strip showing the recommended command, ego action, best gap, and most critical agent
   - A spoken navigation command via the browser's TTS
5. Press **Reset Session** to end the current session and start a new one.

### Dashboard Tab

Select a session from the dropdown and click **Load** to view:

- Total frames, average speed, agent encounters, critical events
- Navigation command distribution
- Agent risk level distribution
- Ego action histogram
- Speed profile over time

---

## Configuration

All parameters are in [config.py](config.py). Key values:

| Parameter | Default | Description |
|---|---|---|
| `YOLO_CONF` | 0.35 | Detection confidence threshold |
| `DEPTH_UPDATE_EVERY` | 5 | Frames between full depth inference runs |
| `VIDEO_WIDTH` | 518 | Input resize width (must be 14-pixel aligned) |
| `MIN_GAP_WIDTH_PX` | 50 | Minimum gap width to consider navigable |
| `HISTORY_LEN` | 8 | Agent trajectory history in frames |
| `TTC_EMERGENCY` | 1.0 | TTC threshold for critical risk (seconds) |
| `TTC_CRITICAL` | 2.0 | TTC threshold for high risk (seconds) |
| `TTC_URGENT` | 4.0 | TTC threshold for moderate risk (seconds) |
| `FOV_DEG` | 70 | Estimated camera horizontal field of view |

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

```python
!git clone <repo-url>
%cd WalkSafe
!pip install -r requirements.txt
!python app.py
```

The `share=True` flag in `app.py` creates a public Gradio tunnel automatically.

---

## Acknowledgements

- [Apple DepthPro](https://huggingface.co/apple/DepthPro-hf) — monocular metric depth estimation
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) — real-time object detection
- [RAFT](https://github.com/princeton-vl/RAFT) (via `torchvision`) — optical flow estimation
- [Gradio](https://www.gradio.app/) — web UI framework
