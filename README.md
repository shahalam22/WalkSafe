# WalkSafe

A navigation aid for blind and low-vision pedestrians, used **alongside a white cane**, for
crowded and unplanned streets (Dhaka is the reference setting). It covers the one to
eight metres ahead of the user, the range where a cane is too short and a map knows
nothing, and reduces what the phone's camera sees to one short spoken command.

The requirements are in [docs/SRS.md](docs/SRS.md); how they map to code and tests is in
[docs/traceability.md](docs/traceability.md); the design is in
[docs/architecture.md](docs/architecture.md).

---

## How it works

**The models measure, the rules decide.** Three pretrained models measure the scene:

- **DepthPro**: depth in metres for every pixel
- **YOLOv8n + ByteTrack**: people, cyclists and vehicles, with identities kept across frames
- **RAFT-Small**: optical flow, from which the user's own movement is worked out

Plain, deterministic rules then pick exactly one of nine commands. There is no language
model anywhere in the decision path, and every command is stored with the rule and the
values that produced it.

The work is split by urgency:

- **On the phone**, a cheap check measures how fast the image is growing. Something
  closing in grows quickly, so the phone can say `stop` without any model or network.
  A stop from the phone always wins.
- **On the server** (a Colab GPU), the full analysis picks the command, within about 1.2 s.

If something fails, the phone says so and falls back to a more cautious level (L0 to L4)
instead of going quiet.

The phone side is a web page, not an installed app: the user opens a fixed address in
Chrome on Android (Safari on iOS also works).

---

## Repository layout

```
walksafe/                 the Python package (python -m walksafe)
  config.py               every tunable value, as frozen dataclasses (optional YAML override)
  server.py               FastAPI: the phone API, the page, the dashboard mount, the tunnel
  session.py              per-user state between frames, and the store of live sessions
  pipeline.py             one frame through perception, interpretation and decision
  decision.py             the nine commands and the ordered rules
  pages.py                publishes the phone page and today's server address to GitHub Pages
  perception/             DepthPro, YOLOv8 + ByteTrack and RAFT behind small Protocols
  interpretation/         agents (motion, speed, TTC, risk), ego motion, openings, frame quality
  storage/                SQLite schema and migrations, background writer, dashboard queries
  ui/                     Gradio dashboard and the diagnostic fusion panel
  web/                    the phone page: plain ES modules, no build step
    js/capture.js         rear camera and the two copies of each frame
    js/quality.js         too dark, too bright, blurred
    js/expansion.js       the on-phone stop
    js/guidance.js        phone stop wins, stale results dropped, what to speak and when
    js/speech.js          earcons, speech and vibration
    js/capability.js      levels L0 to L4 and their announcements
    js/setup.js           the spoken setup
    js/api.js             talking to the server
    js/main.js            wiring
tests/                    pytest (CPU, fake models), tests/js (node --test), tests/gpu
scripts/                  benchmark.py, eval_depth.py, eval_tracking.py, soak.py
docs/                     SRS, traceability, architecture, manual test checklist
run_on_colab.ipynb        clone, install, run
```

---

## Running on Colab

Open [run_on_colab.ipynb](run_on_colab.ipynb) in Colab with a T4 GPU and run its three cells:
**clone**, **install**, **run**. The run cell logs `WalkSafe is live at <url>`. The first run
downloads the model weights (a few minutes).

Colab secrets the notebook reads (all optional):

| Secret | Purpose |
|---|---|
| `GITHUB_TOKEN` | Clone this repository if it is private |
| `WALKSAFE_DASHBOARD_PASSWORD` | Dashboard password; otherwise one is generated and logged |
| `WALKSAFE_PAGES_REPO`, `WALKSAFE_PAGES_TOKEN` | Publish the fixed phone address (below) |

One URL serves everything:

| Path | What |
|---|---|
| `/` | The phone page |
| `/api/...` | The phone API |
| `/dashboard` | Research dashboard, behind a login (user `walksafe`) |
| `/healthz` | Health check, including the count of dropped log items |

