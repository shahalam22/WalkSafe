# Requirement traceability

Every functional and non-functional requirement in [SRS.md](SRS.md) §2, with the code that
implements it, the test that checks it, and its status. Status values:

- **Met**: implemented and checked by an automated test.
- **Met, measurement pending**: implemented and tested with fakes or synthetic data; the real
  figure needs a GPU, a phone or a street, and has **not been run**.
- **Partial**: part of it is implemented; the rest is explained.
- **Platform limitation**: the browser or Colab cannot provide it; see SRS "Platform Limitations".

**Mode.** The phone page has two modes (decided 2 Oct 2026). **Full safety** applies everything
below. **Simple**, the default while testing, works like the prototype: it does not drop late
answers (FR-17, NFR-2), keeps no capability levels (FR-18, FR-19, NFR-7) and runs no stop check on
the phone (FR-16, NFR-1, NFR-3). Those rows are met only in Full safety mode.

Paths are relative to the repository root. `tests/js/*` run with `node --test`; everything
else under `tests/` runs with `pytest` on a CPU, apart from `tests/gpu`.

## Functional requirements

| ID | Requirement (short) | Implemented in | Tested by | Status |
|---|---|---|---|---|
| FR-1 | Rear camera, capture time on every frame, reject bad frames | `web/js/capture.js` (rear camera, `clockMs`), `web/js/quality.js`, `interpretation/quality.py` (checked again on the server) | `tests/js/quality.test.js`, `tests/test_quality.py`, `tests/test_pipeline.py::test_dark_frame_is_rejected…` | Met; thresholds untuned |
| FR-2 | Distance to obstacles and ground | `perception/depth.py` (Depth Anything V2 Metric by default, DepthPro selectable), depth scale from setup | `tests/gpu/test_models.py`; T2 `scripts/eval_depth.py` | Met, measurement pending (T2) |
| FR-3 | Detect and track people, cyclists, vehicles | `perception/detection.py` (YOLOv8n restricted to FR-3 classes, ByteTrack per session) | `tests/test_agents.py::test_only_agent_classes…`, `tests/gpu/test_models.py` (identity kept); T3 `scripts/eval_tracking.py` | Met, measurement pending (T3) |
| FR-4 | Motion: approaching, receding, crossing, static | `interpretation/agents.py::classify_motion` | `tests/test_agents.py` | Met |
| FR-5 | Distance, approach speed, TTC from measured frame times | `interpretation/agents.py` (line fit against capture times), `server.py` passes the phone's `capture_ts` | `tests/test_agents.py::test_t4_*` at 1.5, 5, 15 fps | Met |
| FR-6 | Risk: critical, high, moderate, low | `interpretation/agents.py::risk_level` | `tests/test_agents.py::test_risk_levels` | Met |
| FR-7 | Openings, width in metres | `interpretation/openings.py` | `tests/test_openings.py` (T5) | Met; tape-measure check pending (checklist E2) |
| FR-8 | Compare with shoulder width + margin; report when none | `openings.py` (`wide_enough`, `best_opening`), `decision.py` R2, shoulder width from setup | `tests/test_openings.py::test_t5_narrow_gap_depends_on_shoulder_width`, `tests/test_decision.py::test_r2_…` | Met |
| FR-9 | Exactly one of nine commands, fixed order, cautious default | `decision.py` (R1 to R10) | `tests/test_decision.py` (each rule, and a `hypothesis` property) | Met |
| FR-10 | Cautious commands only when confidence is low | `interpretation/quality.py::confidence`, `decision.py::decide` (downgrade); `web/js/guidance.js` at L1 | `tests/test_decision.py` (property and downgrade), `tests/js/capability.test.js::guidance at L1…` | Met |
| FR-11 | Record the rule and values | `decision.py` (reason string), `storage/writer.py` | `tests/test_decision.py::test_reason_carries…`, `tests/test_writer.py::test_t13_a_decision_is_stored…` | Met |
| FR-12 | Speak, distinct sound, vibrate for urgent | `web/js/speech.js` (earcons, speech), `web/js/guidance.js` (vibration for stop and yield) | `tests/js/guidance.test.js` (with a recording output) | Met; no vibration on iOS (platform limitation) |
| FR-13 | Speak only when the situation changes | `guidance.js::judge` (command change) | `tests/js/guidance.test.js::T9 a static scene is spoken once` | Met |
| FR-14 | Interrupt speech for a stop | `guidance.js` (`interrupt` only for stop), `speech.js::speak` | `tests/js/guidance.test.js::T9 only a stop interrupts speech`, T7 | Met |
| FR-15 | Mute, verbosity, speech rate during a session | `web/js/main.js` settings, `guidance.js` (`muted`, `verbosity`), `speech.js` (`rate`) | `tests/js/guidance.test.js` (detail by verbosity, mute); checklist B3 to B5 | Met; screen-reader use pending (checklist B) |
| FR-16 | Server never overrides or delays a phone stop | `web/js/expansion.js`, `guidance.js::phoneStop` / `judge` | `tests/js/guidance.test.js` (T7), `tests/js/expansion.test.js` | Met |
| FR-17 | Discard guidance that is too old | `guidance.js::judge` (2 s, sequence) | `tests/js/guidance.test.js` (T8), `tests/test_server.py::test_out_of_order…` | Met |
| FR-18 | Announce loss of capability with cause; repeat | `web/js/capability.js` | `tests/js/capability.test.js` (T10) | Met |
| FR-19 | Announce on any fault; never fail silently | `capability.js` (server silence, check stopped or threw), `server.py` (500 and fault event) | `tests/js/capability.test.js`, `tests/test_server.py::test_pipeline_fault…`, `::test_a_fault_is_logged…` | Met |
| FR-20 | Warn before low battery or overheating | `capability.js::battery` (20 %, 10 %, shutdown at 5 %) via `navigator.getBattery` | `tests/js/capability.test.js::T10 battery warnings…` | Partial: battery on Chrome for Android only; overheating is a platform limitation |
| FR-21 | Start and end with one action, no sight needed | `web/index.html` (one large button), `main.js` | checklist B1, B6 | Met, manual check pending |
| FR-22 | Find the server automatically | `pages.py` (publishes page + `server.json`), `api.js::findServer`, `server.py` `/server.json` | `tests/test_pages.py`, `tests/js/api.test.js` (FR-22) | Met; first real publish needs the one-time Pages setup |
| FR-23 | Spoken setup: field of view, mounting, depth check, left/right test that blocks use | `web/js/setup.js`, `server.py` `/api/setup/depth`, `/api/setup/direction`, `server.require_setup` | `tests/js/setup.test.js` (T1), `tests/test_server.py::test_depth_check…`, `::test_setup_is_optional…` | Partial by decision (2 Oct 2026): setup is optional, so a failed direction test blocks use only with `server.require_setup: true` |
| FR-24 | Record every decision with its values; no images | `storage/schema.py`, `storage/writer.py` | `tests/test_schema.py::test_no_column_can_hold_an_image`, `tests/test_writer.py`, `tests/test_server.py::test_no_frame_is_written_to_disk` | Met |
| FR-25 | Logging never delays guidance | `storage/writer.py` (bounded queue, drops counted) | `tests/test_writer.py::test_t13_the_writer_never_blocks…` | Met |
| FR-26 | Summaries, delay against target, time per reduced level | `storage/queries.py`, `ui/dashboard.py` | `tests/test_queries.py` | Met |

