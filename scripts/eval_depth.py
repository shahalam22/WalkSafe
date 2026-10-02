"""T2 depth accuracy: DepthPro against known distances.

Photograph obstacles straight ahead, centred, at measured distances, and put
the distance in the file name: wall_2.0m.jpg, person_3.5m.jpg, glass_1.5m.jpg.
Include glass and a blank wall; their spread should come out higher.

    PYTHONPATH=. python scripts/eval_depth.py photos/ [--band 0.15] [--fp16]
"""
import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np

from walksafe import pipeline
from walksafe.config import CFG
from walksafe.perception.depth import DepthPro
from walksafe.server import check_depth


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--band", type=float, default=0.15, help="acceptable relative error")
    ap.add_argument("--fp16", action="store_true")
    args = ap.parse_args()

    model = DepthPro(CFG.models.depth_model_id, "cuda", args.fp16)
    rows = []
    for path in sorted(Path(args.folder).iterdir()):
        known = re.search(r"_(\d+(?:\.\d+)?)m\b", path.stem)
        image = cv2.imread(str(path))
        if not known or image is None:
            continue
        frame  = pipeline.resize(image, CFG.models.resize_width)
        depth  = model.estimate(frame)
        result = check_depth(depth, float(known.group(1)), model.last_fov_deg)
        H, W   = depth.shape
        centre = depth[H // 2 - H // 10:H // 2 + H // 10, W // 2 - W // 10:W // 2 + W // 10]
        rows.append({
            "file": path.name, "known_m": float(known.group(1)), "measured_m": result["measured_m"],
            "error": result["error_frac"], "within_band": result["error_frac"] <= args.band,
            "spread": round(float(np.std(centre) / np.median(centre)), 3), "fov_deg": result["fov_deg"],
        })

    for r in rows:
        print(f"{r['file']:32} known {r['known_m']:4.1f} m  measured {r['measured_m']:5.2f} m  "
              f"error {100 * r['error']:5.1f} %  spread {r['spread']:.3f}  {'ok' if r['within_band'] else 'OUT'}")
    print(json.dumps({
        "images": len(rows),
        "mean_error": round(float(np.mean([r["error"] for r in rows])), 3) if rows else None,
        "within_band": sum(r["within_band"] for r in rows), "band": args.band,
    }, indent=2))


if __name__ == "__main__":
    main()
