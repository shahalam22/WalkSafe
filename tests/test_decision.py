from walksafe.decision import COMMANDS, decide, phrase


def agent(motion="static", dist=5.0, ttc=None, risk="low", name="person"):
    return {"name": name, "motion": motion, "dist_m": dist, "ttc_s": ttc, "risk_level": risk}


def gap(direction="ahead", width_m=1.5, width_px=150, dist=4.0):
    return {"direction": direction, "width_m": width_m, "width_px": width_px, "dist_m": dist, "cx_px": 259}


def test_vocabulary_is_the_nine_srs_commands_most_cautious_first():
    assert COMMANDS == ("stop", "yield", "slow_down", "walk_forward_slow", "step_left",
                        "step_right", "turn_left", "turn_right", "walk_forward")


def test_critical_agent_stops():
    assert decide([agent(risk="critical", ttc=0.5)], [gap()])[0] == "stop"


def test_no_gap_stops():
    assert decide([], []) == ("stop", "no clear corridor ahead", "no_gap")


def test_crossing_agent_with_short_ttc_yields():
    assert decide([agent("crossing-L", ttc=2.5, risk="high")], [gap()])[0] == "yield"


def test_approaching_agent_by_ttc_and_distance():
    assert decide([agent("approaching", ttc=1.5, risk="high")], [gap()])[0] == "stop"
    assert decide([agent("approaching", ttc=3.0, risk="moderate")], [gap()])[0] == "yield"
    assert decide([agent("approaching", dist=2.0)], [gap()])[0] == "slow_down"


def test_routes_toward_the_best_gap():
    assert decide([], [gap("ahead")])[0] == "walk_forward"
    assert decide([], [gap("left")])[0] == "step_left"
    assert decide([], [gap("right")])[0] == "step_right"
    assert decide([], [gap("ahead", width_m=0.5)])[0] == "walk_forward_slow"
    assert decide([agent("approaching", dist=5.0)], [gap("ahead")])[0] == "walk_forward_slow"


def test_best_gap_is_chosen_by_pixels_not_metres():
    # Characterises defect 6, fixed in Phase 1.
    wide_px_narrow_m = gap("left", width_m=0.8, width_px=200)
    narrow_px_wide_m = gap("right", width_m=2.0, width_px=100)
    assert decide([], [wide_px_narrow_m, narrow_px_wide_m])[0] == "step_left"


def test_turn_commands_never_fire():
    # Characterises defect 7, fixed in Phase 1.
    outputs = {decide([], [gap(d, w)])[0] for d in ("left", "ahead", "right") for w in (0.4, 1.0, 3.0)}
    assert not outputs & {"turn_left", "turn_right"}


def test_phrase():
    assert phrase("yield") == "Yield. Wait"
    assert phrase("step_left") == "Step left"
