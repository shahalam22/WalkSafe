# Task: Complete the WalkSafe application

You are working in the WalkSafe repository. Your job is to take the working prototype to a complete, tested application that meets the requirements in `docs/SRS.md`, with a clean folder structure and sound engineering practice. Work in phases, commit after each, and keep me informed.

Before planning anything, read: `docs/SRS.md` (this is the contract), `README.md`, every `.py` file, and `run_on_colab.ipynb`.

---

## 1. What WalkSafe is

A navigation aid for blind and low-vision pedestrians, used **alongside** a white cane, for crowded and unplanned streets (Dhaka is the reference setting). It covers the 1–8 m ahead of the user. Three pretrained models measure the scene: DepthPro (depth in metres), YOLOv8n + ByteTrack (agents with stable IDs) and RAFT-Small (optical flow). Deterministic rules then reduce the scene to one spoken command from a fixed nine-command vocabulary (SRS §2.4). There is no LLM anywhere in the decision path. The principle is: **the models measure, the rules decide.**

Urgency splits the work across two places:
- **The phone** runs a cheap image-expansion check that can say `stop` within 250 ms, with no model and no network.
- **The server** runs the full analysis within 1.2 s.

A `stop` from the phone always wins. Capability levels L0–L4 (SRS §2.2) make sure the system never fails silently.

## 2. Current state

- Runs end to end on Google Colab (T4) through Gradio: a webcam stream goes to the pipeline, which produces a command, speaks it in the browser, logs it to SQLite and shows it on a dashboard.
- Code layout: `pipeline/`, `storage/`, `ui/`, `audio/`, plus `config.py`, `models.py` and `state.py` at the root.
- There are **no tests**.
- Requirement status against the SRS: FR-2, 3, 4, 6, 11, 24 and 25 are done. FR-1, 5, 7, 9, 12, 13, 14 and 26 are partial. FR-8, 10 and 15–23 are missing.

## 3. Platform decision (fixed, do not revisit)

- **Web app only.** The Python server runs on Colab and the user opens it in a phone browser: Chrome on Android first, Safari on iOS second. **No native mobile app.**
- The SRS components marked "on the phone" are built as **browser JavaScript** in the served page: Camera Capture, Expansion Check, Guidance Control, Session Control and Setup. Server components stay in Python.
- Browsers cannot do some things the SRS asks for. Document each as a platform limitation (see §9); do not try to work around them:
  - running with the screen off (use the Screen Wake Lock API instead)
  - thermal warnings
  - vibration on iOS
  - guaranteed 2-hour sessions on free Colab
  - a fully offline phone-only mode before the page has loaded

## 4. Known defects (from code review; fix them first)

1. **Assumed frame rate.** `pipeline/detection.py` (`dt = len(hist) / 30.0`) and `pipeline/flow.py` (`* 30.0`) assume 30 fps. The real rate is about 1–2 fps, so approach speed and walking speed come out 15–30× too high and TTC far too low, which causes false `stop`s. Use measured capture timestamps instead. Note that `len(hist)` frames span `len(hist) - 1` intervals.
2. **Old depth maps.** Depth is refreshed every 5 frames (`ui/processor.py`), so at 1–2 fps it can be 2.5–5 s old, and agent distances are read from it at new box positions. Cap depth age by time (the SRS says 400 ms), not by frame count.
3. **Gap detection always finds a gap.** `pipeline/gaps.py` uses a relative threshold (the 55th percentile), so about 45% of columns always count as "open", even facing a wall, and the "no clear corridor" rule almost never fires. Use an absolute free-distance criterion, remove columns covered by detected agents, and compare width against the user's shoulder width plus a clearance margin (FR-8).
4. **No error handling** around the per-frame pipeline. A fault stops guidance silently (FR-19, NFR-7).
5. **All mutable state is module-global** (`state.py`, `_track_history` in `ui/processor.py`), so two clients corrupt each other. Resetting does not reset the ByteTrack tracker either.
6. **Inconsistent "best gap".** `suggestion.py` picks it by width in pixels and `storage/writer.py` by width in metres, so the log can disagree with the decision.
7. **Two commands never fire.** `turn_left` and `turn_right` are unreachable, and the fallback rule is unreachable too.
8. **Only the bare command is spoken.** The `detail` string ("person approaching from your right") is never spoken.
9. **`speechSynthesis.cancel()` runs on every change**, not only for `stop`.
10. **Logging problems:**
    - The log queue has no size limit, although a comment claims "drops if full".
    - The last session is never closed (`ended_at` stays NULL).
    - The session starts at app launch instead of when the user starts.
