"""
InstallPlanDialog — shows ordered install plan before queuing.

Groups items by dependency order (Other → Framework → AP mods → Templates),
flags missing hard deps in red, and lets the user confirm or cancel.
"""
from __future__ import annotations

from typing import Optional, Callable

from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.scrollview import MDScrollView

from ..chrome.constants import COL_DIM, COL_WARN, COL_STATUS_OK, COL_STATUS_MISS


_TYPE_ORDER = {
    "github_release_binary": 0,
    "external_url_binary": 0,
    "manual_binary": 0,
    "framework_mod": 1,
    "ap_mod": 2,
    "third_party_mod": 2,
    "template": 3,
}

_TYPE_LABEL = {
    "github_release_binary": "UE4SS / Binary",
    "external_url_binary": "External Binary",
    "manual_binary": "Manual Install",
    "framework_mod": "Framework Mod",
    "ap_mod": "AP Mod",
    "third_party_mod": "UE4SS Mod",
    "template": "Template",
}


class InstallPlanDialog:
    """
    Shows an ordered list of items to download/install. User confirms or cancels.

    Parameters
    ----------
    items      : list of ContentDescriptor — items to install (order preserved)
    missing    : list[str] — mod_ids of hard deps that are absent from queue + installed
    warnings   : list[str] — human-readable warning strings
    on_confirm : Callable[[], None] — called when user clicks Confirm
    on_cancel  : Callable[[], None] | None
    """

    def __init__(
        self,
        items: list,
        missing: Optional[list] = None,
        warnings: Optional[list] = None,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ):
        self._items = items
        self._missing = missing or []
        self._warnings = warnings or []
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._dialog: Optional[MDDialog] = None

    def open(self) -> None:
        if self._dialog:
            return
        self._dialog = self._build()
        self._dialog.open()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> MDDialog:
        content_area = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(4),
            padding=[dp(4), dp(4)],
        )

        sorted_items = sorted(
            self._items,
            key=lambda c: _TYPE_ORDER.get(getattr(c, "content_type", ""), 99),
        )

        for item in sorted_items:
            content_area.add_widget(self._item_row(item))

        for mid in self._missing:
            row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
            )
            row.add_widget(MDIcon(
                icon="alert-circle-outline", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=(0.9, 0.3, 0.3, 1),
            ))
            row.add_widget(MDLabel(
                text=f"Missing dep: {mid}",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=(0.9, 0.3, 0.3, 1),
            ))
            content_area.add_widget(row)

        for warn in self._warnings:
            row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
            )
            row.add_widget(MDIcon(
                icon="alert-outline", size_hint=(None, 1), width=dp(20),
                theme_icon_color="Custom", icon_color=COL_WARN,
            ))
            row.add_widget(MDLabel(
                text=warn, font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=COL_WARN,
            ))
            content_area.add_widget(row)

        n = len(self._items)
        confirm_label = f"Download {n} item{'s' if n != 1 else ''}"

        def _confirm(*_):
            if self._dialog:
                self._dialog.dismiss()
            self._dialog = None
            if self._on_confirm:
                self._on_confirm()

        def _cancel(*_):
            if self._dialog:
                self._dialog.dismiss()
            self._dialog = None
            if self._on_cancel:
                self._on_cancel()

        btn_confirm = MDButton(
            MDButtonText(text=confirm_label),
            style="filled",
            on_release=_confirm,
        )
        btn_cancel = MDButton(
            MDButtonText(text="Cancel"),
            style="text",
            on_release=_cancel,
        )

        return MDDialog(
            MDDialogHeadlineText(text="Install Plan"),
            content_area,
            MDDialogButtonContainer(
                Widget(),
                btn_cancel,
                btn_confirm,
            ),
        )

    def _item_row(self, item) -> MDBoxLayout:
        ctype = getattr(item, "content_type", "")
        type_label = _TYPE_LABEL.get(ctype, ctype)
        name = getattr(item, "name", "Unknown")
        version = getattr(item, "version", "")

        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(8),
        )
        type_color = _type_color(ctype)
        row.add_widget(MDLabel(
            text=f"[{type_label}]", font_style="Label", role="small",
            size_hint=(None, 1), width=dp(110),
            theme_text_color="Custom", text_color=type_color,
        ))
        row.add_widget(MDLabel(
            text=name, font_style="Label", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        if version:
            row.add_widget(MDLabel(
                text=version, font_style="Label", role="small",
                size_hint=(None, 1), width=dp(72),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        return row


def _type_color(ctype: str):
    if ctype in ("github_release_binary", "external_url_binary", "manual_binary"):
        return (0.8, 0.55, 0.1, 1)
    if ctype == "framework_mod":
        return (0.5, 0.8, 1.0, 1)
    if ctype == "ap_mod":
        return (0.3, 0.5, 0.9, 1)
    if ctype == "template":
        return (0.2, 0.7, 0.6, 1)
    return (0.6, 0.6, 0.6, 1)
