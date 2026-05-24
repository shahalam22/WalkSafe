import numpy as np
import cv2
from PIL import Image

import state
import storage
from config import CFG
from pipeline import depth, flow, gaps, fusion
from pipeline import detection
from pipeline import suggestion as sug
from audio import speaker

_track_history = {}


def _resize(frame, width):
    h, w  = frame.shape[:2]
    new_w = (width // 14) * 14
    new_h = int(h * new_w / w)
    new_h = (new_h // 14) * 14
    return cv2.resize(frame, (new_w, new_h))


def process_frame(pil_image):
    if pil_image is None:
        blank = np.zeros((400, 300, 3), dtype=np.uint8)
        cv2.putText(blank, "Waiting for camera...", (20, 200),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
        return Image.fromarray(blank), ""

    s = state.get()
    with state.lock():
        frame_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        frame_bgr = _resize(frame_bgr, CFG["resize_width"])
        H, W      = frame_bgr.shape[:2]

        s["frame_idx"] += 1
        fi = s["frame_idx"]

        # Depth
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
            ego          = flow.derive_ego(flow_signals, depth_arr,
                                           s["speed_history"], H, W)
            s["speed_history"] = (s["speed_history"] + [ego["ego_speed_ms"]])[-3:]
            s["ego"] = ego
        else:
            flow_bgr = np.zeros_like(frame_bgr)
            ego      = s["ego"]

        s["prev_frame"] = frame_bgr.copy()

        # Gaps + suggestion
        gap_list                       = gaps.find(depth_arr, H, W)
        command, detail, reasoning     = sug.decide(dets, gap_list)
        phrase                         = speaker.command_phrase(command)

        # Store
        storage.enqueue(fi, command, detail, reasoning, ego, gap_list, dets)

        # Render
        panel = fusion.build_panel(
            frame_bgr, depth_arr, flow_bgr, det_frame, gap_list, ego, H, W)
        strip = fusion.build_advisory(dets, gap_list, ego, command, detail, W)

        output = np.vstack([panel, strip])
        return Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB)), phrase


def on_reset():
    storage.new_session()
    state.reset(_track_history)
    return None, "State reset. Ready."
