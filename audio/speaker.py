import threading
import queue
import time

# We use pyttsx3 for offline TTS — no internet needed, works on Colab via espeak
# Install: pip install pyttsx3 && apt-get install -y espeak

_tts_engine  = None
_tts_queue   = queue.Queue()
_tts_thread  = None
_last_spoken = ""
_last_time   = 0
MIN_INTERVAL = 2.5   # seconds — don't repeat same command within this window


def init():
    """Call once at startup."""
    global _tts_engine, _tts_thread
    try:
        import pyttsx3
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate", 160)    # words per minute
        _tts_engine.setProperty("volume", 1.0)
        _tts_thread = threading.Thread(target=_worker, daemon=True)
        _tts_thread.start()
        print("✅ Speaker ready")
    except Exception as e:
        print(f"⚠️  Speaker init failed: {e}. Audio disabled.")
        _tts_engine = None


def speak(command, detail):
    """
    Non-blocking. Puts the message on the queue.
    Skips if same command was spoken within MIN_INTERVAL seconds.

    command — e.g. "step_right"
    detail  — e.g. "1.4m gap at 2.1m"
    """
    if _tts_engine is None:
        return

    global _last_spoken, _last_time
    now = time.time()

    text = _build_text(command, detail)

    # Debounce — only speak if command changed or enough time passed
    if text == _last_spoken and (now - _last_time) < MIN_INTERVAL:
        return

    _last_spoken = text
    _last_time   = now

    # Clear stale items so latest command always wins
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break

    _tts_queue.put(text)


def _build_text(command, detail):
    """Convert command + detail into a natural spoken sentence."""
    PHRASES = {
        "stop":              "Stop.",
        "yield":             "Yield. Wait.",
        "slow_down":         "Slow down.",
        "walk_forward":      "Walk forward.",
        "walk_forward_slow": "Walk forward slowly.",
        "step_left":         "Step left.",
        "step_right":        "Step right.",
        "turn_left":         "Turn left.",
        "turn_right":        "Turn right.",
    }
    base = PHRASES.get(command, command.replace("_", " "))

    # Append simplified detail if meaningful
    if detail and detail not in ("assess surroundings", "no clear corridor ahead"):
        # Strip technical notation, keep human-readable parts
        readable = detail.replace("m away", " metres away") \
                         .replace("m wide", " metres wide") \
                         .replace("m gap", " metre gap") \
                         .replace("m TTC", " metres,") \
                         .replace("_", " ")
        return f"{base} {readable}"
    return base


def _worker():
    """Background thread — speaks queued messages one at a time."""
    while True:
        try:
            text = _tts_queue.get(timeout=1)
            if _tts_engine:
                _tts_engine.say(text)
                _tts_engine.runAndWait()
        except queue.Empty:
            continue
        except Exception:
            continue