11. **Smaller issues:**
    - `pipeline/fusion.py` has a dead duplicate `build_advisory` stub.
    - `►` and `—` render as `?` in OpenCV text.
    - Thresholds are hard-coded outside `config.py`.
    - Unused config keys, `is_ready()` and `pyttsx3`.
    - All 80 COCO classes are treated as agents.
    - `walksafe.db` is not in `.gitignore`.
    - The README describes buttons that don't exist.

Confirm each defect against the code before fixing it. If any turns out to be wrong, say so.

## 5. Target architecture

### 5.1 Data flow

```
Browser (phone)
  getUserMedia(rear camera, facingMode: "environment")
    ├─ every frame, locally, ≥10 fps:
    │    frame quality check (dark / bright / blur)      → FR-1, FR-10
    │    expansion check (time-to-contact from flow)     → FR-16, NFR-1, NFR-3
    └─ newest frame only, one request in flight:
         POST /api/frame {session_id, seq, capture_ts, jpeg (518 px wide)}
                │
Server (Colab)  ▼
  perception (depth, detection + tracking, flow)
  → interpretation (agents, TTC from capture_ts, risk, openings, ego motion)
  → decision rules → {seq, capture_ts, command, detail, phrase, reason,
                      confidence, level, server_ms}
  → async log writer
                │
Browser         ▼
  guidance controller: phone stop wins · drop stale (>2 s) or out-of-order
  · speak only on change · rate limit · earcon → speech → vibration
  capability state machine L0–L4 · announcements · event log
```

- Gradio stays for the dashboard and an **optional** diagnostic view of the fusion panel. Turn the diagnostic view off by default to save bandwidth.
- Serve the API and the Gradio UI from one app, for example FastAPI with `gr.mount_gradio_app`, behind one public URL.
- Check the APIs against the Gradio version actually installed instead of guessing.
- The capture timestamp comes from the phone's clock, which is the same clock for every frame. The server uses it for all speed and TTC calculations. The browser compares it with its own clock to discard stale guidance.

### 5.2 Folder structure

Treat this as an upper bound, not a target. If a folder would hold only one small file, merge it into its neighbour (§5.4). Explain any change in the plan.

```
walksafe/                    # Python package
  __init__.py
  __main__.py                # python -m walksafe
  config.py                  # one typed config (dataclasses); every threshold lives here
  server/                    # FastAPI app, routes (/api/frame, /api/session, /api/event), Gradio mount
  perception/                # model wrappers behind Protocols: DepthEstimator, Detector, FlowEstimator
    loader.py  depth.py  detection.py  flow.py
  interpretation/            # pure functions, no models, no I/O
    agents.py  ego.py  openings.py  quality.py  confidence.py
  decision/                  # pure functions
    vocabulary.py  rules.py
  session/                   # per-session state, keyed by session_id; capability levels (server side)
  storage/                   # schema + migrations, bounded async writer, queries
  ui/                        # Gradio dashboard + diagnostic view
  web/static/                # served to the phone
    index.html  css/
    js/  capture.js  quality.js  expansion.js  guidance.js  capability.js  setup.js  api.js  main.js
tests/
  unit/  integration/  gpu/  js/  fixtures/
scripts/                     # benchmark.py, eval_depth.py, soak.py
notebooks/run_on_colab.ipynb
docs/                        # SRS.md, traceability.md, testing/manual-checklist.md, architecture.md
pyproject.toml  requirements.txt  requirements-dev.txt  README.md
```

