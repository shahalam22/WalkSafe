"""Runs one camera frame through the pipeline. Frames are handled one at a time."""
import threading

import cv2
import numpy as np

import models
import state
from audio import speaker
from config import CFG
from pipeline import depth, detection, flow, fusion, gaps
from pipeline import suggestion as sug

_track_history = {}


class _DepthWorker:
    """Keeps the newest depth map, computed in its own thread so a slow depth
    model (DepthPro takes seconds per frame on a T4) never holds up a frame.
    Frames use the newest map available; only the first frame of a session, or
    the first after the phone turns, waits for one."""

    def __init__(self):
        self._cv      = threading.Condition()
        self._pending = None      # newest frame waiting for depth
        self._latest  = None      # (depth_arr, (H, W))
        self._gen     = 0         # bumped by reset() so a stale result is dropped
        self._thread  = None

    def submit(self, frame_bgr):
        with self._cv:
            self._pending = frame_bgr
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
            self._cv.notify_all()

    def latest(self, shape, wait=False, timeout=60.0):
        def ready():
            return self._latest is not None and self._latest[1] == shape
        with self._cv:
            if wait:
                self._cv.wait_for(ready, timeout=timeout)
            return self._latest[0] if ready() else None

    def reset(self):
        with self._cv:
            self._gen    += 1
            self._pending = None
            self._latest  = None

    def _run(self):
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._pending is not None)
                frame, self._pending = self._pending, None
                gen = self._gen
            H, W = frame.shape[:2]
            try:
                arr = depth.estimate(frame, H, W)
            except Exception as e:
                print(f"⚠️  Depth error: {e}")
                arr = None
            with self._cv:
                if arr is not None and gen == self._gen:
                    self._latest = (arr, (H, W))
                self._cv.notify_all()


_depth = _DepthWorker()


def _resize(frame, width):
    h, w  = frame.shape[:2]
    new_w = (width // 14) * 14
    new_h = int(h * new_w / w)
    new_h = (new_h // 14) * 14
    return cv2.resize(frame, (new_w, new_h))


def _depth_for(s, frame_bgr, fi, H, W):
    if CFG["depth_in_background"]:
        _depth.submit(frame_bgr)
        arr = _depth.latest((H, W))
        if arr is None:                      # first frame, or the phone turned
            arr = _depth.latest((H, W), wait=True)
        return arr if arr is not None else depth.estimate(frame_bgr, H, W)

    stale = s["depth_arr"] is None or s["depth_arr"].shape != (H, W)
    if stale or fi % CFG["depth_every_n_frames"] == 0:
        return depth.estimate(frame_bgr, H, W)
    return s["depth_arr"]


def process(frame_bgr, want_view=False):
    """frame_bgr: the phone's camera frame. Returns the command and everything
    behind it; `view` is the annotated panel as JPEG bytes when want_view."""
    s = state.get()
    with state.lock():
        frame_bgr = _resize(frame_bgr, CFG["resize_width"])
        H, W      = frame_bgr.shape[:2]

        s["frame_idx"] += 1
        fi = s["frame_idx"]

        # Depth
        s["depth_arr"] = _depth_for(s, frame_bgr, fi, H, W)
        depth_arr      = s["depth_arr"]

        # Detection
        det_frame, dets = detection.run(frame_bgr, depth_arr, fi, _track_history)

        # Flow + ego
        prev        = s["prev_frame"]
        flow_tensor = None
        if prev is not None and prev.shape == frame_bgr.shape:
            flow_tensor  = flow.compute(prev, frame_bgr)
            flow_signals = flow.extract_signals(flow_tensor, depth_arr, H, W)
            ego          = flow.derive_ego(flow_signals, depth_arr,
                                           s["speed_history"], H, W)
            s["speed_history"] = (s["speed_history"] + [ego["ego_speed_ms"]])[-3:]
            s["ego"] = ego
        else:
            ego = s["ego"]

        s["prev_frame"] = frame_bgr.copy()

        # Gaps + suggestion
        gap_list                   = gaps.find(depth_arr, H, W)
        command, detail, reasoning = sug.decide(dets, gap_list)

        # Render only when the phone asked to see it
        view = None
        if want_view:
            flow_bgr = (flow.to_bgr_hue_arrows(flow_tensor, frame_bgr)
                        if flow_tensor is not None else np.zeros_like(frame_bgr))
            panel = fusion.build_panel(
                frame_bgr, depth_arr, flow_bgr, det_frame, gap_list, ego, H, W)
            strip = fusion.build_advisory(dets, gap_list, ego, command, detail, W)
            ok, buf = cv2.imencode(".jpg", np.vstack([panel, strip]),
                                   [cv2.IMWRITE_JPEG_QUALITY, 70])
            view = buf.tobytes() if ok else None

        return {
            "frame_idx": fi,
            "command":   command,
            "phrase":    speaker.command_phrase(command),
            "detail":    detail,
            "reasoning": reasoning,
            "ego":       dict(ego),
            "gaps":      gap_list,
            "agents":    dets,
            "view":      view,
        }


def reset():
    """Forget everything from the previous session: tracks, depth, motion."""
    state.reset(_track_history)
    _depth.reset()
    predictor = getattr(models.yolo_model, "predictor", None)
    for tracker in getattr(predictor, "trackers", None) or []:
        tracker.reset()
