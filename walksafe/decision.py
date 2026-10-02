from walksafe.config import CFG, AgentConfig, OpeningConfig

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


def phrase(command):
    return PHRASES.get(command, command.replace("_", " "))


def decide(dets, gap_list, agents: AgentConfig = CFG.agents, openings: OpeningConfig = CFG.openings):
    """Returns (command, detail, reasoning)."""
    RISK_ORDER  = {"critical":0, "high":1, "moderate":2, "low":3}
    top_agents  = sorted(dets,
                         key=lambda d: (RISK_ORDER.get(d["risk_level"], 3), d["dist_m"]))
    critical    = [a for a in top_agents if a["risk_level"] == "critical"]
    approaching = [a for a in top_agents
                   if a["motion"] in ("approaching", "parallel_counter", "erratic")]
    crossing    = [a for a in top_agents if "crossing" in a["motion"]]
    best_gap    = max(gap_list, key=lambda g: g["width_px"]) if gap_list else None

    # Rule 1: critical agent
    if critical:
        a   = critical[0]
        ttc = f" TTC {a['ttc_s']:.1f}s" if a.get("ttc_s") and a["ttc_s"] < 10 else ""
        return (
            "stop",
            f"{a['name']} {a['motion'].replace('-',' ')} at {a['dist_m']:.1f}m{ttc}",
            f"critical:{a['name']}:{a['motion']}:{a['dist_m']}m"
        )

    # Rule 2: no gap
    if not gap_list:
        return (
            "stop",
            "no clear corridor ahead",
            "no_gap"
        )

    # Rule 3: crossing agent with short TTC
    if crossing:
        a   = crossing[0]
        ttc = a.get("ttc_s")
        if ttc and ttc < 3.0:
            return (
                "yield",
                f"{a['name']} crossing in {ttc:.1f}s",
                f"crossing:{a['name']}:{ttc:.1f}s"
            )

    # Rule 4: approaching agent
    if approaching:
        a   = approaching[0]
        ttc = a.get("ttc_s")
        if ttc and ttc < agents.ttc_critical:
            return (
                "stop",
                f"{a['name']} approaching {a['dist_m']:.1f}m TTC {ttc:.1f}s",
                f"approaching_critical:{a['name']}:{a['dist_m']}m"
            )
        if ttc and ttc < agents.ttc_urgent:
            return (
                "yield",
                f"{a['name']} approaching {a['dist_m']:.1f}m",
                f"approaching_urgent:{a['name']}:{a['dist_m']}m"
            )
        if a["dist_m"] < agents.close_distance_m:
            return (
                "slow_down",
                f"{a['name']} ahead {a['dist_m']:.1f}m",
                f"approaching_close:{a['name']}:{a['dist_m']}m"
            )

    # Rule 5: route toward the best gap
    dir_    = best_gap["direction"]
    width_m = best_gap["width_m"]
    dist_m  = best_gap["dist_m"]
    detail  = f"{width_m:.1f}m gap {dist_m:.1f}m away"

    if width_m < openings.tight_m:
        cmd_map = {"ahead": "walk_forward_slow", "right": "step_right", "left": "step_left"}
        cmd     = cmd_map.get(dir_, "slow_down")
        return (
            cmd,
            f"tight corridor {dir_} — {detail}",
            f"tight_gap_{dir_}:{width_m}m:{dist_m}m"
        )

    if dir_ == "ahead":
        cmd = "walk_forward" if not approaching else "walk_forward_slow"
        return (
            cmd,
            detail + (" — agent nearby" if approaching else ""),
            f"gap_ahead:{width_m}m:{dist_m}m"
        )

    if dir_ == "right":
        return (
            "step_right",
            detail,
            f"gap_right:{width_m}m:{dist_m}m"
        )

    if dir_ == "left":
        return (
            "step_left",
            detail,
            f"gap_left:{width_m}m:{dist_m}m"
        )

    # Fallback
    return (
        "slow_down",
        "assess surroundings",
        "fallback"
    )
