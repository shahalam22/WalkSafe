import numpy as np

from walksafe.interpretation.ego import derive_ego, extract_signals


def flow(dx, dy, H=378, W=518):
    f = np.zeros((H, W, 2), dtype=np.float32)
    f[..., 0], f[..., 1] = dx, dy
    return f


def ego_for(f, depth=4.0, history=()):
    depth_arr = np.full(f.shape[:2], depth, dtype=np.float32)
    return derive_ego(extract_signals(f), depth_arr, list(history))


def test_no_flow_is_standing_still():
    assert ego_for(flow(0, 0))["action"] == "standing_still"


def test_uniform_sideways_flow_is_not_read_as_a_step():
    # Characterises defect A, fixed in Phase 1: left/right comes from where the
    # flow is concentrated, not which way it points.
    assert ego_for(flow(3, 0))["action"] == "walking_forward"
    assert ego_for(flow(-3, 0))["action"] == "walking_forward"


def test_ego_speed_assumes_30_fps():
    # Characterises defect 1: 1 px/frame at 4 m with a 70 deg FOV -> * 30.
    e = ego_for(flow(0, 1))
    focal = 518 / (2 * np.tan(np.radians(35)))
    assert e["ego_speed_ms"] == round(1 * 4.0 / focal * 30.0, 3)
