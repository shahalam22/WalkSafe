# WalkSafe manual test checklist

These are the checks that need a real phone, a real street or a person; automated
tests cover the rest (see the README's Testing section). Fill in **Result** and
**Notes** as you go. Anything not yet done stays **Not run**. Never estimate a
figure; leave it blank until it is measured.

Record for each run: date, phone model, Android/iOS version, browser version,
server commit (`git log --oneline -1`) and whether earphones were used.

## Before you start

- The server is running from the Colab notebook and logs `WalkSafe is live at …`.
- The phone opens the fixed GitHub Pages address (or the live URL directly).
- Add `?debug=1` to the address for the measurements in section C. It shows the
  on-phone check rate.
- For section B, turn on the screen reader (TalkBack on Android, VoiceOver on iOS)
  before opening the page.

## A. Setup and direction (T1, FR-23)

| # | Check | Expected | Result | Notes |
|---|---|---|---|---|
| A1 | Run setup, stepping **left** at the tone | "Direction test passed" | Not run | |
| A2 | Run setup again, stepping **right** at the tone (a reversed build looks like this) | Setup refused: "left and right appear reversed"; Start runs setup again | Not run | |
| A3 | Depth check at 1.5 m from a flat wall | Passes; measured distance within 25 % | Not run | |
| A4 | Depth check claiming 3 m while standing at 1.5 m | Fails; offered to try again | Not run | |
| A5 | Hold the phone pointing at the ground during setup | Asked to hold it level | Not run | |
| A6 | Decline consent | Phone-only mode announced; nothing sent (server log shows no session) | Not run | |

## B. Accessibility without sight (T12, FR-15, FR-21, NFR-11, NFR-12)

Do every task with the screen reader only, one-handed, holding a cane in the other hand.

| # | Task | Expected | Result | Notes |
|---|---|---|---|---|
| B1 | Find and press Start | The large button is reached at once and announced as "Start guidance" | Not run | |
| B2 | Complete the whole setup | Every question is heard; every answer is a labelled button | Not run | |
| B3 | Mute, then unmute, during a session | Spoken confirmation; guidance stops and resumes | Not run | |
| B4 | Change Detail to Detailed, then Brief | Details are spoken only in Detailed and Normal (for hazards) | Not run | |
| B5 | Change Speech rate | Next message at the new rate | Not run | |
| B6 | Stop the session | "WalkSafe is shutting down: guidance ended by you." | Not run | |
| B7 | No link was ever read or typed | Holds for the whole test | Not run | |
| B8 | The screen reader and WalkSafe's own speech do not make guidance unusable when they overlap | Note how often they clash | Not run | |
| B9 | Phone speaker only, no earphones | Guidance is audible on a busy street | Not run | |

## C. Measurements on the phone (NFR-1, NFR-3, NFR-14, NFR-15)

| # | Measure | How | Target | Result | Notes |
|---|---|---|---|---|---|
| C1 | On-phone check rate | Read `checks …/s` from the debug line over 2 minutes of walking | ≥ 10/s (NFR-3) | Not run | |
| C2 | Phone stop delay | Film the phone and an approaching object at 240 fps; count frames from the debug line's ttc crossing 1.5 s to the stop sound | ≤ 250 ms (NFR-1) | Not run | |
| C3 | Battery | Full charge, one hour of guidance with the screen on; read the battery percentage | ≤ 25 % of 4000 mAh per hour (NFR-14) | Not run | |
| C4 | Mobile data | Android: Settings → Network → Data usage for the browser over one hour | ≤ 250 MB per hour (NFR-15) | Not run | |
| C5 | Server guidance delay | Dashboard "Guidance on time" after a 20-minute walk | ≥ 95 % within 1.2 s (NFR-2) | Not run | |

## D. Guidance behaviour on the street (T7, T9, T10, T11)

| # | Check | Expected | Result | Notes |
|---|---|---|---|---|
| D1 | Stand still facing an open path for a minute | One message, then silence | Not run | |
| D2 | Walk toward a wall or a person until it is close | "Stop" with the earcon and vibration, interrupting any speech | Not run | |
| D3 | Play music in another app during a session | Guidance is still heard | Not run | |
| D4 | Cover the camera with a hand | L3 announced ("the camera view is blocked …"), repeated every minute, recovery announced | Not run | |
| D5 | Walk into a dark place | L1 announced with "poor visibility" | Not run | |
| D6 | Turn on aeroplane mode for 30 s, then off | L2 announced within about 2 s; "Full guidance restored" afterwards | Not run | |
| D7 | Stop the Colab runtime mid-session, then start it again | L2, the session carries on, then full guidance returns without touching the phone (T11) | Not run | |
| D8 | Let the battery drop below 20 % (Android Chrome) | "Battery at … percent" | Not run | |

## E. Openings and distances (T5, with the diagnostic view on)

Set `ui.diagnostic_view: true` in a YAML file passed through `WALKSAFE_CONFIG`, and
watch the dashboard's Live view while a sighted helper checks with a tape measure.

| # | Scene | Expected | Result | Notes |
|---|---|---|---|---|
| E1 | Blank wall 2 m ahead | "Stop", no clear path | Not run | |
| E2 | Two obstacles 3 m ahead with a 1 m gap | Opening reported, width within 20 % of the tape | Not run | |
| E3 | Same gap with shoulder width set to Broad | Result changes as expected | Not run | |
| E4 | Clear path | "Walk forward" | Not run | |

## Known platform limitations to confirm, not fix

- With the screen off, the browser stops the camera: WalkSafe keeps the screen on instead.
- No thermal warning: browsers do not report temperature.
- No vibration on iOS.
- Battery level is not reported on iOS Safari or Firefox.
- Free Colab may end the session or give no GPU; the page then drops to L2.
- Before the page has loaded once, there is no offline mode.
