"""
Lightweight logger for APFramework apworld.

Controlled by two optional YAML options:
- apf_log: minimum log level (trace/debug/info/warn/error). Default: warn
- apf_logfile: file path for log output. Default: "" (uses print)

These options are NOT auto-generated in framework YAMLs. Developers
add them manually when debugging:

    APFramework:
      apf_log: debug
      apf_logfile: "C:/temp/apf_debug.log"
"""

from datetime import datetime


class APFLogger:
    """Custom logger that is silent by default (warn level) and safe for
    AP's official servers where file I/O is restricted."""

    LEVELS = {"trace": 0, "debug": 1, "info": 2, "warn": 3, "error": 4}

    def __init__(self, min_level: str = "warn", logfile: str = ""):
        self.min_level = self.LEVELS.get(min_level.lower(), 3)
        self.logfile = logfile
        self._file = None

        if logfile:
            try:
                self._file = open(logfile, "a", encoding="utf-8")
            except OSError:
                pass  # Silently fall back to print if file can't be opened

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    def _emit(self, level: str, message: str, component: str = ""):
        if self.LEVELS.get(level, 2) < self.min_level:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        comp = f" [{component}]" if component else ""
        line = f"[{ts}] [{level.upper()}]{comp} {message}"
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()
        else:
            print(line)

    def trace(self, msg: str, component: str = ""):
        self._emit("trace", msg, component)

    def debug(self, msg: str, component: str = ""):
        self._emit("debug", msg, component)

    def info(self, msg: str, component: str = ""):
        self._emit("info", msg, component)

    def warn(self, msg: str, component: str = ""):
        self._emit("warn", msg, component)

    def error(self, msg: str, component: str = ""):
        self._emit("error", msg, component)