To run elsewhere: `pip install -r requirements.txt`, then `python -m walksafe`. It needs
Python 3.10+, and a CUDA GPU in practice.

### Fixed address for the phone (FR-22)

The Colab URL changes every time, and a blind user cannot be asked to read a new link.
The phone instead always opens a fixed GitHub Pages address. That site hosts the phone
page itself plus a `server.json` holding today's server URL, and the server publishes both
when it starts. Because the page loads from Pages, it opens even when no server is
running, and then works in phone-only mode. If the server restarts with a new URL, the
page reads `server.json` again while it retries.

One-time setup:

1. Create a **public** repository for the page, e.g. `walksafe-phone`, with a README so it
   has a `main` branch. (Pages on a private repository needs a paid plan.)
2. In its **Settings → Pages**, deploy from branch `main`, folder `/ (root)`.
3. Create a fine-grained token with **Contents: read and write** on that repository only.
4. Add the Colab secrets `WALKSAFE_PAGES_REPO` (`owner/walksafe-phone`) and `WALKSAFE_PAGES_TOKEN`.
5. On the phone, open `https://<owner>.github.io/walksafe-phone/` and add it to the home screen.
   GitHub takes up to a minute to update Pages after each server start.

The repository holds only the page and the server's address; the token never appears in logs.

---

## Using it

### On the phone

1. Open the fixed address and press **Start guidance**, the large button that fills most
   of the screen. The first time, this runs the spoken setup.
2. Hold the phone at chest height, camera pointing ahead, and keep the screen on.
3. WalkSafe plays a short sound and speaks only when the command changes. A `stop`
   interrupts anything being said and also vibrates.
4. **Mute guidance**, **Detail** (brief, normal, detailed) and **Speech rate** can be changed
   at any time. All are ordinary controls that work with TalkBack and VoiceOver.
5. Press the large button again to stop.

Each frame is checked on the phone (too dark, too bright, blurred), and unusable frames are
not sent. About 12 times a second, the **expansion check** matches blocks between frames,
removes the overall motion, and turns the remaining outward growth in the centre into a
time to contact. If it stays below 1.5 s for three frames, the phone says `stop` at once,
and no server command is spoken until the scene stops closing in. The page keeps one
request in flight and always sends the newest frame. Results older than 2 s, or older than
one already handled, are dropped.

### First-time setup (FR-23)

Spoken, answered with buttons, and usable without sight:

1. **Limits.** WalkSafe does not replace a cane or guide dog and cannot detect kerbs or
   steps. The user confirms they understand.
2. **Consent** to send camera images. Declining gives phone-only mode and skips the next
   two checks.
3. **How the phone is held** (chest strap or hand). Where the browser reports orientation,
   the user is asked to hold the phone level.
4. **Depth check.** The user faces a flat wall at a chosen distance (a cane length is a good
   measure), and the server measures it. More than 25 % off fails setup. Otherwise the ratio
   becomes the depth scale. DepthPro's own field-of-view estimate is used when plausible,
   otherwise the standard 70°.
5. **Direction test.** After a tone, the user steps left, and the server must report
   `stepping_left`. If it reports `stepping_right`, left and right are reversed, and WalkSafe
   refuses to run (NFR-6).
6. **Shoulder width** (narrow, average, broad), used to judge openings.

The profile is kept in the browser's storage and sent when a session starts. The server
refuses a walking session unless both checks passed. **Run setup again** is in the settings.

### Capability levels

| Level | When | What the user gets |
|---|---|---|
| L0 | Everything working | Full guidance |
| L1 | Frames too dark, bright or blurred, or the server unsure of the view | Cautious commands only |
| L2 | No answer from the server for 2 s, or images not being sent | Stop warnings from the phone only |
| L3 | The on-phone check cannot see (camera covered, too plain) or has stopped | Guidance stopped; no commands |
| L4 | Battery at 5 %, or the user ends the session | Shutdown announced with the reason |

Every change is spoken with its cause. A reduced level is repeated every minute, and
recovery is announced. A fault must last 1 s before the level drops, and be gone 3 s before
it recovers. Announcements are never muted. Battery warnings at 20 % and 10 % work where the
browser reports the battery (Chrome on Android).

