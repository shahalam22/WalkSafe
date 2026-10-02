import numpy as np

from walksafe.interpretation.openings import find


def test_flat_wall_still_reports_an_opening():
    # Characterises defect 3, fixed in Phase 1: the threshold is relative, so a
    # wall 1 m away is "open".
    gaps = find(np.full((378, 518), 1.0, dtype=np.float32))
    assert len(gaps) == 1
    assert gaps[0]["direction"] == "ahead"


def test_far_right_half_is_an_opening_on_the_right():
    depth = np.full((378, 518), 1.0, dtype=np.float32)
    depth[:, 200:] = 6.0
    gaps = find(depth)
    assert [g["direction"] for g in gaps] == ["right"]
    assert gaps[0]["width_px"] == 318
