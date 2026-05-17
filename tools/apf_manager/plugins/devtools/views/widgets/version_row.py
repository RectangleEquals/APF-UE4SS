"""VersionRow + make_version_header for the DevTools Versions tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.label import MDLabel

from .data_row import DevDataRow, DevHeaderRow

# Fixed column widths (dp) — shared by header and data rows so they always align
# regardless of ScrollView scrollbar width.
_W = dict(component=110, local=90, remote=90, status=90, bump=120, action=130)

_COLS = [
    ("Component", None), ("Local", None), ("Remote", None),
    ("Status", None), ("Bump", None), ("Action", None),
]
_FIXED_WIDTHS = {i: dp(v) for i, v in enumerate(_W.values())}


def make_version_header() -> DevHeaderRow:
    return DevHeaderRow.from_columns(_COLS, fixed_widths=_FIXED_WIDTHS)


class VersionRow(DevDataRow):
    """
    One row in the Versions table: component / local / remote / status / bump / commit.
    """

    def __init__(
        self,
        component: str,
        label: str,
        bump_part: str,
        on_bump_menu: Callable,
        on_commit_tag: Callable,
        row_index: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(hover=False, row_index=row_index, **kwargs)
        self.component = component

        self._label_lbl = MDLabel(
            text=label,
            size_hint_x=None, width=dp(_W["component"]),
            adaptive_height=True,
        )
        self._local_lbl = MDLabel(
            text="--",
            size_hint_x=None, width=dp(_W["local"]),
            adaptive_height=True,
            theme_text_color="Secondary",
        )
        self._remote_lbl = MDLabel(
            text="--",
            size_hint_x=None, width=dp(_W["remote"]),
            adaptive_height=True,
            theme_text_color="Secondary",
        )
        self._status_lbl = MDLabel(
            text="",
            size_hint_x=None, width=dp(_W["status"]),
            adaptive_height=True,
        )
        self._bump_btn = MDButton(
            MDButtonIcon(icon="chevron-up"),
            MDButtonText(text=bump_part),
            size_hint_x=None,
            width=dp(_W["bump"]),
        )
        self._bump_btn.bind(
            on_release=lambda btn, c=component: on_bump_menu(btn, c),
        )
        self._commit_btn = MDButton(
            MDButtonIcon(icon="tag-check"),
            MDButtonText(text="Commit & Tag"),
            size_hint_x=None,
            width=dp(_W["action"]),
        )
        self._commit_btn.bind(
            on_release=lambda *_, c=component: on_commit_tag(c),
        )

        for w in (self._label_lbl, self._local_lbl, self._remote_lbl,
                  self._status_lbl, self._bump_btn, self._commit_btn):
            self.add_widget(w)

    # -----------------------------------------------------------------------
    # Accessors used by VersionsTab
    # -----------------------------------------------------------------------

    @property
    def local_lbl(self) -> MDLabel:
        return self._local_lbl

    @property
    def remote_lbl(self) -> MDLabel:
        return self._remote_lbl

    @property
    def status_lbl(self) -> MDLabel:
        return self._status_lbl

    @property
    def bump_btn(self) -> MDButton:
        return self._bump_btn

    @property
    def commit_btn(self) -> MDButton:
        return self._commit_btn

    def set_bump_label(self, part: str) -> None:
        from kivymd.uix.button import MDButtonText
        for child in self._bump_btn.walk(restrict=True):
            if isinstance(child, MDButtonText):
                child.text = part
                break

    def set_status(self, local: Optional[str], remote: Optional[str]) -> None:
        if not local or not remote:
            self._status_lbl.text = ""
            self._status_lbl.theme_text_color = "Secondary"
            return
        if local == remote:
            self._status_lbl.text = "Up to date"
            self._status_lbl.theme_text_color = "Custom"
            self._status_lbl.text_color = (0.3, 0.8, 0.3, 1)
        else:
            self._status_lbl.text = "Needs bump"
            self._status_lbl.theme_text_color = "Custom"
            self._status_lbl.text_color = (1, 0.7, 0, 1)
