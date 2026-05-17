"""WorkflowRow + make_workflow_header for the DevTools CI tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.label import MDLabel

from .data_row import DevDataRow, DevHeaderRow

# Fixed-width columns (dp).  Name is flexible (size_hint_x=1).
_W_STATUS = 140
_W_RUN    = 80
_W_VIEW   = 36

_COLS = [("Name", 1), ("Status", None), ("Run", None), ("View", None)]
_FIXED_WIDTHS = {1: dp(_W_STATUS), 2: dp(_W_RUN), 3: dp(_W_VIEW)}


def make_workflow_header() -> DevHeaderRow:
    return DevHeaderRow.from_columns(_COLS, fixed_widths=_FIXED_WIDTHS)


class WorkflowRow(DevDataRow):
    """One row in the Workflows list: name / status / Run / View."""

    def __init__(
        self,
        wf: dict,
        on_run: Callable[[str, str, MDLabel], None],
        on_view: Optional[Callable[[str], None]] = None,
        row_index: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(hover=True, row_index=row_index, **kwargs)
        wf_id    = wf.get("id")
        wf_name  = wf.get("name", "Unknown")
        html_url = wf.get("html_url", "")

        self._name_lbl = MDLabel(
            text=wf_name,
            size_hint_x=1,
            size_hint_y=1,
            valign="middle",
            halign="left",
        )
        self._status_lbl = MDLabel(
            text="",
            size_hint_x=None,
            width=dp(_W_STATUS),
            size_hint_y=1,
            valign="middle",
            halign="left",
            theme_text_color="Secondary",
        )

        self._run_btn = MDButton(
            MDButtonIcon(icon="play"),
            MDButtonText(text="Run"),
            size_hint=(None, None),
            width=dp(_W_RUN),
            height=dp(36),
            pos_hint={"center_y": 0.5},
        )
        _lbl = self._status_lbl
        self._run_btn.bind(
            on_release=lambda *_, _id=wf_id, _name=wf_name, lbl=_lbl: on_run(_id, _name, lbl),
        )

        self._view_btn = MDIconButton(
            icon="open-in-new",
            size_hint=(None, None),
            width=dp(_W_VIEW),
            height=dp(36),
            pos_hint={"center_y": 0.5},
        )
        if html_url and on_view:
            self._view_btn.bind(on_release=lambda *_, u=html_url: on_view(u))
        else:
            self._view_btn.disabled = True

        for w in (self._name_lbl, self._status_lbl, self._run_btn, self._view_btn):
            self.add_widget(w)

    def set_status(self, text: str) -> None:
        self._status_lbl.text = text
