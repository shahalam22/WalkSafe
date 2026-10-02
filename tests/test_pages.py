import json
import subprocess

import pytest

from walksafe import pages


@pytest.fixture
def remote(tmp_path):
    bare = tmp_path / "pages.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    return str(bare)


def checkout(remote, tmp_path):
    out = tmp_path / "check"
    subprocess.run(["git", "clone", "-q", remote, str(out)], check=True)
    return out


def test_fixed_page_address():
    assert pages.page_url("shahalam22/walksafe-phone") == "https://shahalam22.github.io/walksafe-phone/"
    assert pages.page_url("shahalam22/shahalam22.github.io") == "https://shahalam22.github.io/"


def test_site_has_the_page_its_config_and_the_server_address():
    files = pages.site_files("https://abc.gradio.live")
    assert {"index.html", "style.css", "js/main.js", "js/config.js", "server.json"} <= set(files)
    assert json.loads(files["server.json"])["url"] == "https://abc.gradio.live"
    assert b"stale_after_ms" in files["js/config.js"]


def test_publish_to_an_empty_repository_then_update_it(remote, tmp_path):
    assert pages.publish("https://one.gradio.live", remote) is True
    site = checkout(remote, tmp_path)
    assert json.loads((site / "server.json").read_text())["url"] == "https://one.gradio.live"
    assert (site / "js" / "guidance.js").exists()
    assert pages.publish("https://two.gradio.live", remote) is True


def test_git_errors_never_show_the_token(tmp_path):
    secret = "https://x-access-token:SECRET@github.invalid/nobody/nothing.git"
    with pytest.raises(RuntimeError) as e:
        pages.publish("https://one.gradio.live", secret)
    assert "SECRET" not in str(e.value)
