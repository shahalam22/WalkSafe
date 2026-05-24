import gradio as gr
from .processor import process_frame, on_reset
from .dashboard import build_dashboard_content


def build_ui():
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
                            mirror_webcam=False,
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
                    js="(t) => { if (!t) return; window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(t)); }"
                )

            with gr.Tab("Dashboard"):
                build_dashboard_content(demo)

    return demo
