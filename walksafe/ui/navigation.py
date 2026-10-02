"""Gradio webcam front end from the prototype; replaced by the phone page in walksafe/web."""
import logging
import time

import cv2
import gradio as gr
import numpy as np
from PIL import Image

from walksafe import pipeline, storage
from walksafe.perception import Models
from walksafe.session import Session
from walksafe.ui import diagnostic
from walksafe.ui.dashboard import build_dashboard_content

log = logging.getLogger(__name__)

# Gradio 5+ replaced `mirror_webcam` with `webcam_options`. Mirroring must stay
# off either way — a flipped frame would swap step_left / step_right.
if hasattr(gr, "WebcamOptions"):
    _NO_MIRROR = {"webcam_options": gr.WebcamOptions(mirror=False)}
else:
    _NO_MIRROR = {"mirror_webcam": False}


FAULT_PHRASE = "Guidance stopped. System error."


def build_ui(models: Models):

    def process_frame(pil_image, session):
        if pil_image is None:
            blank = np.zeros((400, 300, 3), dtype=np.uint8)
            cv2.putText(blank, "Waiting for camera...", (20, 200),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
            return Image.fromarray(blank), "", session

        # The webcam stream carries no capture time, so arrival time stands in
        # until the phone page sends its own (Phase 2).
        capture_ts = time.time()
        try:
            session = session or Session(models.detector.new_tracker())
            frame   = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            r       = pipeline.process(models, session, frame, capture_ts)
            storage.enqueue(session.frame_idx, r)
            return Image.fromarray(diagnostic.render(r)), r.phrase, session
        except Exception:
            log.exception("Frame pipeline failed")
            return None, FAULT_PHRASE, session

    def on_reset():
        storage.new_session()
        return None, "State reset. Ready.", None

    with gr.Blocks(title="WalkSafe", theme=gr.themes.Default()) as demo:
        with gr.Tabs():

            with gr.Tab("Navigation"):
                gr.Markdown("""
                # 🧭 WalkSafe — Real-Time Navigation Assistant
                **How to use:**
                1. Tap **Start** on your phone to activate the camera
                2. Hold your phone in front of you as you walk
                3. The panel shows detected gaps, agents and your current action
                4. The advisory strip gives text guidance
                5. Audio instructions will play through your speaker

                > Depth is never more than 0.4 s old. Expect ~1-2 fps on Colab free tier.
                """)

                with gr.Row():
                    with gr.Column(scale=1):
                        cam_input = gr.Image(
                            sources=["webcam"],
                            streaming=True,
                            label="📷 Phone Camera",
                            **_NO_MIRROR,
                        )
                        reset_btn = gr.Button("🔄 Reset Tracker", variant="secondary")
                        status    = gr.Textbox(label="Status", value="Ready.",
                                               interactive=False)

                    with gr.Column(scale=1):
                        output_img = gr.Image(
                            label="🗺️ Fusion Panel + Advisory",
                            interactive=False,
                        )

                tts_box = gr.Textbox(visible=False, elem_id="tts_box")

                session = gr.State(None)
                cam_input.stream(fn=process_frame, inputs=[cam_input, session],
                                 outputs=[output_img, tts_box, session])
                reset_btn.click(fn=on_reset, inputs=[], outputs=[output_img, status, session])
                tts_box.change(
                    fn=None, inputs=[tts_box], outputs=[],
                    js="(t) => { if (!t) return; window.speechSynthesis.cancel(); "
                       "window.speechSynthesis.speak(new SpeechSynthesisUtterance(t)); }"
                )

            with gr.Tab("Dashboard"):
                build_dashboard_content(demo)

    return demo
