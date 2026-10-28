"""Small shutdown bridge used only by the packaged desktop host."""
from __future__ import annotations

from collections.abc import Callable

_shutdown_callback: Callable[[], None] | None = None


def set_shutdown_callback(callback: Callable[[], None]) -> None:
    global _shutdown_callback
    _shutdown_callback = callback


def request_shutdown() -> bool:
    if _shutdown_callback is None:
        return False
    _shutdown_callback()
    return True
