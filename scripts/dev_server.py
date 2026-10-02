"""Run the WalkSafe server locally without a GPU or the vision models.

Frames get a made-up command (cycling through a few), so the app pages, sign-in
and session logging can be tried on a laptop. Logs go to Supabase when
SUPABASE_SECRET_KEY is set (environment or .env), otherwise they are printed.

    python scripts/dev_server.py            # API + app page on http://localhost:8000
"""
import itertools
import os
import sys
from pathlib import Path

import cv2
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import _load_dotenv  # noqa: E402
from audio.speaker import command_phrase  # noqa: E402
from config import SERVER  # noqa: E402
from server import api, auth, supa  # noqa: E402
from storage import LogWriter  # noqa: E402

_COMMANDS = itertools.cycle(["walk_forward"] * 4 + ["step_left"] * 2 + ["stop"] + ["walk_forward_slow"] * 2)
_frame = itertools.count(1)


def fake_process(frame_bgr, want_view):
    cmd = next(_COMMANDS)
    view = None
    if want_view:
        img = frame_bgr.copy()
        cv2.putText(img, f"DEV: {cmd}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 212, 255), 2)
        view = cv2.imencode(".jpg", img)[1].tobytes()
    return {
        "frame_idx": next(_frame), "command": cmd, "phrase": command_phrase(cmd),
        "detail": "dev server, no models", "reasoning": "dev",
        "ego": {"action": "walking_forward", "ego_speed_ms": 1.1, "action_confidence": 0.9},
        "gaps": [{"direction": "ahead", "width_m": 1.4, "dist_m": 2.5, "cx_px": 259, "width_px": 140}],
        "agents": [], "view": view,
    }


class PrintDb:
    def insert(self, table, rows, on_conflict=None):
        if rows:
            print(f"[db] insert {table}: {len(rows)} rows")

    def update(self, table, match, values):
        print(f"[db] update {table} {match}: {values}")

    def select(self, table, match, columns="*"):
        return []


def main():
    _load_dotenv()
    url, key = SERVER["supabase_url"], os.environ.get("SUPABASE_SECRET_KEY")
    db = supa.Supabase(url, key) if key else PrintDb()
    writer = LogWriter(supa.Supabase(url, key) if key else PrintDb(), flush_every_s=2).start()
    print("Logging to", "Supabase" if key else "the console (no SUPABASE_SECRET_KEY)")
    app = api.create_app(verifier=auth.Verifier(url), db=db, writer=writer,
                         process=fake_process, reset=lambda: None, web_dir=ROOT / "web")
    uvicorn.run(app, host=os.environ.get("WALKSAFE_HOST", "127.0.0.1"),
                port=int(os.environ.get("WALKSAFE_PORT", 8000)), log_level="warning")


if __name__ == "__main__":
    main()
