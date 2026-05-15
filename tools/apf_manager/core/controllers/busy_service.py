"""BusyService — key-counted busy state manager.

Overlay shows when any key is held; hides only when all keys are cleared.
All UI calls are routed via Clock.schedule_once so callers may call from
any thread.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from ...core.views.widgets.busy_overlay import BusyOverlay


class BusyService:
    """
    Key-counted busy state manager.

    Usage (from any thread):
        svc = host.get_service("busy")
        svc.set_busy("my.op", "Fetching data...")
        ...async work...
        svc.clear_busy("my.op")
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._messages: dict[str, str] = {}
        self._overlay: Optional["BusyOverlay"] = None

    # -----------------------------------------------------------------------
    # Wiring
    # -----------------------------------------------------------------------

    def attach_overlay(self, overlay: "BusyOverlay") -> None:
        """Wire the view widget after the Kivy UI is built (main thread)."""
        self._overlay = overlay

    # -----------------------------------------------------------------------
    # Public API — safe to call from any thread
    # -----------------------------------------------------------------------

    def set_busy(self, key: str, message: str = "Working...") -> None:
        """Increment ref count for key; show overlay if not already visible."""
        self._counts[key] = self._counts.get(key, 0) + 1
        self._messages[key] = message
        logger.debug("busy set: key=%r count=%d msg=%r", key, self._counts[key], message)
        self._schedule_show(message)

    def update_message(self, key: str, message: str) -> None:
        """Update displayed status text while key is held."""
        if key not in self._counts:
            return
        self._messages[key] = message
        self._schedule_set_message(message)

    def clear_busy(self, key: str) -> None:
        """Decrement ref count; hide overlay when all keys reach zero."""
        if key not in self._counts:
            return
        self._counts[key] -= 1
        if self._counts[key] <= 0:
            del self._counts[key]
            del self._messages[key]
        logger.debug("busy clear: key=%r remaining=%d", key, len(self._counts))
        if not self._counts:
            self._schedule_hide()

    def is_busy(self) -> bool:
        return bool(self._counts)

    # -----------------------------------------------------------------------
    # Internal — Clock-scheduled UI calls
    # -----------------------------------------------------------------------

    def _schedule_show(self, message: str) -> None:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_show(message), 0)

    def _schedule_hide(self) -> None:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_hide(), 0)

    def _schedule_set_message(self, message: str) -> None:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._do_set_message(message), 0)

    def _do_show(self, message: str) -> None:
        if self._overlay:
            self._overlay.show(message)

    def _do_hide(self) -> None:
        if self._overlay:
            self._overlay.hide()

    def _do_set_message(self, message: str) -> None:
        if self._overlay:
            self._overlay.set_message(message)
