# WalkSafe — Mid Presentation Slide Content

Source: `docs/1439_SPL_3_SRS.md` (final SRS)
Template: `docs/bsse1439_SPL_3_Proposal.pptx.pptx` — keep **Slide 1 (title)**, **Slide 9 (references)**, **Slide 10 (thank you)** as-is.

Deck plan: **17 slides + 4 backup**

| # | Slide | Source |
| :-- | :-- | :-- |
| 1 | Title | reuse from proposal |
| 2 | Overview / contents | new |
| 3 | Project Overview — the gap | §1.2 |
| 4 | Project Overview — what WalkSafe is | §1.3, Abstract |
| 5 | Scope | §1.4 |
| 6 | Functional Requirements — coverage map | §2.1 |
| 7 | Functional Requirements — safety-critical | §2.1 |
| 8 | Non-Functional Requirements — the numbers | §2.2 |
| 9 | Commands & Levels | §2.4, §2.2 |
| 10 | Use Case — Level 0 | fig01 |
| 11 | Use Case — Level 1 (4 modules) | fig02 |
| 12 | Use Case — Level 1.2 (core module) | fig04 |
| 13 | Activity — Guidance Loop | fig08 (body caption) |
| 14 | Activity — Capability Change & Recovery | fig09 |
| 15 | ER Diagram | fig10 |
| 16 | AI Pipeline + Model Selection | fig13, §7.2 |
| 17 | Demo | screenshots (to capture) |
| 18 | Status & What's Next | §1.5, §9 |
| 19 | References | reuse from proposal |
| 20 | Thank You | reuse from proposal |
| B1–B4 | Backup: UC 1.1 / 1.3 / 1.4, Component, Deployment, Test Plan, Gantt | fig03, 05, 06, 11, 12, 14 |

---

## Slide 2 — Overview

```
Overview

01  Project Overview
02  Requirements
03  Use Case Diagram
04  Activity Diagram
05  ER Diagram
06  AI Pipeline
07  Demo
08  Status & Timeline
09  References
```

---

## Slide 3 — Project Overview: The Gap

**Title:** The 1–8 Metre Gap

Three-column / three-card layout:

| White Cane | GPS Apps | **1–8 m — nobody** |
| :-- | :-- | :-- |
| Finds the ground and obstacles within **about one step** | Gives route-level direction over **tens of metres** | The range where a pedestrian decides to **slow down, move aside, or wait** |

Bullets below:

- A cyclist approaching from the side falls outside both — the cane reaches it too late, and the map does not know it exists.
- This is the **anticipatory** range: slow down, step left, wait for someone to pass.
- A smartphone camera can capture what is needed. Current vision models can process it.
- The hard part is **not perception — it is delivery.** Guidance must arrive fast enough to act on, stay quiet when nothing needs saying, and clearly announce when it cannot be trusted.
- A system that advises well most of the time and **falls silent when it fails** is worse than no system, because the user has already learned to rely on it.

> Speaker note: the last bullet is the design principle the whole report hangs on. Say it out loud.

---

## Slide 4 — Project Overview: What WalkSafe Is

**Title:** WalkSafe — A Real-Time Navigation Assistant

- **Input:** one smartphone rear camera. No LiDAR, no wearable, no extra hardware.
- **Perception:** three pretrained models — **DepthPro** (depth in metres), **YOLOv8n + ByteTrack** (detect and follow people, cyclists, vehicles), **RAFT-Small** (image motion).
- **Decision:** deterministic rules reduce the whole scene to **one spoken instruction** from a fixed **nine-command vocabulary**.
- **Split by urgency, not by difficulty** — the central finding of the work:
  - **On the phone:** one cheap question — is something closing in? No model, no network. Warns within **250 ms**.
  - **On the server:** depth, agents, risk, openings, command choice. Budget **1.2 s**.
  - **A phone `stop` always overrides the server** — the fast path can only ever make the system more cautious.
- **Accountability:** every decision is logged with the values behind it. **No images are stored at any point.**
- **Positioning:** a *supplementary* aid. Every requirement assumes the user also has a cane or guide dog.

> Speaker note: the asymmetry justification — a wrong stop from the phone costs a needless pause; a wrong "walk forward" the phone was not allowed to veto costs a collision.

