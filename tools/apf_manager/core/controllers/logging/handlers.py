from __future__ import annotations

import logging
from typing import Callable, Optional


class APFPanelHandler(logging.Handler):
    """Forwards log records to the in-app LogPanel widget, wired after UI is built."""

    def __init__(self, display_level: int = logging.INFO):
        super().__init__(level=display_level)
        self._panel_fn: Optional[Callable[[str, int], None]] = None

    def set_panel_fn(self, fn: Callable[[str, int], None]) -> None:
        self._panel_fn = fn

    def emit(self, record: logging.LogRecord) -> None:
        if not self._panel_fn:
            return
        try:
            self._panel_fn(self.format(record), record.levelno)
        except Exception:
            self.handleError(record)
