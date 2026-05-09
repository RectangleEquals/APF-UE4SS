"""SharingMixin — registry share/import for RegistryService."""
from __future__ import annotations

import base64
import json
from typing import Callable, TYPE_CHECKING

from ......core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)


class SharingMixin:
    """Mixin for RegistryService: search_github, export/import base64, is_share_payload."""

    def search_github(self, game_id: str, on_done: Callable[[list], None]) -> None:
        """
        Search GitHub for repos tagged apf-ue4ss-registry-{game_id}.
        Results are cached; calls on_done(results) directly (caller schedules if needed).
        """
        import threading

        def _bg():
            resolver = self._get_resolver()
            cache = self._get_cache()
            results = resolver.search_github(game_id, cache)
            on_done(results)

        threading.Thread(target=_bg, daemon=True).start()

    def export_registries_b64(self) -> str:
        urls = [r["url"] for r in self._host.config.get_user_registries()]
        payload = {"apf_registry_share": "v1", "registries": urls}
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def import_registries_b64(self, encoded: str) -> list[str]:
        """Decode a share payload and return the list of registry URLs."""
        try:
            data = json.loads(base64.b64decode(encoded.strip().encode()).decode())
            if data.get("apf_registry_share") != "v1":
                return []
            return data.get("registries", [])
        except Exception as exc:
            logger.warning(f"import_registries_b64 decode failed: {exc}")
            return []

    @staticmethod
    def is_share_payload(text: str) -> bool:
        """Return True if text looks like a base64 registry share payload."""
        try:
            data = json.loads(base64.b64decode(text.strip().encode()).decode())
            return data.get("apf_registry_share") == "v1"
        except Exception:
            return False
