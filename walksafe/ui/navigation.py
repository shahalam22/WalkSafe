"""Gradio webcam front end from the prototype; replaced by the phone page in walksafe/web."""
import cv2
import gradio as gr
import numpy as np
from PIL import Image

from walksafe import pipeline, storage
from walksafe.perception import Models
from walksafe.session import Session
from walksafe.ui import diagnostic
from walksafe.ui.dashboard import build_dashboard_content

# Gradio 5+ replaced `mirror_webcam` with `webcam_options`. Mirroring must stay
# off either way — a flipped frame would swap step_left / step_right.
if hasattr(gr, "WebcamOptions"):
    _NO_MIRROR = {"webcam_options": gr.WebcamOptions(mirror=False)}
else:
    _NO_MIRROR = {"mirror_webcam": False}


def build_ui(models: Models):
    state = {"session": Session()}

    def process_frame(pil_image):
        if pil_image is None:
            blank = np.zeros((400, 300, 3), dtype=np.uint8)
            cv2.putText(blank, "Waiting for camera...", (20, 200),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
            return Image.fromarray(blank), ""

        s         = state["session"]
        frame_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        r         = pipeline.process(models, s, frame_bgr)
        storage.enqueue(s.frame_idx, r.command, r.detail, r.reasoning, r.ego, r.gaps, r.dets)
        return Image.fromarray(diagnostic.render(r, s.track_history)), r.phrase

    def on_reset():
        storage.new_session()
        state["session"] = Session()
        return None, "State reset. Ready."

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

                > Depth updates every 5 frames. Expect ~1-2 fps on Colab free tier.
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

                cam_input.stream(fn=process_frame, inputs=[cam_input], outputs=[output_img, tts_box])
                reset_btn.click(fn=on_reset, inputs=[], outputs=[output_img, status])
                tts_box.change(
                    fn=None, inputs=[tts_box], outputs=[],
                    js="(t) => { if (!t) return; window.speechSynthesis.cancel(); "
                       "window.speechSynthesis.speak(new SpeechSynthesisUtterance(t)); }"
                )

            with gr.Tab("Dashboard"):
                build_dashboard_content(demo)

    return demo
