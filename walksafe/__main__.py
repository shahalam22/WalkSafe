import logging

from walksafe import storage
from walksafe.perception import loader
from walksafe.ui.navigation import build_ui


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    models = loader.load()
    storage.init()
    build_ui(models).launch(share=True, debug=False, quiet=True)


if __name__ == "__main__":
    main()
