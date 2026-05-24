import threading
import queue
import time


_audio_enabled = False
_tts_queue     = queue.Queue()
_tts_thread    = None
_last_spoken   = ""
_last_time     = 0
MIN_INTERVAL   = 2.5   # seconds — don't repeat same command within this window


def init():
    """Call once at startup from models.py."""
    global _audio_enabled, _tts_thread
    try:
        import pyttsx3  # just verify it's importable
        _audio_enabled = True
        _tts_thread = threading.Thread(target=_worker, daemon=True)
        _tts_thread.start()
        print("✅ Speaker ready")
    except Exception as e:
        print(f"⚠️  Speaker init failed: {e}. Audio disabled.")


def speak(command, detail):
    """Non-blocking. Queues only the command phrase. detail is ignored."""
    if not _audio_enabled:
        return

    global _last_spoken, _last_time
    now  = time.time()
    text = _build_text(command)

    if text == _last_spoken and (now - _last_time) < MIN_INTERVAL:
        return

    _last_spoken = text
    _last_time   = now

    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break

    _tts_queue.put(text)


def _build_text(command):
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
    return PHRASES.get(command, command.replace("_", " ") + ".")


def _worker():
    """Background thread — owns the pyttsx3 engine (fixes COM threading on Windows)."""
    import pyttsx3
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 1.0)
    except Exception as e:
        print(f"⚠️  pyttsx3 engine init failed in worker: {e}")
        return

    while True:
        try:
            text = _tts_queue.get(timeout=1)
            engine.say(text)
            engine.runAndWait()
        except queue.Empty:
            continue
        except Exception:
            continue