### 5.3 Engineering rules

- **Models measure, rules decide.** Everything after the model outputs is a pure function with typed inputs and outputs (dataclasses), with no globals and no I/O. Inject a clock so time-dependent logic is testable.
- **Swappable models (NFR-16).** Models sit behind Protocol interfaces. Tests use fake implementations, so the whole suite runs on CPU without downloading any weights.
- **No module-level mutable state** except the loaded model singletons. All per-user state lives in a session object.
- **One typed config.** Thresholds live only in `walksafe/config.py`, with no magic numbers in the logic. Allow an environment or YAML override for experiments.
- **Logging.** Use the `logging` module, not `print`. Use type hints throughout. Comment only what isn't obvious.
- **Faults.** Every fault path ends in an announced capability change. Never swallow an exception silently.
- **Privacy.** No frame is ever written to disk anywhere. Gradio flagging and caching are off. Ask for consent before the first frame is sent. The database has no image columns. Put the dashboard behind authentication.
- **Safety invariants, each encoded as a test:**
  - a failure only ever makes output more cautious (NFR-5)
  - left and right are never swapped (NFR-6)
  - a phone `stop` is never overridden or delayed (FR-16)
  - silence is never the only signal of a fault (NFR-7)
- **Tooling.** Use `ruff` for lint and format and `pytest` for tests. Write JS as plain ES modules with no build step, tested with `node --test`. Pin dependencies to compatible ranges. Target Python 3.10+.

### 5.4 Keep it simple (this overrides everything above)

This is a final-year student project, maintained and presented by one person. The code must read as if one careful developer wrote it by hand. When a rule above conflicts with simplicity, choose simplicity and mention it in your phase report.

- **Fewer, meaningful files.** Every file and folder must be easy to explain in a viva in one sentence. No folders that hold a single tiny file, and no `utils/`, `helpers/`, `common/` or `core/` dumping grounds.
- **No enterprise patterns.** No abstract base classes, factories, registries, dependency-injection frameworks, plugin systems or event buses. Use a `Protocol` only where tests need a fake model. Plain functions and a few dataclasses are enough.
- **Match the existing style.** Short functions, clear names, aligned assignments where the current code uses them, and comments only where the reason isn't obvious. No banner comments on every function, no docstrings that repeat the function name, and no emoji in code or logs.
- **Small dependency list.** Prefer the standard library, what's already in `requirements.txt`, and plain browser APIs. No frontend framework, no bundler, no ORM.
- **Readable tests.** One test file per module, with plain `assert`s and descriptive test names. Use few fixtures and no deep test helpers.
- **No speculative code.** Build only what a requirement needs. No configuration options, flags or extension points that nothing uses.
- **Small, readable diffs.** Each commit should be easy to review on its own.

## 6. Requirement notes

- **FR-1 (bad frames):** use mean brightness bounds plus variance of the Laplacian for blur. Run the check in the browser, and again on the server.
- **FR-5 (speeds and TTC):** compute from the `capture_ts` differences, never from frame counts.
- **FR-8 (openings):** shoulder width and clearance margin come from the user's setup profile.
- **FR-9 (one command per cycle):**
  - Exactly one of the nine commands per cycle. Do **not** add a tenth.
  - Either make `turn_left`/`turn_right` reachable, for example when the only opening is far to one side or the path is blocked ahead with a clear side, or document why they never fire.
  - Overhead obstacles are not in the SRS. Leave them out unless everything else is finished; if you add them, map them to `slow_down` with a detail string.
