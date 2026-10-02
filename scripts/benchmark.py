"""Server throughput on the real models (NFR-4: at least 2 decisions per second on a T4).

Frames go straight into the pipeline, one after another, each stamped with the
time it was taken, so the 0.4 s depth age cap behaves as it would live. JPEG
decoding and the network are not included; server_ms in /api/frame covers those.

    PYTHONPATH=. python scripts/benchmark.py
    PYTHONPATH=. python scripts/benchmark.py --fp16 --flow-scale 0.5
    PYTHONPATH=. python scripts/benchmark.py --video street.mp4 --frames 120
"""
import argparse
import json
import statistics
import time
from dataclasses import replace

import cv2
import numpy as np

from walksafe import pipeline
from walksafe.config import CFG
from walksafe.perception import loader
from walksafe.session import Session


def frames(video: str | None, n: int):
    if not video:
        # Noise has no agents in it, so detection and the rules run lighter than on a street.
        rng = np.random.default_rng(0)
        for _ in range(n):
            yield rng.integers(0, 255, (720, 960, 3), dtype=np.uint8)
        return
    cap, sent = cv2.VideoCapture(video), 0
    while sent < n:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        sent += 1
        yield frame


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--fp16", action="store_true", help="run DepthPro in half precision")
    ap.add_argument("--flow-scale", type=float, default=CFG.models.flow_scale, help="RAFT input scale")
    ap.add_argument("--depth-max-age", type=float, default=CFG.models.depth_max_age_s)
    args = ap.parse_args()

    models_cfg = replace(CFG.models, depth_fp16=args.fp16, flow_scale=args.flow_scale,
                         depth_max_age_s=args.depth_max_age)
    cfg     = replace(CFG, models=models_cfg)
    models  = loader.load(models_cfg)
    session = Session(models.detector.new_tracker(), cfg.profile)

    totals, stages = [], {}
    for i, frame in enumerate(frames(args.video, args.warmup + args.frames)):
        t0 = time.perf_counter()
        r  = pipeline.process(models, session, frame, t0, cfg)
        if i < args.warmup:
            continue
        totals.append((time.perf_counter() - t0) * 1000)
        for name, ms in r.timings.items():
            stages.setdefault(name, []).append(ms)

    totals.sort()
    report = {
        "options": {"fp16": args.fp16, "flow_scale": args.flow_scale, "depth_max_age_s": args.depth_max_age,
                    "source": args.video or "noise", "frames": args.frames},
        "decisions_per_s": round(1000 / statistics.mean(totals), 2),
        "ms_mean": round(statistics.mean(totals), 1),
        "ms_p50":  round(totals[len(totals) // 2], 1),
        "ms_p95":  round(totals[int(len(totals) * 0.95) - 1], 1),
        "stage_ms_mean": {k: round(statistics.mean(v), 1) for k, v in stages.items()},
        "nfr4_met": 1000 / statistics.mean(totals) >= 2.0,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
