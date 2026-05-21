"""StagingMixin — mod staging and install queue for RegistryService."""
from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class StagingMixin:
    """Mixin for RegistryService: stage_mod, unstage_mod, get_staged, validate_queue, install_queue."""

    def stage_mod(self, mod_id: str) -> None:
        with self._lock:
            if mod_id not in self._staged:
                self._staged.append(mod_id)

    def unstage_mod(self, mod_id: str) -> None:
        with self._lock:
            self._staged = [s for s in self._staged if s != mod_id]

    def get_staged(self) -> list:
        game_id = self._get_game_id() or ""
        all_mods = self.get_mods(game_id)
        id_to_mod = {m.mod_id: m for m in all_mods}
        with self._lock:
            return [id_to_mod[sid] for sid in self._staged if sid in id_to_mod]

    def validate_queue(self, game_id: str) -> list:
        from . import RegistryError  # late import; service is fully loaded at call time
        errors: list = []
        staged = self.get_staged()
        candidates = self.get_framework_candidates(game_id)

        if not candidates:
            errors.append(RegistryError(
                error_type="no_framework_mod",
                severity="error",
                message="No framework mod candidate found — install is blocked.",
            ))

        seen: dict[str, int] = {}
        for m in staged:
            seen[m.mod_id] = seen.get(m.mod_id, 0) + 1
        for mid, count in seen.items():
            if count > 1:
                errors.append(RegistryError(
                    error_type="duplicate_mod_id",
                    severity="error",
                    message=f"Duplicate mod staged: {mid} ({count}×).",
                    affected=[mid],
                ))

        return errors

    def install_queue(
        self,
        game_id: str,
        on_progress: Callable[[str], None],
        on_done: Callable[[bool, str], None],
    ) -> None:
        """Install all staged mods. Blocking work runs on a background thread."""
        import threading
        errors = self.validate_queue(game_id)
        blocking = [e for e in errors if e.severity == "error"]
        if blocking:
            on_done(False, blocking[0].message)
            return

        def _bg():
            raise NotImplementedError(
                "Staging install workflow not yet implemented — "
                "use DownloadsTab cache-based install instead."
            )

        threading.Thread(target=_bg, daemon=True).start()
