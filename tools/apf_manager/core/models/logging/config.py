from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LogConfig:
    log_level: int = logging.DEBUG
    display_level: int = logging.INFO
    dev_mode: bool = False
    to_console: bool = True
    to_file: bool = True
    log_dir: Optional[Path] = None
