"""queue_panel.py — QueuePanelMixin: active download queue row + UI state."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator

from .....shared.ui.constants import COL_DIM

if TYPE_CHECKING:
    from .downloads_tab import _QueueItem


_BG_ITEM = (0.13, 0.13, 0.13, 1)


class QueuePanelMixin:
    """Active download queue row builder and download logic for DownloadsTab."""

    def _queue_row(self, item: "_QueueItem") -> MDBoxLayout:
        from .....shared.ui.content_row import ContentRowWidget
        row = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_ITEM,
        )
        row.add_widget(ContentRowWidget(content=item.mod, row_index=0))

        status_colors = {
            "queued":      (0.5, 0.5, 0.5, 1),
            "downloading": (0.3, 0.7, 1.0, 1),
            "unpacking":   (0.7, 0.5, 1.0, 1),
            "done":        (0.3, 0.8, 0.4, 1),
            "error":       (1.0, 0.3, 0.3, 1),
        }
        status_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24),
            padding=[dp(8), 0], spacing=dp(8),
        )
        status_row.add_widget(MDLabel(
            text=item.status.capitalize(),
            font_style="Label", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
            theme_text_color="Custom",
            text_color=status_colors.get(item.status, COL_DIM),
        ))
        if item.status in ("queued", "downloading"):
            status_row.add_widget(MDButton(
                MDButtonText(text="Cancel"),
                style="text", size_hint=(None, None), size=(dp(72), dp(24)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, qi=item: self._cancel(qi),
            ))
        row.add_widget(status_row)

        if item.status == "downloading":
            bar = MDLinearProgressIndicator(size_hint=(1, None), height=dp(4))
            bar.value = item.progress
            row.add_widget(bar)

        if item.status == "error" and item.error_msg:
            row.add_widget(MDLabel(
                text=item.error_msg,
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                padding=[dp(8), 0],
                theme_text_color="Custom", text_color=(1.0, 0.4, 0.4, 1),
            ))

        return row

    def _start_next_download(self) -> None:
        with self._queue_lock:
            pending = [q for q in self._queue if q.status == "queued"]
            active  = [q for q in self._queue if q.status == "downloading"]
        if active or not pending:
            return
        item = pending[0]
        with self._queue_lock:
            item.status = "downloading"

        from .....services.download_service import DownloadService
        svc = DownloadService(self._host)

        def _on_progress(p: float) -> None:
            self._set_progress(item, p)

        def _on_done(success: bool, error_msg: str, cache_path) -> None:
            with self._queue_lock:
                if success:
                    item.status = "done"
                    item.cache_path = cache_path
                else:
                    item.status = "error"
                    item.error_msg = error_msg
            Clock.schedule_once(lambda dt: self._on_item_done(item), 0)

        threading.Thread(
            target=svc.download_item,
            args=(item, self._game_id),
            kwargs={"on_progress": _on_progress, "on_done": _on_done},
            daemon=True,
        ).start()
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    def _set_progress(self, item: "_QueueItem", progress: float) -> None:
        with self._queue_lock:
            item.progress = progress
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    def _on_item_done(self, item: "_QueueItem") -> None:
        self._scan_cache_and_rebuild()
        self._start_next_download()

    def _cancel(self, item: "_QueueItem") -> None:
        with self._queue_lock:
            if item.status == "queued":
                self._queue.remove(item)
        self._rebuild_ui()