---

## Slide 5 — Scope

Two columns.

**In scope**

- Smartphone client + remote GPU inference service
- Depth, agent detection and tracking, optical-flow motion
- Per-agent distance, time-to-collision, risk level
- Traversable corridor detection, width in **metres**
- Nine-command vocabulary — speech + earcon + haptic
- On-device collision check that works with **no network** and overrides remote guidance
- Audible degradation reporting — connectivity, visibility, occlusion, battery, thermal
- Guided **non-visual** calibration — FOV, mounting, shoulder width, left/right polarity
- Screen-reader operation with the screen off
- Session logging of derived metrics + analytics view

**Out of scope**

- Route planning, destinations, map integration
- Reading text or signs; recognising specific people
- Traffic signals; deciding when to cross a road
- Kerbs, stairs, drop-offs — monocular depth is unreliable at downward steps, so this is **declared a limitation, not attempted**
- Indoor mapping
- Replacing a cane, guide dog, or O&M training

> Speaker note: the kerb exclusion is the honest one. Expect a question on it — answer that monocular depth fails at downward steps and a wrong "clear" at a kerb is exactly the failure mode we refuse to risk.

---

## Requirements — how to present 42 of them

**The problem:** 26 functional + 16 non-functional = **42 requirements.** A 42-row table on a slide gets read by nobody and answers no question an examiner has.

**Recommendation — three slides doing three different jobs:**

1. **Coverage map (Slide 6)** — all 26 FRs collapsed into the 7 functional areas, one line each. Proves completeness in 7 rows instead of 26.
2. **Safety-critical (Slide 7)** — the 6 requirements verbatim that *are* the contribution. These answer "how do you know it's safe?"
3. **The numbers (Slide 8)** — the latency and budget NFRs. These answer "how fast is it?"

Everything else stays in the report. If an examiner wants FR-14, the traceability matrix in §6.2 has it — and mentioning that on Slide 7 is stronger than showing it.

---

## Slide 6 — Functional Requirements: Coverage

**Title:** Functional Requirements — 26 requirements, 7 areas

| Area | FRs | What it covers |
| :-- | :-- | :-- |
| **Capture and Perception** | FR-1 – FR-3 | Timestamped frames, reject unusable ones; depth to obstacles and ground; detect and track people, cyclists, vehicles |
| **Interpretation** | FR-4 – FR-6 | Classify motion (approaching / receding / crossing / static); distance, approach speed, time-to-collision; assign risk level |
| **Navigation Decision** | FR-7 – FR-11 | Find openings and measure width in metres; compare against shoulder width; **one command per cycle** by fixed-order rules; downgrade when unsure; record the reason |
| **Guidance Delivery** | FR-12 – FR-15 | Speech + earcon + haptic; **silent unless something changed**; interrupt for a `stop`; mute and adjust mid-session |
| **Safety and Failure Handling** | FR-16 – FR-20 | Phone `stop` is never overridden; discard stale guidance; announce every loss of capability with its cause; **never fail silently**; warn before battery or heat ends the session |
| **Setup, Session, Accessibility** | FR-21 – FR-23 | One sightless action to start/end; find the server automatically — the user never handles a link; spoken calibration with a blocking left/right test |
| **Logging and Review** | FR-24 – FR-26 | Log every decision with its values, **store no images**; logging never delays guidance; session summaries and drill-down |

Footer line: *Each requirement maps to a risk in the Appendix, and to a component, use case, and test in the traceability matrix (§6.2).*

---

## Slide 7 — Functional Requirements

**Title:** Functional Requirements — 26 requirements, 7 areas

**Selection rule:** one flagship requirement per functional area. Seven rows that stand in for all 26 — coverage, not a favourites list.

| Area | The requirement that carries it |
| :-- | :-- |
| **Capture & Perception** · FR-1–3 | **FR-2** — Estimate distance to obstacles and to the ground ahead |
| **Interpretation** · FR-4–6 | **FR-5** — Distance, approach speed and time-to-collision per agent, from measured frame times |
| **Navigation Decision** · FR-7–11 | **FR-9** — Exactly one command per cycle from the nine, by fixed-order rules, cautious default |
| **Guidance Delivery** · FR-12–15 | **FR-12** — Speak each command, play its earcon, vibrate for urgent ones |
| **Safety & Failure Handling** · FR-16–20 | **FR-19** — Announce that guidance has stopped on any fault. **Never fail silently** |
| **Setup & Accessibility** · FR-21–23 | **FR-23** — Spoken setup: FOV, mounting, depth check, and a left/right test that **blocks use** if it fails |
| **Logging & Review** · FR-24–26 | **FR-24** — Record every decision with its values. **Store no images** |

