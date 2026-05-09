from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .handlers import APFPanelHandler
from ...models.logging.config import LogConfig


class APFLogManager:
    """Central logging manager. Call setup() once at startup; get_logger() everywhere else."""

    _panel_handler: Optional[APFPanelHandler] = None
    _log_file: Optional[Path] = None
    _initialized: bool = False

    @classmethod
    def setup(cls, config: LogConfig) -> None:
        root = logging.getLogger("apf_manager")
        root.setLevel(config.log_level)
        root.propagate = False

        fmt = logging.Formatter("[%(levelname)s] %(name)s -- %(message)s")
        ts_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        if config.to_console:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            root.addHandler(sh)

        if config.to_file:
            log_dir = config.log_dir or (Path.home() / ".apf_manager" / "logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            cls._log_file = log_dir / f"apf_manager_{ts}.log"
            fh = logging.FileHandler(cls._log_file, encoding="utf-8")
            fh.setFormatter(ts_fmt)
            root.addHandler(fh)

        display_lvl = logging.DEBUG if config.dev_mode else config.display_level
        cls._panel_handler = APFPanelHandler(display_level=display_lvl)
        cls._panel_handler.setFormatter(fmt)
        root.addHandler(cls._panel_handler)
        cls._initialized = True

    @classmethod
    def attach_panel(cls, panel_fn: Callable[[str, int], None]) -> None:
        """Wire the in-app LogPanel AFTER Kivy UI is built."""
        if cls._panel_handler:
            cls._panel_handler.set_panel_fn(panel_fn)

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Return a child logger under the 'apf_manager' namespace."""
        clean = re.sub(r"^(tools\.)?apf_manager\.?", "", name)
        return logging.getLogger(f"apf_manager.{clean}" if clean else "apf_manager")

    @classmethod
    def get_log_file_path(cls) -> Optional[Path]:
        return cls._log_file