### Dashboard

Open `/dashboard`, log in, press **Refresh**, then pick a session:

- decisions, phone stops, walking speed, agents seen, and the share of spoken guidance that
  arrived within the 1.2 s target
- commands, agent risk, guidance delay against the target, time at each level, walking speed
- **drill-down** from any decision to its rule, its values, and the agents and openings behind it

The **Live view** tab shows the fusion panel (camera, depth, flow, agents, openings) when
`ui.diagnostic_view` is turned on. It is off by default, and the panel is never written to disk.

---

## Decisions

Each cycle, [walksafe/decision.py](walksafe/decision.py) tries these rules in order, and
the first that matches gives the one command:

| Rule | When | Command |
|---|---|---|
| R1 | An agent at critical risk | `stop` |
| R2 | No opening as wide as shoulder width + clearance margin | `stop` |
| R3 | A crossing agent will reach the user's path within 3 s | `yield` |
| R4 / R5 | An approaching agent with time to collision < 2 s / < 4 s | `stop` / `yield` |
| R6 | An agent in the user's path closer than 3 m | `slow_down` |
| R7 | The best opening is straight ahead | `walk_forward`, or `walk_forward_slow` if tight or someone approaches |
| R8 | The best opening is just beside the path (≤ 1 m) | `step_left` / `step_right` |
| R9 | The best opening is further to the side | `turn_left` / `turn_right` |
| R10 | The path could not be measured (frame rejected) | `slow_down` |

When confidence is low (unsteady depth, or a close agent not yet tracked), `walk_forward`
becomes `walk_forward_slow`, and steps and turns become `slow_down`.

| Risk | Condition |
|---|---|
| Critical | Time to collision < 1 s, or closer than 1 m and approaching |
| High | Time to collision < 2 s |
| Moderate | Time to collision < 4 s |
| Low | Otherwise |

Agent motion is `approaching`, `receding`, `crossing_left`, `crossing_right`, `static`, or
`new` (not enough history yet). Speeds and times to collision are fitted against the
frames' capture times, so they come out the same at any frame rate. Openings are columns
of the image where nothing at body height is nearer than the 3.5 m look-ahead. Detected
agents block their columns, and each opening's width in metres is compared with the
user's width.

---

## Phone API

| Request | Body | Answer |
|---|---|---|
| `POST /api/session` | `{"purpose": "walk" \| "setup", "profile": {...}}` | `{"session_id"}`; 403 without consent, or for `walk` before setup passed |
| `POST /api/session/end` | `{"session_id", "reason"}` | `{"ok": true}` |
| `POST /api/frame` | multipart: `session_id`, `seq`, `capture_ts` (phone clock, ms), `image` (JPEG, 518 px wide) | the decision, below |
| `POST /api/setup/depth` | multipart: `session_id`, `known_distance_m`, `image` | `{"measured_m", "depth_scale", "error_frac", "passed", "fov_deg"}` |
| `POST /api/event` | `{"session_id", "events": [...]}` (level changes, deliveries, phone stops, battery) | `{"ok", "accepted"}` |
| `GET /server.json`, `GET /js/config.js` | | where the server is; the page's settings, generated from `config.py` |

```json
{"seq": 42, "capture_ts": 1759400000123.4, "command": "step_right",
 "detail": "opening on your right", "phrase": "Step right",
 "reason": "R8 opening_beside width=1.10m need=0.75m dist=6.2m offset=+0.60m",
 "confidence": 0.82, "level": "L0", "ego_action": "walking_forward",
 "server_ms": 412.0, "timings": {"quality": 2.1, "depth": 300.4, "detection": 25.0, "flow": 80.2, "rules": 1.3}}
```

The numbers above are an example of the format, not measurements. A frame older than the
last one handled gets 409. A frame for a session that is still busy gets 429 rather than
waiting in a queue. A fault returns 500 `{"error": "pipeline_fault"}`, and the session carries on.

---

## Configuration

