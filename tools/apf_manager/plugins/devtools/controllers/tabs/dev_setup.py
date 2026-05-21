from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from .. import version as vm
from .....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from .....core.controllers.plugin_host import PluginHost

_DEVTOOLS_CONFIG = Path.home() / ".apf_manager" / "devtools.json"


def _load_devtools_config() -> dict:
    try:
        return json.loads(_DEVTOOLS_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_devtools_config(data: dict) -> None:
    try:
        _DEVTOOLS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        _DEVTOOLS_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("[dev_setup] Failed to save devtools config: %s", exc)


class DevSetupController:
    def __init__(self, host: "PluginHost", repo_owner: str, repo_name: str) -> None:
        self._host = host
        self._repo_owner = repo_owner
        self._repo_name = repo_name

    def is_repo_valid(self) -> bool:
        return vm.is_repo_valid()

    @property
    def repo_root(self) -> Optional[Path]:
        return vm._REPO_ROOT

    def load_saved_repo_root(self) -> Optional[Path]:
        saved = _load_devtools_config().get("repo_root", "")
        if saved:
            candidate = Path(saved)
            if (candidate / ".git").is_dir():
                vm.set_repo_root(candidate)
                return candidate
        return None

    def set_repo_root(self, path: Path) -> bool:
        if not (path / ".git").is_dir():
            return False
        vm.set_repo_root(path)
        cfg = _load_devtools_config()
        cfg["repo_root"] = str(path)
        _save_devtools_config(cfg)
        return True

    def clone_repo(
        self,
        url: str,
        target: str,
        on_line: Callable[[str], None],
        on_complete: Callable[[bool, Optional[Path]], None],
    ) -> None:
        def _run():
            try:
                proc = subprocess.Popen(
                    ["git", "clone", url, target],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                for line in proc.stdout:
                    on_line(line.rstrip())
                proc.wait()
                if proc.returncode == 0:
                    new_root = Path(target)
                    vm.set_repo_root(new_root)
                    cfg = _load_devtools_config()
                    cfg["repo_root"] = str(new_root)
                    _save_devtools_config(cfg)
                    on_complete(True, new_root)
                else:
                    on_complete(False, None)
            except Exception as exc:
                logger.error(f"Clone failed: {exc}")
                on_complete(False, None)

        threading.Thread(target=_run, daemon=True).start()

    def open_setup_guide(self) -> None:
        try:
            svc = self._host.get_service("docs_viewer")
            if svc is None:
                logger.warning("docs_viewer service not available")
                return
            svc.open(
                initial_path="docs/public/dev/dev_setup.md",
                force_dev_docs=True,
                sidebar_mode="tree",
                show_mode_toggle=False,
            )
        except Exception as exc:
            logger.error(f"Could not open setup guide: {exc}")