- **FR-10 (low confidence):** confidence comes from frame quality, the spread of depth values (`depth_sigma_*`) and track age. When confidence is low, restrict output to the cautious end of the §2.4 ordering.
- **FR-12–15 (guidance controller):**
  - a short distinct sound (earcon) per command via Web Audio; vibration (`navigator.vibrate`) for urgent ones
  - speak only when the command changes
  - `stop` interrupts any speech in progress
  - at most 15 messages a minute (NFR-13)
  - `step_left`/`step_right` no more often than once every 2 s
  - mute, verbosity and speech-rate controls, usable without sight
- **FR-16 / NFR-1 / NFR-3 (expansion check):**
  - Work on downscaled grayscale frames (about 96×72).
  - Run sparse block matching or Lucas–Kanade on a grid of points.
  - Subtract the mean (rotational) flow, then measure radial divergence in the central region to get time-to-contact.
  - Trigger `stop` when time-to-contact stays below the threshold for N consecutive frames.
  - Must run at ≥10 fps on a mid-range Android phone.
  - Unit-test it on synthetic frames that are scaled or translated.
- **FR-17 / NFR-2 (stale guidance):** discard any server result older than 2 s, or with a lower `seq` than one already handled.
- **FR-18–20 / §2.2 levels (capability state machine):**
  - L1 when the frame quality or the server reports poor visibility.
  - L2 when the server has been silent for about 2 s.
  - L3 when the expansion check has stopped.
  - L4 at the end of the session.
  - Announce every change with its cause, and repeat it every 60 s while reduced. Announce recovery. Log every change as an `event`.
  - Battery warnings via `navigator.getBattery` where the browser supports it.
- **FR-21 (start/stop without sight):** one large accessible control. Must work with TalkBack and VoiceOver.
- **FR-22 (fixed URL):** implement both options behind config, and **ask me which one to use**, because each needs my own account:
  - (a) an ngrok static domain started from the notebook
  - (b) a static redirect page on GitHub Pages that reads the current URL, which the notebook publishes on startup
- **FR-23 (spoken setup):**
  1. State the limits (not a replacement for the cane) and get the user's acknowledgement.
  2. Ask consent to send images.
  3. Camera field of view: use a preset or a measured value.
  4. Depth check: the user stands at a known distance from a wall; derive `depth_scale`, and reject setup if the error is too large.
  5. Left/right test: the user steps left, and the ego-motion classifier must report `stepping_left`. A failure blocks use.
  6. Shoulder width.
  Store the profile on the phone (browser storage) and send it to the server at session start.
- **FR-24–26 (logging and dashboard):**
  - Schema matching SRS §4: user, session, decision, agent, opening, event.
  - A schema-version table.
  - A bounded queue with a counter of dropped items.
  - Sessions closed on shutdown (`atexit`) and on stop.
  - Dashboard additions: guidance delay against target, time spent at each level, and drill-down from a decision to its agents and openings.
- **NFR-4 (≥2 decisions/s on a T4):** measure with `scripts/benchmark.py`. Try fp16, a depth age cap, and a smaller RAFT input. Report the real numbers, whatever they are.

## 7. Tests (map to SRS §8.2)

| Test | How | Runs on |
|---|---|---|
| T1 direction test | A deliberately swapped-polarity build must fail setup; mirrored synthetic flow must be detected | CPU + JS |
| T2 depth accuracy | `scripts/eval_depth.py` on photos or clips at known distances | GPU (I run it) |
| T3 detection/tracking | Recorded clips; check identity is kept and motion class is correct | GPU (I run it) |
| T4 frame-rate independence | Synthetic tracks sampled at 1.5, 5 and 15 fps give the same speed and TTC within tolerance | CPU |
| T5 openings | Synthetic depth maps: wall, blocked path, narrow gap, clear path; shoulder width varied | CPU |
| T6 decision rules | A fixture for every rule, plus a property test (`hypothesis`) that output is always exactly one valid command and that low confidence gives only cautious commands | CPU |
| T7 phone stop wins | Guidance-controller tests with fake timers: server `walk_forward` arriving before, during and after a phone `stop` | JS |
| T8 stale guidance | Delayed and out-of-order results are discarded | JS + integration |
| T9 speaking rules | Static scene gives no repeats; ≤15 messages a minute; `stop` interrupts; left/right alternation limit | JS |
| T10 capability levels | Each fault is injected: correct level, cause announced, repeated, recovery announced | JS + integration |
| T11 server loss | Mocked fetch fails mid-session, then recovers | JS |
| T12 accessibility | Manual checklist in `docs/testing/manual-checklist.md` (TalkBack, one hand) | Manual |
| T13 logging/privacy | No image files or columns anywhere; the writer never blocks the pipeline; sessions close; the full reason chain is stored | CPU |
| T14 two hours | `scripts/soak.py` loops a clip through the server; report crashes, memory, latency | GPU (I run it) |