Every tunable value is in [walksafe/config.py](walksafe/config.py), including the phone's,
which the page receives as `/js/config.js`. Set `WALKSAFE_CONFIG` to a YAML file to
override values for an experiment:

```yaml
agents:
  ttc_critical_s: 1.5
ui:
  diagnostic_view: true
```

Values marked *untuned* in the file are first guesses that still need checking against
recorded clips.

---

## Data and privacy

- No frame is written to disk anywhere: uploads are size-checked before they are parsed, so
  they are never spooled to a temporary file, and the diagnostic panel is kept in memory.
  Gradio's analytics are off.
- Consent is asked before the first frame is sent, and the server refuses images without it.
- `walksafe.db` follows SRS §4: `user`, `session`, `decision`, `agent`, `opening`, `event`, plus
  `schema_version`. It has no image columns. A prototype database is migrated on first start.
- Logging goes through a bounded queue on a background thread, so it never delays guidance.
  If the queue is full, items are dropped and counted. Sessions are closed when the user
  stops, when a session goes idle, and when the server shuts down.
- The dashboard is behind a login.

---

## Testing

```bash
pip install -r requirements-dev.txt
ruff check .
pytest                            # CPU only: fake models, no GPU, no downloads
node --test "tests/js/*.test.js"
```

| Test (SRS §8.2) | Where | Runs on |
|---|---|---|
| T1 direction | `tests/test_ego.py` (mirrored flow), `tests/js/setup.test.js` (reversed result blocks setup) | CPU, Node |
| T2 depth accuracy | `scripts/eval_depth.py` on photos at known distances; `tests/gpu` | GPU |
| T3 detection and tracking | `scripts/eval_tracking.py` on a recorded clip; `tests/gpu` | GPU |
| T4 frame-rate independence | `tests/test_agents.py`, `tests/test_ego.py` at 1.5, 5 and 15 fps | CPU |
| T5 openings | `tests/test_openings.py` | CPU |
| T6 decision rules | `tests/test_decision.py`, with `hypothesis` properties | CPU |
| T7 phone stop wins | `tests/js/guidance.test.js` | Node |
| T8 stale guidance | `tests/js/guidance.test.js`, `tests/test_server.py` | Node, CPU |
| T9 speaking rules | `tests/js/guidance.test.js` | Node |
| T10 capability levels | `tests/js/capability.test.js` | Node |
| T11 server loss | `tests/js/capability.test.js`, `tests/js/api.test.js` | Node |
| T12 accessibility | [docs/manual-checklist.md](docs/manual-checklist.md) | Phone |
| T13 logging and privacy | `tests/test_writer.py`, `tests/test_schema.py`, `tests/test_server.py` | CPU |
| T14 two hours | `scripts/soak.py` | GPU |

The GPU tests and scripts run from the notebook's optional cells.
`scripts/benchmark.py` measures decisions per second (NFR-4), with `--fp16` and
`--flow-scale` to compare speed-ups.

---

## Known limitations

- **Not a replacement for a cane.** Kerbs, steps and drop-offs are out of scope, and glass and
  thin poles are weak spots for monocular depth.
- **Browser limits** (see the SRS's Platform limitations): the screen must stay on (WalkSafe
  holds a wake lock); there is no thermal warning; there is no vibration on iOS; the battery
  level is not reported on iOS; there is no offline mode before the page has loaded once.
- **Free Colab** can end a session or give no GPU. The phone then drops to L2 and recovers
  when a server returns.
- **Not yet measured:** depth accuracy, tracking on real clips, server throughput on a T4, phone
  check rate, phone stop delay, battery and data use, and a two-hour run. The commands are
  in the notebook and in [docs/manual-checklist.md](docs/manual-checklist.md).
- The thresholds marked *untuned* need recorded clips to set them properly.

---

## Acknowledgements

- [Apple DepthPro](https://huggingface.co/apple/DepthPro-hf): monocular metric depth
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) and ByteTrack: detection and tracking
- [RAFT](https://github.com/princeton-vl/RAFT) via `torchvision`: optical flow
- [FastAPI](https://fastapi.tiangolo.com/) and [Gradio](https://www.gradio.app/): server and dashboard
