import threading
import numpy as np
import cv2
from PIL import Image
import gradio as gr

import models
import state
from config import CFG
from pipeline import depth, flow, gaps, fusion
from pipeline import detection


def _resize(frame, width):
    h, w  = frame.shape[:2]
    new_w = (width // 14) * 14
    new_h = int(h * new_w / w)
    new_h = (new_h // 14) * 14
    return cv2.resize(frame, (new_w, new_h))


# Per-session track history (resets when user clicks Reset)
_track_history = {}


def process_frame(pil_image):
    if pil_image is None:
        blank = np.zeros((400, 300, 3), dtype=np.uint8)
        cv2.putText(blank, "Waiting for camera...", (20,200),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180,180,180), 1)
        return Image.fromarray(blank)

    s = state.get()
    with state.lock():
        frame_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        frame_bgr = _resize(frame_bgr, CFG["resize_width"])
        H, W      = frame_bgr.shape[:2]

        s["frame_idx"] += 1
        fi = s["frame_idx"]

        # Depth — every N frames
        if s["depth_arr"] is None or fi % CFG["depth_every_n_frames"] == 0:
            s["depth_arr"] = depth.estimate(frame_bgr, H, W)
        depth_arr = s["depth_arr"]

        # Detection
        det_frame, dets = detection.run(frame_bgr, depth_arr, fi, _track_history)

        # Flow + ego
        prev = s["prev_frame"]
        if prev is not None and prev.shape == frame_bgr.shape:
            flow_tensor  = flow.compute(prev, frame_bgr)
            flow_bgr     = flow.to_bgr_hue_arrows(flow_tensor, frame_bgr)
            flow_signals = flow.extract_signals(flow_tensor, depth_arr, H, W)
            ego          = flow.derive_ego(flow_signals, depth_arr, s["speed_history"], H, W)
            s["speed_history"] = (s["speed_history"] + [ego["ego_speed_ms"]])[-3:]
            s["ego"] = ego
        else:
            flow_bgr = np.zeros_like(frame_bgr)
            ego      = s["ego"]

        s["prev_frame"] = frame_bgr.copy()

        # Gaps
        gap_list = gaps.find(depth_arr, H, W)

        # Build output
        panel   = fusion.build_panel(frame_bgr, depth_arr, flow_bgr,
                                     det_frame, gap_list, ego, H, W)
        strip   = fusion.build_advisory(dets, gap_list, ego, depth_arr, W, H)
        output  = np.vstack([panel, strip])

        return Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))


def on_reset():
    state.reset(_track_history)
    return None, "State reset. Ready."


def build_ui():
    with gr.Blocks(title="NavGap", theme=gr.themes.Default()) as demo:
        gr.Markdown("""
        # 🧭 NavGap — Real-Time Navigation Gap Detector
        **How to use:**
        1. Tap **Start** on your phone to activate the camera
        2. Hold your phone in front of you as you walk
        3. The panel shows detected gaps, agents and your current action
        4. The advisory strip below gives text guidance
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

        cam_input.stream(fn=process_frame, inputs=[cam_input], outputs=[output_img])
        reset_btn.click(fn=on_reset, inputs=[], outputs=[output_img, status])

    return demo