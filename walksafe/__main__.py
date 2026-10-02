import logging
import os
import secrets

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr  # noqa: E402

from walksafe import server  # noqa: E402
from walksafe.config import CFG  # noqa: E402
from walksafe.perception import loader  # noqa: E402
from walksafe.storage import LogWriter  # noqa: E402
from walksafe.ui.dashboard import build_dashboard  # noqa: E402

log = logging.getLogger("walksafe")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    models = loader.load()
    writer = LogWriter(CFG.storage.db_path)
    app = server.create_app(models, writer)

    password = os.environ.get("WALKSAFE_DASHBOARD_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(9)
        log.info("Dashboard login: walksafe / %s (set WALKSAFE_DASHBOARD_PASSWORD to choose one)", password)
    dashboard = build_dashboard(CFG.storage.db_path, app.state.sessions)
    gr.mount_gradio_app(app, dashboard, path="/dashboard", auth=("walksafe", password))
    server.add_phone_page(app)
    server.serve(app)


if __name__ == "__main__":
    main()
