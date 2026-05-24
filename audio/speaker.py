_PHRASES = {
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


def init():
    print("✅ Speaker ready (browser Web Speech API)")


def speak(command, detail):
    pass  # audio is handled client-side in the browser


def command_phrase(command):
    return _PHRASES.get(command, command.replace("_", " "))