Footer: *All 42 requirements are traced to a component, use case, and test in §6.2.*

> Speaker notes — the four worth naming aloud even though they are not on the slide:
> — **FR-16** a `stop` from the phone is never overridden or delayed by the server. The keystone; the architecture slide covers it.
> — **FR-13** speak only when the situation changes. Silence is the normal state.
> — **FR-17** guidance older than 2 s is discarded, not spoken late.
> — **FR-8** openings are compared against *this user's* shoulder width plus a clearance margin.

**Swaps if you want a different emphasis:** FR-16 in place of FR-19 (architecture over honesty) · FR-3 in place of FR-2 (tracking over depth) · FR-13 in place of FR-12 (silence over delivery).

⚠️ **This makes Slide 6 redundant** — it maps the same 7 areas. Use this slide alone and drop Slide 6, which brings the deck to 19.

---

## Slide 8 — Non-Functional Requirements

**Title:** Non-Functional Requirements — 16 requirements, 5 areas

**Area 1 — Safety** · NFR-5–8 · **Three Guarantees**, set large; these are the slide

- Every failure leaves the system **more** cautious — never less *(NFR-5)*
- Left and right are **never** reversed *(NFR-6)*
- No fault is signalled by **silence alone** *(NFR-7)*

**The other four areas** — one line each, smaller

- **Performance** — a hard deadline for phone warnings, a looser one for server guidance; late guidance is discarded, not spoken *(NFR-1–4)*
- **Reliability** — a long session runs without a crash or an unannounced loss of capability; no single dependency failure ends a session *(NFR-9, 10)*
- **Accessibility** — everything reachable without sight; earphones optional, because the user must hear the street *(NFR-11–13)*
- **Resources** — bounded battery and data; every threshold in one config file, models swappable without touching the rules *(NFR-14–16)*

> Speaker notes:
> — **No numbers on this slide by design.** The latency figures belong to the architecture slide, where they justify the phone/server split instead of sitting as a list. Saying them twice spends them.
> — They are also **targets, not measurements** — T7 and T14 are planned, not run. If asked for figures, give them and say exactly that. Volunteering unverified numbers invites "have you measured it?"; answering the question when asked does not.
> — **NFR-6** sounds trivial and is the most dangerous requirement in the document. A build with left and right swapped walks the user into traffic and the user cannot tell. That is why the calibration direction test **blocks use** on failure.
> — **NFR-8** (every safety requirement has an automated test) is deliberately **not** on this slide. It stays in the SRS, but on the deck it belongs to **D4 — Planned** on the status slide. An invariant the audience can't see satisfied reads as a promise; keep promises on the timeline slide, not the safety slide.

---

## Slide 9 — Commands & Levels

**Title:** Commands & Levels

**Left — the vocabulary** (most cautious → least; the order *is* the downgrade path)

| # | Command | Meaning |
| :-- | :-- | :-- |
| 1 | `stop` | Stop moving forward now |
| 2 | `yield` | Wait for an agent to pass |
| 3 | `slow_down` | Reduce pace |
| 4 | `walk_forward_slow` | Continue ahead with caution |
| 5 | `step_left` | Move left, keeping heading |
| 6 | `step_right` | Move right, keeping heading |
| 7 | `turn_left` | Change heading left |
| 8 | `turn_right` | Change heading right |
| 9 | `walk_forward` | Continue ahead, path clear |

**Right — capability levels** (each step more cautious than the last, each **announced with its reason**)

| Level | Condition | Behaviour |
| :-- | :-- | :-- |
| **L0** | Everything working | Full command vocabulary |
| **L1** | Poor visibility — glare, rain, blur | Cautious commands only; announce reduced confidence |
| **L2** | Server unreachable | Obstacle warnings only; announce loss of route guidance |
| **L3** | On-phone check unavailable | Announce that guidance has stopped; issue none |
| **L4** | Battery exhausted or user ends session | Announce shutdown with reason |

