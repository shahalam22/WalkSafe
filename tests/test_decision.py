from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from walksafe.config import CFG
from walksafe.decision import CAUTIOUS, COMMANDS, PHRASES, decide, describe
from walksafe.interpretation.agents import RISKS, Agent
from walksafe.interpretation.openings import Opening

PERSON = Agent(tid=1, kind="person", box=(200, 100, 260, 300), dist_m=5.0, dist_sigma=0.02,
               lateral_m=0.0, side="ahead", in_path=True, motion="static", approach_speed_ms=0.0,
               lateral_speed_ms=0.0, ttc_s=None, path_time_s=0.0, risk="low", track_points=5)
AHEAD  = Opening(x1_px=100, x2_px=400, width_m=2.0, dist_m=6.0, offset_m=0.0, direction="ahead", wide_enough=True)


def agent(**kw):
    return replace(PERSON, **kw)


def opening(**kw):
    return replace(AHEAD, **kw)


def command(agents=(), openings=(AHEAD,), confidence=1.0):
    return decide(list(agents), None if openings is None else list(openings), confidence).command


def test_vocabulary_is_the_nine_srs_commands_most_cautious_first():
    assert COMMANDS == ("stop", "yield", "slow_down", "walk_forward_slow", "step_left",
                        "step_right", "turn_left", "turn_right", "walk_forward")
    assert set(PHRASES) == set(COMMANDS)


def test_r1_critical_agent_stops():
    d = decide([agent(risk="critical", ttc_s=0.8, motion="approaching")], [AHEAD])
    assert d.command == "stop" and d.reason.startswith("R1")


def test_r2_no_opening_wide_enough_stops():
    assert command(openings=[]) == "stop"
    d = decide([], [opening(width_m=0.5, wide_enough=False)])
    assert d.command == "stop" and d.reason.startswith("R2") and "need=0.75m" in d.reason


def test_r3_crossing_agent_about_to_enter_the_path_yields():
    d = decide([agent(motion="crossing_right", side="left", in_path=False, path_time_s=1.5)], [AHEAD])
    assert d.command == "yield" and d.reason.startswith("R3")
    assert d.detail == "person crossing from your left, 5 metres"


def test_r4_r5_approaching_agent_by_ttc():
    assert command([agent(motion="approaching", ttc_s=1.5, risk="high", in_path=False)]) == "stop"
    assert command([agent(motion="approaching", ttc_s=3.0, risk="moderate", in_path=False)]) == "yield"


def test_r6_agent_in_the_path_close_by_slows():
    d = decide([agent(dist_m=2.0)], [AHEAD])
    assert d.command == "slow_down" and d.reason.startswith("R6")


def test_r7_opening_ahead():
    assert command() == "walk_forward"
    assert command(openings=[opening(width_m=0.8)]) == "walk_forward_slow"         # tight
    far_approaching = agent(motion="approaching", ttc_s=6.0, in_path=False)
    assert command([far_approaching]) == "walk_forward_slow"


def test_r8_opening_just_beside_steps():
    assert command(openings=[opening(direction="left", offset_m=-0.6)]) == "step_left"
    assert command(openings=[opening(direction="right", offset_m=0.6)]) == "step_right"


def test_r9_opening_far_to_one_side_turns():
    assert command(openings=[opening(direction="left", offset_m=-1.8)]) == "turn_left"
    assert command(openings=[opening(direction="right", offset_m=1.8)]) == "turn_right"


def test_r10_fallback_when_the_path_was_not_measured():
    d = decide([], None)
    assert d.command == "slow_down" and d.reason.startswith("R10")


def test_low_confidence_is_downgraded_to_a_cautious_command():
    d = decide([], [AHEAD], confidence=0.3)
    assert d.command == "walk_forward_slow" and "downgraded" in d.reason
    assert command(openings=[opening(direction="right", offset_m=1.8)], confidence=0.3) == "slow_down"


def test_left_and_right_are_never_swapped():
    for side in ("left", "right"):
        sign = -1 if side == "left" else 1
        assert command(openings=[opening(direction=side, offset_m=sign * 0.5)]) == f"step_{side}"
        assert command(openings=[opening(direction=side, offset_m=sign * 2.0)]) == f"turn_{side}"
    assert describe(agent(side="right", motion="approaching")) == "person approaching on your right, 5 metres"


def test_reason_carries_the_values_behind_the_command():
    d = decide([agent(motion="approaching", ttc_s=1.5, risk="high", dist_m=3.0)], [AHEAD])
    assert "dist=3.0m" in d.reason and "ttc=1.5s" in d.reason


agents_st = st.builds(
    agent,
    dist_m=st.floats(0.3, 8.0), side=st.sampled_from(["left", "ahead", "right"]), in_path=st.booleans(),
    motion=st.sampled_from(["new", "static", "approaching", "receding", "crossing_left", "crossing_right"]),
    ttc_s=st.none() | st.floats(0.1, 99), path_time_s=st.none() | st.floats(0, 10),
    risk=st.sampled_from(RISKS),
)
openings_st = st.none() | st.lists(st.builds(
    opening, width_m=st.floats(0.1, 4.0), offset_m=st.floats(-3, 3), wide_enough=st.booleans(),
    direction=st.sampled_from(["left", "ahead", "right"])), max_size=4)


@given(st.lists(agents_st, max_size=5), openings_st, st.floats(0, 1))
def test_t6_always_exactly_one_valid_command(agents, openings, confidence):
    d = decide(agents, openings, confidence)
    assert d.command in COMMANDS
    if confidence < CFG.decision.confidence_low:
        assert d.command in CAUTIOUS


@given(st.lists(agents_st, max_size=5), openings_st, st.floats(0, 1))
def test_lower_confidence_never_makes_the_command_less_cautious(agents, openings, confidence):
    sure = decide(agents, openings, 1.0).command
    less = decide(agents, openings, confidence).command
    assert COMMANDS.index(less) <= COMMANDS.index(sure)
