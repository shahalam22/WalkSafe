"""Start the WalkSafe server: load the models, serve the API, open a tunnel.

Needs SUPABASE_SECRET_KEY in the environment (Colab Secrets on Colab) or in a
.env file next to this one.
"""
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

from config import SERVER

ROOT = Path(__file__).parent


def _load_dotenv():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _wait_reachable(url, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(2)
    return False


def main():
    _load_dotenv()
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not key:
        sys.exit("SUPABASE_SECRET_KEY is not set. On Colab add it under Secrets (🔑); "
                 "locally put it in .env.")

    import uvicorn

    import models
    from pipeline import processor
    from server import api, auth, supa, tunnel
    from storage import LogWriter

    url = SERVER["supabase_url"]
    models.load_all()
    writer = LogWriter(supa.Supabase(url, key)).start()
    app = api.create_app(
        verifier=auth.Verifier(url),
        db=supa.Supabase(url, key),
        writer=writer,
        process=processor.process,
        reset=processor.reset,
        is_ready=models.is_ready,
        web_dir=ROOT / "web",
    )

    port   = int(os.environ.get("WALKSAFE_PORT", SERVER["port"]))
    server = uvicorn.Server(uvicorn.Config(app, host=os.environ.get("WALKSAFE_HOST", "127.0.0.1"),
                                           port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.1)

    public = tunnel.open_tunnel(port, os.environ.get("WALKSAFE_TUNNEL", SERVER["tunnel"]))
    reachable = _wait_reachable(public)
    print("\n" + "═" * 64)
    print(f"  WalkSafe server address:  {public}")
    print("  Paste it in the app: Admin → Server → Save.")
    if not reachable:
        print("  (Not reachable yet; the tunnel can take a minute.)")
    print("═" * 64 + "\n", flush=True)

    try:
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        writer.stop()


if __name__ == "__main__":
    main()