> Speaker note: L2 is the *normal* case, not the exception — free Colab sessions end after a few hours and may not get a GPU at all. Losing the server reduces capability; it never ends the session (NFR-10).

---

## Slide 10 — Use Case Diagram: Level 0

**Image:** `docs/figures/fig01.png`

**Caption:** Figure 1 — Level 0 (WalkSafe System)

- **Primary actors:** Pedestrian · O&M Instructor · Researcher
- **Secondary actors:** Phone Camera · Speech Engine · Colab GPU Platform · Session Database
- The **pedestrian** is the main actor. The instructor and researcher use only the **setup and review** sides — they never appear in the walking loop.
- Four secondary actors, four distinct dependencies: frames in, speech out, compute remote, decisions stored.

---

## Slide 11 — Use Case Diagram: Level 1

**Image:** `docs/figures/fig02.png`

**Caption:** Figure 2 — Level 1 (Modules of WalkSafe)

| Module | Does | Note |
| :-- | :-- | :-- |
| **1. Setup and Session Management** | Spoken setup, session start/end, server lookup, capability announcements | **Nothing else runs until setup has passed** |
| **2. Scene Analysis and Decision** | Frames → phone collision check ∥ server scene analysis → fixed rules → one command | Phone warning **overrides** the server |
| **3. Guidance Delivery** | Speech + earcon + haptic, and the rules for **when to stay quiet** | The only module the pedestrian directly experiences |
| **4. Logging and Review** | Every decision with its values; dashboard summaries and drill-down | Makes it possible to ask afterwards *why* it said that |

---

## Slide 12 — Use Case Level 1.2: Scene Analysis and Decision

**Image:** `docs/figures/fig04.png`

**Caption:** Figure 4 — Level 1.2 (Scene Analysis and Decision System) · UC-3

The core module — four use cases:

1. **Frame Capture** — rear camera, timestamp every frame, discard frames too dark, bright, or blurred to trust.
2. **Phone Collision Check** — measures how fast the image is spreading outward. *Things that get closer get bigger*, so rapid expansion means something is closing in. **No model, no network** — which is exactly what makes it fast enough to warn in time.
3. **Scene Analysis (server)** — depth in metres; detect and track people, cyclists, vehicles; per-agent approach speed, time-to-collision, risk; walkable openings; user walking speed.
4. **Command Selection** — rules in fixed order, hazard avoidance before route choice, one of the nine commands. A phone `stop` overrides the server; stale commands are discarded, not passed on; the rule and values are recorded.

> Speaker note: the expansion check is the cheapest idea in the project and the one that makes the 250 ms budget possible. Explain the "closer = bigger" intuition — it lands immediately.

---

## Slide 13 — Activity Diagram: Guidance Loop

**Image:** the activity diagram captioned *"Guidance Loop"* in §3.2 — `docs/figures/fig08.png`

**Caption:** Figure 8 — Activity Diagram (Guidance Loop) · runs once per frame

- Runs **once per frame**.
- The phone check and the server work **at the same time** and meet at the **arbitration** step.
- Arbitration is where FR-16 lives: a phone `stop` wins, whatever the server said and whenever it arrived.
- Then FR-17: guidance older than 2 s is dropped rather than spoken late.
- Then FR-13: if the command has not changed, say nothing. **Silence is the normal state.**
- The **double-bordered box** is the hand-off to the capability flow on the next slide — an unusable frame, a phone check that has stopped, or a server that does not answer all become inputs there.

---

## Slide 14 — Activity Diagram: Capability Change and Recovery

**Image:** `docs/figures/fig09.png`

**Caption:** Figure 9 — Activity Diagram (Capability Change and Recovery)

- Runs **alongside** the guidance loop for the whole session — not a subroutine of it.
- Inputs: the double-bordered box from the guidance loop, **plus** battery and temperature readings.
- Every step down is **announced with its reason**, and the announcement **repeats** while capability stays reduced.
- Recovery is automatic — the app reconnects on its own and announces that full guidance is back.
- The whole point: **silence is never mistaken for everything being fine.**

