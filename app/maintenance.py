import threading


_lock = threading.RLock()
_maintenance_mode = False


def is_enabled() -> bool:
    with _lock:
        return _maintenance_mode


def set_enabled(value: bool) -> None:
    global _maintenance_mode
    with _lock:
        _maintenance_mode = value
