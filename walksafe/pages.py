"""Publish the phone page and the server's current address to GitHub Pages (FR-22).

The phone always opens the same Pages address. The page there reads
server.json to find wherever the server is running today, so nobody ever has
to read or type a link, and the page still loads (in phone-only mode) when no
server is running. Set WALKSAFE_PAGES_REPO to "owner/name" and
WALKSAFE_PAGES_TOKEN to a fine-grained token with write access to its contents.
"""
import json
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from walksafe.config import CFG, Config, phone_js

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"


def page_url(repo: str) -> str:
    owner, name = repo.split("/")
    return f"https://{owner}.github.io/" + ("" if name == f"{owner}.github.io" else f"{name}/")


def github_remote(repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def site_files(server_url: str, cfg: Config = CFG) -> dict[str, bytes]:
    files = {str(p.relative_to(WEB_DIR)): p.read_bytes() for p in WEB_DIR.rglob("*") if p.is_file()}
    files["js/config.js"] = phone_js(cfg).encode()
    files["server.json"] = json.dumps({"url": server_url, "published_at": int(time.time())}).encode()
    files[".nojekyll"] = b""            # serve files as they are
    return files


def publish(server_url: str, remote: str, branch: str = "main", cfg: Config = CFG) -> bool:
    """Push the page and server.json; True if anything changed."""
    with tempfile.TemporaryDirectory() as tmp:
        git = _git(tmp, remote)
        git("clone", "--depth", "1", remote, ".")
        for old in Path(tmp).iterdir():         # the branch holds only the page
            if old.name != ".git":
                shutil.rmtree(old) if old.is_dir() else old.unlink()
        for name, data in site_files(server_url, cfg).items():
            path = Path(tmp) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        git("add", "-A")
        if not git("status", "--porcelain").strip():
            return False
        git("-c", "user.name=WalkSafe", "-c", "user.email=walksafe@users.noreply.github.com",
            "commit", "-q", "-m", f"Server at {server_url}")
        git("push", "-q", "origin", f"HEAD:{branch}")
        return True


def _git(cwd: str, secret: str):
    def run(*args: str) -> str:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if done.returncode != 0:
            # The remote URL carries the token; never let it reach the log.
            raise RuntimeError(f"git {args[0]} failed: {done.stderr.replace(secret, '<remote>').strip()}")
        return done.stdout
    return run
