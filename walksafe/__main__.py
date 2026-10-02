import logging
import os
import secrets

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr  # noqa: E402

from walksafe import server, storage  # noqa: E402
from walksafe.perception import loader  # noqa: E402
from walksafe.ui.dashboard import build_dashboard  # noqa: E402

log = logging.getLogger("walksafe")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    models = loader.load()
    storage.init()
    app = server.create_app(models)

    password = os.environ.get("WALKSAFE_DASHBOARD_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(9)
        log.info("Dashboard login: walksafe / %s (set WALKSAFE_DASHBOARD_PASSWORD to choose one)", password)
    gr.mount_gradio_app(app, build_dashboard(), path="/dashboard", auth=("walksafe", password))
    server.serve(app)


if __name__ == "__main__":
    main()
