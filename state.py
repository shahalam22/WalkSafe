import threading

_lock = threading.Lock()

_data = {
    "prev_frame":    None,
    "depth_arr":     None,
    "speed_history": [],
    "frame_idx":     0,
    "ego": {
        "action":             "standing_still",
        "action_confidence":  0.95,
        "ego_speed_ms":       0.0,
        "lateral_drift":      "straight",
        "speed_trend_ms":     0.0,
        "ego_flow_magnitude": 0.0,
        "flow_centroid_x":    0.5,
        "flow_lateral_ratio": 0.0,
        "flow_rotation_score":0.0,
    },
}


def get():
    return _data


def lock():
    return _lock


def reset(track_history_ref):
    with _lock:
        track_history_ref.clear()
        _data["prev_frame"]     = None
        _data["depth_arr"]      = None
        _data["speed_history"]  = []
        _data["frame_idx"]      = 0
        _data["ego"] = {
            "action":             "standing_still",
            "action_confidence":  0.95,
            "ego_speed_ms":       0.0,
            "lateral_drift":      "straight",
            "speed_trend_ms":     0.0,
            "ego_flow_magnitude": 0.0,
            "flow_centroid_x":    0.5,
            "flow_lateral_ratio": 0.0,
            "flow_rotation_score":0.0,
        }