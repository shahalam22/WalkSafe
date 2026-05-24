import models
from ui import build_ui

if __name__ == "__main__":
    models.load_all()
    demo = build_ui()
    demo.launch(share=True, debug=False, quiet=True)