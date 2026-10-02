"""T3 detection and tracking on a recorded clip (and T4 on real footage).

Runs the clip through the full pipeline at the clip's own frame times,
sampled at --fps as the phone would send them, and reports each track: how
long it lived, how often it was seen, its motion classes, closest distance,
median approach speed and worst risk. Check these against what the clip shows.
For T4, run the same clip at --fps 1.5, 5 and 15 and compare the speeds.

    python scripts/eval_tracking.py clip.mp4 --fps 2
"""
import argparse
import json
from collections import Counter, defaultdict

import cv2
import numpy as np

from walksafe import pipeline
from walksafe.interpretation.agents import RISKS
from walksafe.perception import loader
from walksafe.session import Session


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip")
    ap.add_argument("--fps", type=float, default=2.0)
    args = ap.parse_args()

    models  = loader.load()
    session = Session(models.detector.new_tracker())
    cap     = cv2.VideoCapture(args.clip)
    tracks  = defaultdict(lambda: {"seen": 0, "first_s": None, "last_s": None, "motion": Counter(),
                                   "min_dist_m": 99.0, "speeds": [], "risk": "low"})
    commands, next_t = Counter(), 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t < next_t:
            continue
        next_t = t + 1 / args.fps
        r = pipeline.process(models, session, frame, t)
        commands[r.decision.command] += 1
        for a in r.agents:
            if a.tid < 0:
                continue
            k = tracks[a.tid]
            k["seen"] += 1
            k["first_s"] = t if k["first_s"] is None else k["first_s"]
            k["last_s"] = t
            k["motion"][a.motion] += 1
            k["min_dist_m"] = min(k["min_dist_m"], a.dist_m)
            if a.approach_speed_ms is not None:
                k["speeds"].append(a.approach_speed_ms)
            k["risk"] = min(k["risk"], a.risk, key=RISKS.index)

    report = {
        "fps": args.fps,
        "commands": dict(commands),
        "tracks": {tid: {
            "frames_seen": k["seen"], "from_s": round(k["first_s"], 1), "to_s": round(k["last_s"], 1),
            "motion": dict(k["motion"]), "closest_m": k["min_dist_m"], "worst_risk": k["risk"],
            "median_approach_ms": round(float(np.median(k["speeds"])), 2) if k["speeds"] else None,
        } for tid, k in sorted(tracks.items())},
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
