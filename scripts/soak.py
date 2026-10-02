"""T14: a long session through the server, looking for crashes, leaks and slowdowns.

Sends frames to /api/frame one after another, as the phone does, and prints a
line every minute: frames, errors, server_ms p50/p95, resident and GPU
memory, live sessions and dropped log items. In-process by default (real
models, real server code, no network); with --url it goes through the tunnel
and reports latency and errors only.

    PYTHONPATH=. python scripts/soak.py --minutes 120 --video street.mp4
    PYTHONPATH=. python scripts/soak.py --minutes 120 --url https://abc.gradio.live
"""
import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

PROFILE = {"user_id": "soak", "consent_send_images": True, "depth_check_passed": True, "direction_test_passed": True}


def frames(video):
    if not video:
        rng = np.random.default_rng(0)
        while True:
            yield cv2.imencode(".jpg", rng.integers(0, 255, (388, 518, 3), dtype=np.uint8))[1].tobytes()
    cap = cv2.VideoCapture(video)
    while True:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        h, w = frame.shape[:2]
        yield cv2.imencode(".jpg", cv2.resize(frame, (518, int(h * 518 / w))), [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()


def rss_mb():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024)
    return None


def client_for(url):
    if url:
        import httpx
        return httpx.Client(base_url=url, timeout=10), None
    from fastapi.testclient import TestClient

    from walksafe.perception import loader
    from walksafe.server import create_app
    from walksafe.storage import LogWriter
    writer = LogWriter(str(Path(tempfile.mkdtemp()) / "soak.db"))
    return TestClient(create_app(loader.load(), writer)), writer


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=120)
    ap.add_argument("--video")
    ap.add_argument("--url")
    args = ap.parse_args()

    client, writer = client_for(args.url)
    sid = client.post("/api/session", json={"profile": PROFILE}).json()["session_id"]
    start = time.time()
    end, minute_end, window_start = start + args.minutes * 60, start + 60, start
    seq, errors, server_ms, history = 0, 0, [], []
    for jpeg in frames(args.video):
        seq += 1
        try:
            r = client.post("/api/frame", data={"session_id": sid, "seq": seq, "capture_ts": time.time() * 1000},
                            files={"image": ("f.jpg", jpeg, "image/jpeg")})
            if r.status_code == 200:
                server_ms.append(r.json()["server_ms"])
            else:
                errors += 1
        except Exception:
            errors += 1
        if time.time() >= minute_end or time.time() >= end:
            server_ms.sort()
            line = {
                "minute": len(history) + 1, "seconds": round(time.time() - window_start, 1),
                "frames": len(server_ms), "errors": errors,
                "p50_ms": server_ms[len(server_ms) // 2] if server_ms else None,
                "p95_ms": server_ms[int(len(server_ms) * 0.95) - 1] if server_ms else None,
                "rss_mb": None if args.url else rss_mb(),
                "gpu_mb": None if args.url else _gpu_mb(),
                "health": client.get("/healthz").json(),
            }
            print(json.dumps(line), flush=True)
            history.append(line)
            server_ms, errors, minute_end, window_start = [], 0, time.time() + 60, time.time()
        if time.time() >= end:
            break

    client.post("/api/session/end", json={"session_id": sid, "reason": "soak"})
    if writer:
        writer.close()
    p50s = [h["p50_ms"] for h in history if h["p50_ms"]]
    print(json.dumps({
        "minutes": len(history), "total_errors": sum(h["errors"] for h in history),
        "decisions_per_s": round(sum(h["frames"] for h in history) / sum(h["seconds"] for h in history), 2)
                           if history else 0,
        "p50_first_last_ms": [p50s[0], p50s[-1]] if p50s else None,
        "rss_first_last_mb": [history[0]["rss_mb"], history[-1]["rss_mb"]] if history else None,
        "median_p50_ms": statistics.median(p50s) if p50s else None,
    }, indent=2))


def _gpu_mb():
    import torch
    return round(torch.cuda.memory_allocated() / 2**20) if torch.cuda.is_available() else None


if __name__ == "__main__":
    main()
