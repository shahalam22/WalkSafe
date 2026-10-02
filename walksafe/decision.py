"""The nine commands and the rules that pick one per cycle (FR-9 to FR-11).

Rules are tried in order, hazards before route choice. The first that matches
gives the command; the reason string names the rule and the values behind it.
"""
from dataclasses import dataclass

from walksafe.config import CFG, Config, Profile
from walksafe.interpretation.agents import RISKS, Agent
from walksafe.interpretation.openings import Opening, best_opening

# SRS §2.4, most cautious first.
COMMANDS = (
    "stop",
    "yield",
    "slow_down",
    "walk_forward_slow",
    "step_left",
    "step_right",
    "turn_left",
    "turn_right",
    "walk_forward",
)
CAUTIOUS = COMMANDS[:4]

PHRASES = {
    "stop":              "Stop",
    "yield":             "Yield. Wait",
    "slow_down":         "Slow down",
    "walk_forward":      "Walk forward",
    "walk_forward_slow": "Walk forward slowly",
    "step_left":         "Step left",
    "step_right":        "Step right",
    "turn_left":         "Turn left",
    "turn_right":        "Turn right",
}


@dataclass(frozen=True)
class Decision:
    command:    str
    detail:     str
    reason:     str
    confidence: float


def phrase(command: str) -> str:
    return PHRASES[command]


def decide(agents: list[Agent], openings: list[Opening] | None, confidence: float = 1.0,
           profile: Profile = CFG.profile, cfg: Config = CFG) -> Decision:
    """openings is None when the path could not be measured at all."""
    command, detail, reason = _first_matching_rule(agents, openings, profile, cfg)
    if confidence < cfg.decision.confidence_low and command not in CAUTIOUS:
        command = "walk_forward_slow" if command == "walk_forward" else "slow_down"
        reason += f" | low confidence {confidence:.2f}, downgraded"
    return Decision(command, detail, reason, round(confidence, 2))


def _first_matching_rule(agents, openings, profile, cfg):
    ac, dc = cfg.agents, cfg.decision
    need   = profile.needed_width_m
    agents = sorted(agents, key=lambda a: (RISKS.index(a.risk), a.dist_m))
    best   = best_opening(openings)

    for a in agents:
        if a.risk == "critical":
            return "stop", describe(a), f"R1 critical_agent {_values(a)}"

    if openings is not None and best is None:
        widest = max((o.width_m for o in openings), default=0.0)
        return "stop", "no clear path ahead", f"R2 no_safe_opening widest={widest:.2f}m need={need:.2f}m"

    for a in agents:
        if a.motion.startswith("crossing") and a.path_time_s is not None and a.path_time_s < dc.crossing_ttc_s:
            return "yield", describe(a), f"R3 crossing_agent {_values(a)} path_time={a.path_time_s}s"

    approaching = [a for a in agents if a.motion == "approaching" and a.ttc_s is not None]
    if approaching and approaching[0].ttc_s < ac.ttc_high_s:
        a = approaching[0]
        return "stop", describe(a), f"R4 approaching_agent {_values(a)}"
    if approaching and approaching[0].ttc_s < ac.ttc_moderate_s:
        a = approaching[0]
        return "yield", describe(a), f"R5 approaching_agent {_values(a)}"

    close = [a for a in agents if a.in_path and a.dist_m < ac.close_distance_m]
    if close:
        a = close[0]
        return "slow_down", describe(a), f"R6 agent_in_path {_values(a)}"

    if best is not None:
        values = f"width={best.width_m:.2f}m need={need:.2f}m dist={best.dist_m:.1f}m offset={best.offset_m:+.2f}m"
        if best.direction == "ahead":
            tight = best.width_m < need + cfg.openings.tight_extra_m
            if tight or approaching:
                return "walk_forward_slow", "narrow path ahead" if tight else describe(approaching[0]), \
                       f"R7 opening_ahead_with_care {values}"
            return "walk_forward", "path clear", f"R7 opening_ahead {values}"
        if abs(best.offset_m) <= dc.step_max_offset_m:
            return f"step_{best.direction}", f"opening on your {best.direction}", f"R8 opening_beside {values}"
        return f"turn_{best.direction}", f"opening to your {best.direction}", f"R9 opening_far_side {values}"

    return "slow_down", "path not measured", "R10 fallback openings_unknown"


def describe(a: Agent) -> str:
    """Spoken detail, e.g. "cyclist crossing from your left, 4 metres"."""
    motion = {
        "approaching":    " approaching",
        "receding":       " moving away",
        "crossing_right": " crossing from your left",
        "crossing_left":  " crossing from your right",
    }.get(a.motion, "")
    where = "" if a.motion.startswith("crossing") else \
            (" ahead" if a.side == "ahead" else f" on your {a.side}")
    return f"{a.kind}{motion}{where}, {round(a.dist_m, 1):g} metres"


def _values(a: Agent) -> str:
    return (f"{a.kind}#{a.tid} motion={a.motion} side={a.side} dist={a.dist_m}m "
            f"approach={a.approach_speed_ms}m/s ttc={a.ttc_s}s risk={a.risk}")