> Speaker note: if you only have time for one activity diagram, show this one. It is the part of the design that is unusual, and it is where the "worse than no system" argument from Slide 3 gets paid off.

---

## Slide 15 — ER Diagram

**Image:** `docs/figures/fig10.png`

**Caption:** Figure 10 — ER Diagram

- Records **what the app measured and what it decided — never what it saw.**
- **No images at any point.** A walk leaves behind numbers, not footage of the street: enough to reconstruct why any command was given, nothing that could identify a passer-by.
- Six entities:

| Entity | Holds |
| :-- | :-- |
| **user** | Calibration for this person and this phone — FOV, mount height and pitch, depth scale, shoulder clearance, consent, and whether the depth check and direction test **passed** |
| **session** | One walk — start, end, end reason, decision count |
| **decision** | One command — captured/spoken timestamps, **delay_ms**, source (phone or server), command, **reason**, confidence, capability level, whether it was actually spoken |
| **agent** | Per tracked agent per decision — track_id, type, distance, approach speed, **ttc_s**, risk, motion class |
| **opening** | Per candidate opening per decision — direction, **width_m**, distance, whether chosen |
| **event** | Capability changes — cause, from_level, to_level |

- `decision` is keyed on **(session_id, sequence)**; `agent` and `opening` hang off that pair, so a single decision can be replayed with every value that produced it — which is what FR-11 requires.
- `depth_check_passed` and `direction_test_passed` are stored on `user` because onboarding is **rejected** if either fails.

---

## Slide 16 — AI Pipeline

**Image:** `docs/figures/fig13.png`

**Caption:** Figure 13 — AI Pipeline

**The headline, big on the slide:**

> ### The models measure. The rules decide.

- Every AI component produces a **number** — depth in metres, boxes with identities, a motion field.
- Everything after that is **ordinary, inspectable code**.
- That is what makes it possible to say afterwards exactly why a command was issued (FR-11). A vision-language model describing the scene could not.
- **Nothing is trained or fine-tuned.** All models are pretrained and used as they are.

**Model selection**

| Where | Model | Why this one | Also considered |
| :-- | :-- | :-- | :-- |
| Server, depth | **DepthPro** | Depth **in metres** from one image — no separate scaling step. Sharp edges matter for narrow things like poles | MiDaS, Depth Anything — relative depth, needs extra scaling |
| Server, detection | **YOLOv8n + ByteTrack** | Small enough to leave GPU time for depth and flow. ByteTrack keeps the **same identity** across frames, which time-to-collision depends on | Larger YOLO — more accurate, pushes past the 1.2 s budget |
| Server, motion | **RAFT-Small** | Reasonable accuracy for the cost; drives the user's walking speed in session summaries | Farnebäck — cheaper, too noisy |
| Phone | **No model** | Frame-to-frame expansion only. This is *why* it fits in 250 ms | — |

> Speaker note: "no model on the phone" is a design decision, not a shortcut. Say it that way.

---

## Slide 17 — Demo

Screenshots to capture (none are in the repo yet — see the capture list below).

**Layout:** 2×2 grid, or split across two slides — *Navigation* and *Dashboard*.

**Captions:**

1. **Navigation view** — live camera on the left, fusion panel and advisory strip on the right (`ui/layout.py`)
2. **Fusion panel** — detected agents with distance, time-to-collision, and risk; depth map; detected openings with width in metres
3. **Dashboard — summary** — total frames, average speed, agent encounters, critical events
4. **Dashboard — distributions** — navigation commands, agent risk levels, user actions
5. **Dashboard — speed profile** — walking speed over one session
6. **A logged decision row** — command, reason, confidence, delay_ms, and the agents behind it. **No image column anywhere.**

Closing line for the slide: *Prototype: perception pipeline + decision engine + logging + dashboard, running end-to-end on a Colab T4.*

---

## Slide 18 — Status & What's Next

**Title:** Where the Project Stands

| # | Deliverable | Status |
| :-- | :-- | :-- |
| **D1** | **Working prototype** — depth, detection and motion together on a Colab GPU; rule-based decision engine; browser interface | ✅ **Complete** |
| **D2** | **Logging and dashboard** — SQLite record of every decision and the values behind it; command, risk and speed summaries | 🔄 **In progress** |
| **D3** | **Smartphone application** — capture, on-phone collision check, server guidance, speech; spoken setup; screen-reader support | 🔄 **In progress** |
| **D4** | **Test suite and test clips** — automated tests for the safety requirements, plus clips with known distances | ⏳ **Planned** |
| **D5** | **Final report and demonstration** | ⏳ **Planned** |

