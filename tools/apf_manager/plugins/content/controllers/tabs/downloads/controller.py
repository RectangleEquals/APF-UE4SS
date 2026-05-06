"""
DownloadsController — download queue, threading, and state for Tab 3.

Owns the _QueueItem dataclass (imported by DownloadsTab view) and all
download orchestration. No Kivy imports.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ....models.descriptors.base import ContentDescriptor


@dataclass
class _QueueItem:
    """One entry in the download queue."""
    mod: ContentDescriptor
    status: str = "queued"       # queued | downloading | unpacking | done | error
    progress: float = 0.0        # 0.0 – 1.0
    error_msg: str = ""
    cache_path: Optional[Path] = None
    game_id: str = ""

    @property
    def category(self) -> str:
        from ....models.descriptors.types import TemplateDescriptor as _TPL, BinaryDescriptor as _BD
        if isinstance(self.mod, _TPL):
            return "template"
        if isinstance(self.mod, _BD):
            return "other"
        return "mod"

    @property
    def key(self) -> str:
        from ....models.descriptors.types import GithubReleaseBinary as _GRB, TemplateDescriptor as _TPL
        mod = self.mod
        if isinstance(mod, _TPL):
            _src = mod.source
            owner = _src.repo.owner if _src else ""
            repo  = _src.repo.repo if _src else ""
            return f"tmpl:{owner}+{repo}/{mod.template_path}"
        if isinstance(mod, _GRB):
            _hash = mod.tags.content_hash if mod.tags else ""
            _src = mod.source
            return (f"other:{_hash}" if _hash else
                    f"other:{_src.repo.owner if _src else ''}+{_src.repo.repo if _src else ''}/{_src.tag if _src else mod.name}")
        _src = getattr(mod, "source", None)
        owner = _src.repo.owner if _src else ""
        repo  = _src.repo.repo if _src else ""
        folder = getattr(mod, "folder_name", "") or (
            _src.folder.split("/")[-1] if _src and _src.folder else getattr(mod, "mod_id", "")
        )
        return f"{owner}+{repo}/{folder}"

    @property
    def display_name(self) -> str:
        return self.mod.name or self.key


class DownloadsController:
    """
    Non-Kivy controller for DownloadsTab.

    Manages the download queue and dispatches background download threads.
    The on_progress callback is called from the download thread — callers must
    wrap in Clock.schedule_once if needed for Kivy-thread safety.
    """

    def __init__(self, host, on_queue_changed: Callable) -> None:
        self._host = host
        self._on_queue_changed = on_queue_changed
        self._queue: list[_QueueItem] = []
        self._lock = threading.Lock()
        self._active_thread: Optional[threading.Thread] = None

    # -----------------------------------------------------------------------
    # Queue management
    # -----------------------------------------------------------------------

    def add_items(self, items: list, game_id: str) -> None:
        """
        Add (content_obj, category) pairs to the queue.

        Items already in the queue (by key) are ignored.
        """
        with self._lock:
            existing_keys = {qi.key for qi in self._queue}
            for mod_obj, _category in items:
                qi = _QueueItem(mod=mod_obj, game_id=game_id)
                if qi.key not in existing_keys:
                    self._queue.append(qi)
                    existing_keys.add(qi.key)
        self._on_queue_changed()

    def get_queue(self) -> list:
        with self._lock:
            return list(self._queue)

    def get_download_count(self) -> int:
        with self._lock:
            return len(self._queue)

    def get_active_download_count(self) -> int:
        with self._lock:
            return sum(1 for qi in self._queue if qi.status == "downloading")

    def cancel_item(self, qi: "_QueueItem") -> None:
        with self._lock:
            if qi in self._queue:
                self._queue.remove(qi)
        self._on_queue_changed()

    # -----------------------------------------------------------------------
    # Download dispatch
    # -----------------------------------------------------------------------

    def start_downloads(self, game_id: str, on_item_done: Callable) -> None:
        """
        Start a background thread that processes queued items sequentially.

        on_item_done(qi: _QueueItem) — called from background thread when an
        item finishes; caller must schedule to Kivy thread if needed.
        """
        if self._active_thread and self._active_thread.is_alive():
            return

        def _worker():
            while True:
                with self._lock:
                    pending = [qi for qi in self._queue if qi.status == "queued"]
                if not pending:
                    break
                qi = pending[0]

                with self._lock:
                    qi.status = "downloading"
                self._on_queue_changed()

                download_svc = self._host.get_service("download")
                if not download_svc:
                    with self._lock:
                        qi.status = "error"
                        qi.error_msg = "Download service unavailable"
                    on_item_done(qi)
                    self._on_queue_changed()
                    break

                def _on_progress(p, _qi=qi):
                    with self._lock:
                        _qi.progress = p
                    self._on_queue_changed()

                def _on_done(success, msg, path, _qi=qi):
                    with self._lock:
                        if success:
                            _qi.status = "done"
                            _qi.cache_path = path
                        else:
                            _qi.status = "error"
                            _qi.error_msg = msg
                    on_item_done(_qi)
                    self._on_queue_changed()

                download_svc.download_item(
                    qi, qi.game_id or game_id,
                    on_progress=_on_progress,
                    on_done=_on_done,
                )

        self._active_thread = threading.Thread(target=_worker, daemon=True)
        self._active_thread.start()