## Non-functional requirements

| ID | Requirement (short) | Implemented in | Tested by | Status |
|---|---|---|---|---|
| NFR-1 | Phone warnings within 250 ms | `expansion.js` (no network), `guidance.js` (stop says one word, not rate-limited) | `tests/js/expansion.test.js` (synthetic) | Met, measurement pending (checklist C2). Risk: confirming over 3 frames at 12 fps itself takes about 250 ms |
| NFR-2 | Server guidance within 1.2 s; older than 2 s discarded | discard: `guidance.js` (`phone.stale_after_ms`); delay: `server_ms`, `delay_ms` in the log | `tests/js/guidance.test.js` (T8) | Not met in testing (2 Oct 2026): the gradio.live round trip alone was over 2 s, so the discard limit is relaxed to 4 s until a closer tunnel or server is used |
| NFR-3 | On-phone check at ≥ 10 fps | `expansion.js` on 96×72, `capture_fps` 12 | `tests/js/expansion.test.js` (about 2.5 ms per frame in desktop Node) | Met, measurement pending on a phone (checklist C1, `?debug=1`) |
| NFR-4 | ≥ 2 decisions/s on a T4 | DepthPro in the background (`models.depth_in_background`), fp16 and smaller RAFT input as options | `scripts/benchmark.py`, `tests/test_pipeline.py::test_slow_depth_runs_in_the_background…` | Measurement pending; decisions no longer wait for DepthPro (6.6 s a frame on a T4), but the depth map behind them can be that old, which breaks the 0.4 s cap of SRS §7.3 by decision |
| NFR-5 | Every failure leaves the system more cautious | rejected frames give `slow_down`; low confidence downgrades; levels L1 to L3 | `tests/test_decision.py::test_lower_confidence_never…` (property), `tests/js/capability.test.js` | Met |
| NFR-6 | Left and right never reversed | `ego.py` (sign of motion), `agents.py`/`openings.py` (image right = user's right, never mirrored), setup direction test | `tests/test_ego.py::test_t1_*`, `tests/test_agents.py::test_side_follows…`, `tests/test_decision.py::test_left_and_right…`, `tests/js/setup.test.js` | Met; on-phone check pending (checklist A1, A2) |
| NFR-7 | No fault signalled by silence alone | `capability.js` (spoken, repeated, never muted, vibration from L2) | `tests/js/capability.test.js` | Met |
| NFR-8 | Every requirement in the Appendix has an automated test | see the risk table below | — | Met for everything testable without a GPU or a phone |
| NFR-9 | Two hours without crash or unannounced loss | session expiry, track pruning, bounded queues | `scripts/soak.py` (T14) | Measurement pending; free Colab cannot guarantee two hours (platform limitation) |
| NFR-10 | Losing the server reduces capability, never ends the session | `capability.js` (L2), `main.js` reconnects and re-reads `server.json` | `tests/js/capability.test.js` (T11) | Met |
| NFR-11 | Everything reachable without sight | one large control, spoken setup, labelled buttons | checklist B | Met in design, manual check pending |
| NFR-12 | Earphones supported, never required | output through the phone speaker | checklist B9 | Met in design, manual check pending |
| NFR-13 | At most 15 spoken messages a minute | `guidance.js::judge` | `tests/js/guidance.test.js::T9 never more than 15…` | Met; a stop is exempt (safety first), and so are capability announcements, which are rare |
| NFR-14 | Battery ≤ 25 % of 4000 mAh per hour | small frames, one request in flight | checklist C3 | Measurement pending; the screen must stay on (platform limitation) |
| NFR-15 | Data ≤ 250 MB per hour | JPEG quality 0.6 at 518 px (about 30 KB), at most one frame in flight | checklist C4 | Measurement pending; about 216 MB/h at 2 frames/s is an estimate, not a measurement |
| NFR-16 | One config file; replaceable models | `config.py` (including the phone section served as `/js/config.js`), `perception/__init__.py` Protocols | `tests/test_server.py::test_every_setting_the_page_reads…`, fakes in `tests/conftest.py` | Met |

## Risks (SRS Appendix) and their tests

| Risk | Requirements | Automated tests | Still open |
|---|---|---|---|
| R1 walks into something missed | FR-7, FR-8, FR-9, FR-16 | T5, T6, T7, expansion tests | Glass and thin poles; real-scene accuracy (T2, checklist E) |
| R2 acts on a stale scene | FR-17, NFR-2 | T8, server 409 and 429 tests, depth age test | Real delays (checklist C5) |
| R3 kerbs and stairs | §1.4, FR-23 | Limits stated first in setup (`setup.test.js`) | Out of scope; the cane remains essential |
| R4 left and right swapped | FR-23, NFR-6 | T1 (mirrored flow, reversed result blocks setup) | Setup on each real phone (checklist A) |
| R5 earphones block hearing | FR-12, NFR-12 | Vibration for urgent commands (T7, T9) | Street audibility (checklist B9); no vibration on iOS |
| R6 over-trust | FR-18, FR-23 | Limits stated first; changes always announced (T10) | Only user trials can show this (SRS §8.3) |
| R7 guidance stops unnoticed | FR-18, FR-19, FR-20, NFR-7 | T10, T11, fault logging | Overheating cannot be detected |
| R8 false stops | FR-5, NFR-6 | T4, expansion tests (no stop on sideways motion or slow approach) | Thresholds untuned; false-stop rate on real walks |
| R9 confident but wrong in poor light | FR-1, FR-10 | Quality tests, confidence downgrade, L1 | Thresholds untuned |
| R10 bystanders filmed without consent | FR-24 | Consent required (403), no image columns, no files on disk | — |
| R11 Colab session ends | FR-22, NFR-10 | T11, Pages lookup tests | Free Colab limits |
