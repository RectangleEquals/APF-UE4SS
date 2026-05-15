"""WorkflowRow + WorkflowHeaderRow for the DevTools CI tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.label import MDLabel

from .data_row import DevDataRow, DevHeaderRow

_COLS = [("Name", 0.45), ("Status", 0.30), ("Run", None), ("View", None)]
_RUN_W: int = 80   # dp — shared by header and Run button so columns align
_VIEW_W: int = 36  # dp — shared by header and View button


def make_workflow_header() -> DevHeaderRow:
    return DevHeaderRow.from_columns(_COLS, fixed_widths={2: dp(_RUN_W), 3: dp(_VIEW_W)})


class WorkflowRow(DevDataRow):
    """One row in the Workflows list: name / status / Run / View."""

    def __init__(
        self,
        wf: dict,
        on_run: Callable[[str, str, MDLabel], None],
        on_view: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(hover=True, **kwargs)
        wf_id    = wf.get("id")
        wf_name  = wf.get("name", "Unknown")
        html_url = wf.get("html_url", "")

        self._name_lbl   = MDLabel(text=wf_name, adaptive_height=True, size_hint_x=0.45)
        self._status_lbl = MDLabel(
            text="", adaptive_height=True, size_hint_x=0.30,
            theme_text_color="Secondary")

        self._run_btn = MDButton(
            MDButtonIcon(icon="play"),
            MDButtonText(text="Run"),
            size_hint_x=None,
            width=dp(_RUN_W),
        )
        _lbl = self._status_lbl
        self._run_btn.bind(
            on_release=lambda *_, _id=wf_id, _name=wf_name, lbl=_lbl: on_run(_id, _name, lbl)
        )

        self._view_btn = MDIconButton(icon="open-in-new", size_hint_x=None, width=dp(_VIEW_W))
        if html_url and on_view:
            self._view_btn.bind(on_release=lambda *_, u=html_url: on_view(u))
        else:
            self._view_btn.disabled = True

        # Correct column order: Name | Status | Run | View
        for w in (self._name_lbl, self._status_lbl, self._run_btn, self._view_btn):
            self.add_widget(w)

    def set_status(self, text: str) -> None:
        self._status_lbl.text = text
