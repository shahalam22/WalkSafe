"""A public HTTPS address for the server running on Colab.

cloudflared's quick tunnel needs no account and adds little delay. Gradio's
share tunnel is the fallback. The address changes every run; the admin pastes
it into the app (Admin → Server).
"""
import os
import queue
import re
import secrets
import shutil
import stat
import subprocess
import threading
import urllib.request
from pathlib import Path

CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
_URL = re.compile(r"https://(?!api\.)[-a-z0-9]+\.trycloudflare\.com")


def open_tunnel(port, kind="cloudflared"):
    if kind == "none":
        return f"http://localhost:{port}"
    if kind == "cloudflared":
        try:
            return _cloudflared(port)
        except Exception as e:
            print(f"⚠️  cloudflared tunnel failed ({e}); trying Gradio's tunnel")
    return _gradio(port)


def _cloudflared_exe():
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    path = Path.home() / ".cache" / "walksafe" / "cloudflared"
    if not path.exists():
        print("Downloading cloudflared...")
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(CLOUDFLARED, path)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def _cloudflared(port, timeout=90):
    proc = subprocess.Popen(
        [_cloudflared_exe(), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    found = queue.Queue()

    def pump():                       # keep reading so the pipe never fills up
        for line in proc.stderr:
            m = _URL.search(line)
            if m:
                found.put(m.group(0))

    threading.Thread(target=pump, daemon=True).start()
    try:
        return found.get(timeout=timeout)
    except queue.Empty:
        proc.kill()
        raise RuntimeError(f"no address after {timeout} s") from None


def _gradio(port):
    from gradio.networking import setup_tunnel
    os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
    return setup_tunnel("127.0.0.1", port, secrets.token_urlsafe(32), None, None)
