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
| Depth Estimation | Dense per-pixel depth map, never more than 0.4 s old |
| Object Detection | Detects people, vehicles, and obstacles with confidence filtering |
| Motion Tracking | Per-session ByteTrack; speeds fitted over 2 s of timestamped history |
| Time-to-Collision | Calculates TTC for every tracked agent |
| Openings | Openings at body height, measured in metres against the user's width |
| Ego Motion Analysis | Walking speed, sideways steps and turns from optical flow and metric depth |
| Navigation Commands | Spoken guidance: `walk_forward`, `stop`, `step_left`, `step_right`, `turn_left`, `turn_right`, `yield`, `slow_down` |
| Fusion Visualization | Side-by-side camera / depth / flow / detection panel with annotated advisory strip |
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
5. Press **Reset Tracker** to end the current session and start a new one.

### Dashboard Tab

Press **Refresh**, then select a session from the dropdown to view:

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

```python
!git clone <repo-url>
%cd WalkSafe
!pip install -r requirements.txt
!python -m walksafe
```

The `share=True` flag in `walksafe/__main__.py` creates a public Gradio tunnel automatically.

---

## Acknowledgements

- [Apple DepthPro](https://huggingface.co/apple/DepthPro-hf) — monocular metric depth estimation
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) — real-time object detection
- [RAFT](https://github.com/princeton-vl/RAFT) (via `torchvision`) — optical flow estimation
- [Gradio](https://www.gradio.app/) — web UI framework