**Remaining work (August):**

- Correct the parts of the prototype that behave incorrectly
- Build what does not exist yet: **on-phone collision check**, **guidance delivery**, **capability levels L0–L4**, **spoken setup flow**
- Automated tests T1–T14 against the safety requirements

**Validation with users** — needs ethics approval and an instructor present, so it is scheduled **after** the report deadline:
O&M instructor reviews the vocabulary → closed course with known obstacle positions → supervised walks on familiar routes → unfamiliar routes and poor conditions (*the only way to see whether users start over-trusting the app*).

> Speaker note: be direct that stages 2–4 are post-deadline. "A tool meant for blind travellers cannot be judged without them" is the line from the acknowledgement — it is the right note to end the status slide on.

---

## Slide 19 — References

Reuse the proposal reference slide. It already covers RAFT, ByteTrack, Depth Pro, YOLOv8, WHO, and Sound of Vision. Optionally add:

```
[7]  Y. Zhang et al., "ByteTrack" — cited as [2]; keep numbering as-is if unchanged.
```

No changes needed unless you cite something new in the report.

---

## Slide 20 — Thank You

Reuse the proposal slide unchanged.

---

# Backup slides (after Thank You — for Q&A)

**B1 — Component Diagram** — `docs/figures/fig11.png` (Figure 11). 13 components; use the responsibilities table in §5.2 if asked who talks to whom.

**B2 — Where Things Run** — `docs/figures/fig12.png` (Figure 12). Two-place deployment. The point to make: a small always-on **lookup service** solves the changing Colab URL — the notebook reports where it is on startup, the phone always asks the same fixed address, and a blind user never reads a link (FR-22).

**B3 — Test Plan** — the T1–T14 table from §8.2. Lead with the unusual balance: *for most software, testing checks that features work; here a good part of it checks that **failures** behave correctly.* Best two examples: **T1** (a build with left and right deliberately swapped must be **blocked** by the direction test) and **T7** (assert a phone `stop` while the server sends `walk_forward` at full confidence — arriving before, during, and after — the stop is spoken every time and the server command is never spoken or blended).

**B4 — Gantt Chart** — `docs/figures/fig14-gantt.png`.

**B5 — Use Case Levels 1.1 / 1.3 / 1.4** — `fig03.png`, `fig05.png`, `fig06.png`, one per slide, for setup, guidance delivery, and logging questions.

---

# Screenshots to capture for Slide 17

Run `python app.py` (Colab) for 1–2 and `python -m ui.dashboard` for 3–5.

| # | Shot | Why it earns its place |
| :-- | :-- | :-- |
| 1 | Navigation tab, full window — webcam feed + fusion panel + advisory strip | Shows the system working end-to-end in one frame |
| 2 | Fusion panel cropped — boxes with distance / TTC / risk labels, depth map, opening width in metres | Proves FR-2, FR-3, FR-5, FR-6, FR-7 are real and not just specified |
| 3 | Dashboard metric row — total frames, avg speed, agent encounters, critical events | FR-26 |
| 4 | Dashboard charts — command distribution, risk levels, user actions | FR-26; also shows the vocabulary actually being exercised |
| 5 | Dashboard speed profile for one session | Shows RAFT flow → walking speed working |
| 6 | A `decision` row with its `agent` rows — terminal `sqlite3` query or a dataframe view | FR-11 and FR-24 in one image: full reason chain, **no image column** |

If time is short, capture **1, 2, and 4** — they cover perception, decision, and review.

---

# One fix for the SRS

The figure list in the front matter has **Figures 7 and 8 swapped** relative to the body captions:

- Front-matter list: `7 — Per-Frame Guidance Loop`, `8 — Session Start and Calibration`
- Body captions in §3.2: `Figure 7: Setup and Session Start`, `Figure 8: Guidance Loop`

The body order is the correct one (Figure 8's caption text describes the per-frame loop and refers forward to Figure 9). Fix the front-matter list before final submission.
