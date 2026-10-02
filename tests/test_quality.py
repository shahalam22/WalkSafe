from dataclasses import replace

import numpy as np
from test_decision import PERSON

from walksafe.config import CFG
from walksafe.interpretation.quality import check_frame, confidence


def textured(level=128, spread=60, seed=0):
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(level, spread, (378, 518, 3)), 0, 255).astype(np.uint8)


def test_textured_frame_is_usable():
    q = check_frame(textured())
    assert q.ok and q.cause == ""


def test_dark_bright_and_blurred_frames_are_rejected():
    assert check_frame(textured(level=15, spread=5)).cause == "dark"
    assert check_frame(textured(level=245, spread=5)).cause == "bright"
    assert check_frame(np.full((378, 518, 3), 128, np.uint8)).cause == "blur"


def test_confidence_is_full_with_nothing_doubtful():
    assert confidence([]) == (1.0, "")
    assert confidence([PERSON]) == (1.0, "")


def test_unsteady_depth_and_new_close_tracks_lower_confidence():
    score, why = confidence([replace(PERSON, dist_sigma=0.5)])
    assert score == CFG.quality.poor_depth_score and "depth" in why
    score, why = confidence([replace(PERSON, motion="new", dist_m=2.0)])
    assert score == CFG.quality.new_track_score and "not yet tracked" in why
    assert confidence([replace(PERSON, motion="new", dist_m=7.0)])[0] == 1.0