Rules for tests:
- `pytest` must pass on a CPU machine with no GPU and no model downloads. Put GPU tests behind a `gpu` marker.
- Aim for at least 85% coverage on `interpretation/`, `decision/` and `session/`.
- Add a notebook cell that runs the GPU tests and scripts on Colab.

## 8. How to work

1. **Plan first.** Send me a phased plan (§10) with the final folder tree, the API contract (request and response JSON) and any deviations from this brief. **Wait for my approval** before writing code.
2. Work one phase at a time. In each phase: implement, write tests, run the full suite, then commit with a clear message such as `fix(interpretation): use measured frame times for TTC`. **Do not push.**
3. **Phase 0 must not change behaviour:** restructure, add tooling, add tests that pin down the current behaviour. Fixes start in Phase 1.
4. After each phase, give a short report: what changed, test results, and anything blocked.
5. **Do not touch** `SRS_12_Batch/`, `spl-3-materials/`, or the PDF and PPTX files in `docs/`. In `docs/SRS.md`:
   - you may add a "Platform limitations" section and status updates
   - never renumber, remove or reword requirements without asking me
6. **Ask me before you:**
   - add a heavy dependency
   - change what any requirement means
   - choose between the FR-22 options
   - delete anything that isn't clearly dead code
7. **Never invent measurements.** Anything that needs a GPU, a real phone or a real street stays marked as not run. Give me the exact commands or notebook cells to run it, and I will report back.

## 9. Definition of done

- `docs/traceability.md` maps every FR-1–26 and NFR-1–16 to the code that implements it and the test that checks it, or marks it as a **platform limitation** with the reason (see §3).
- `ruff check` is clean. `pytest` and `node --test tests/js` pass.
- `notebooks/run_on_colab.ipynb` still starts the whole app in three cells: clone, install, run. It prints the public URL.
- The README is rewritten for the new structure, setup flow, API, testing, and known limitations.
- A final summary lists:
  - requirements met
  - requirements met only partially, and why
  - measurements still pending on GPU or on a phone
  - remaining risks from the SRS appendix

## 10. Suggested phases

0. Restructure into `walksafe/`, add tooling and characterization tests. No change in behaviour.
1. Correctness fixes: defects §4.1–4.7, plus the T4, T5 and T6 tests.
2. Server API and per-session state: `/api/frame`, `capture_ts`, newest-frame-only, error handling, latency instrumentation, benchmark script.
3. Browser client: capture, quality check, guidance controller (FR-12–17), JS tests T7–T9.
4. Expansion check and arbitration (FR-16, NFR-1, NFR-3).
5. Capability state machine L0–L4, announcements and events (FR-18–20), tests T10–T11.
6. Accessible start/stop, spoken setup flow, user profile (FR-21, FR-23, FR-8, NFR-11).
7. Fixed URL (FR-22). Ask me which option first.
8. Logging schema to SRS §4, dashboard additions, dashboard auth, privacy checks (FR-24–26, T13).
9. GPU scripts and the Colab notebook (T2, T3, T14, NFR-4), manual checklist (T12).
10. Documentation: README, `traceability.md`, architecture notes, the SRS platform-limitations section, final summary.
