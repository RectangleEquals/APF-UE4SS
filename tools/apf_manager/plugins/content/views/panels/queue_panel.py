"""queue_panel.py — QueuePanelMixin: active download queue row + UI state."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator

from .....core.controllers.logging.manager import APFLogManager
from ..chrome.constants import COL_DIM

if TYPE_CHECKING:
    from ..tabs.downloads import _QueueItem

logger = APFLogManager.get_logger(__name__)

_BG_ITEM = (0.13, 0.13, 0.13, 1)
_THROTTLE_INTERVAL = 0.25   # seconds between Clock.schedule_once calls per item


class QueuePanelMixin:
    """Active download queue row builder and download logic for DownloadsTab."""

    def _queue_row(self, item: "_QueueItem") -> MDBoxLayout:
        from ..rows.content_row import ContentRowWidget
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
            # Reuse pre-registered widgets created before thread start; create if absent.
            # Detach from previous parent first — clear_widgets() on the container only
            # sets row.parent=None for direct children, not nested bar/lbl inside old rows.
            bar = self._progress_bars.get(item.key)
            if bar is None:
                bar = MDLinearProgressIndicator(size_hint=(1, None), height=dp(4))
                self._progress_bars[item.key] = bar
            elif bar.parent is not None:
                bar.parent.remove_widget(bar)
            bar.value = item.progress * 100
            row.add_widget(bar)

            lbl = self._progress_labels.get(item.key)
            if lbl is None:
                lbl = _make_progress_label()
                self._progress_labels[item.key] = lbl
            elif lbl.parent is not None:
                lbl.parent.remove_widget(lbl)
            lbl.text = _format_progress(item)
            row.add_widget(lbl)

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

        # Pre-register bar and label widgets BEFORE the thread starts.
        # This guarantees _set_progress never hits the no-widget path during download.
        item._start_time = time.monotonic()
        if item.key not in self._progress_bars:
            self._progress_bars[item.key] = MDLinearProgressIndicator(
                size_hint=(1, None), height=dp(4))
        if item.key not in self._progress_labels:
            self._progress_labels[item.key] = _make_progress_label()

        logger.info(f"[download] Starting: {item.mod.name!r}")

        from ...controllers.download.service import DownloadService
        svc = DownloadService(self._host)

        def _on_progress(p: float) -> None:
            self._set_progress(item, p)

        def _on_done(success: bool, error_msg: str, cache_path) -> None:
            with self._queue_lock:
                if success:
                    item.status = "done"
                    item.cache_path = cache_path
                    logger.info(f"[download] Completed: {item.mod.name!r}")
                else:
                    item.status = "error"
                    item.error_msg = error_msg
                    logger.error(f"[download] Failed: {item.mod.name!r} — {error_msg}")
            self._progress_bars.pop(item.key, None)
            self._progress_labels.pop(item.key, None)
            self._last_progress_time.pop(item.key, None)
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

        key = item.key
        now = time.monotonic()
        if now - self._last_progress_time.get(key, 0.0) < _THROTTLE_INTERVAL:
            return
        self._last_progress_time[key] = now

        bar = self._progress_bars.get(key)
        lbl = self._progress_labels.get(key)
        if bar is None and lbl is None:
            return

        progress_text = _format_progress(item)

        def _upd(dt):
            if bar is not None:
                bar.value = progress * 100
            if lbl is not None:
                lbl.text = progress_text

        Clock.schedule_once(_upd, 0)

    def _on_item_done(self, item: "_QueueItem") -> None:
        self._scan_cache_and_rebuild()
        self._start_next_download()

    def _cancel(self, item: "_QueueItem") -> None:
        with self._queue_lock:
            if item.status == "queued":
                self._queue.remove(item)
                logger.info(f"[download] Cancelled: {item.mod.name!r}")
        self._progress_bars.pop(item.key, None)
        self._progress_labels.pop(item.key, None)
        self._last_progress_time.pop(item.key, None)
        self._rebuild_ui()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _make_progress_label() -> MDLabel:
    return MDLabel(
        text="0%",
        font_style="Label", role="small",
        size_hint_y=None, height=dp(16),
        padding=[dp(8), 0],
        halign="left", valign="middle",
        theme_text_color="Custom",
        text_color=(0.5, 0.7, 1.0, 1),
    )


def _format_progress(item: "_QueueItem") -> str:
    """Compute a rich progress string from item progress and elapsed time."""
    p = item.progress
    pct = f"{p * 100:.0f}%"
    elapsed = time.monotonic() - item._start_time if item._start_time > 0 else 0.0
    if elapsed > 0.5 and p > 0.01:
        rate = p / elapsed
        remaining = (1.0 - p) / rate
        if remaining < 60:
            eta = f"ETA ~{remaining:.0f}s"
        elif remaining < 3600:
            eta = f"ETA ~{remaining / 60:.0f}m"
        else:
            eta = f"ETA ~{remaining / 3600:.1f}h"
        return f"{pct}  ·  {eta}"
    return pct
