"""ValidationWarningDialog — validation errors/warnings before queue or install."""
from __future__ import annotations

from typing import Optional, Callable

from kivy.uix.widget import Widget
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)


class ValidationWarningDialog:
    """
    Shows validation errors and/or warnings before allowing queue or install.

    Parameters
    ----------
    title         : str — headline (e.g. "Cannot Queue", "Queue with Warnings?")
    lines         : list[str] — formatted message lines to show in the body
    allow_proceed : bool — if True, show a proceed button
    proceed_label : str — label for the proceed button (default "Proceed")
    on_confirm    : Callable[[], None] — called when user clicks proceed
    on_cancel     : Callable[[], None] | None
    """

    def __init__(
        self,
        title: str,
        lines: list,
        allow_proceed: bool = False,
        proceed_label: str = "Proceed",
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ):
        self._title = title
        self._lines = lines
        self._allow_proceed = allow_proceed
        self._proceed_label = proceed_label
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._dialog: Optional[MDDialog] = None

    def open(self) -> None:
        if self._dialog:
            return
        self._dialog = self._build()
        self._dialog.open()

    def _build(self) -> MDDialog:
        def _cancel(*_):
            if self._dialog:
                self._dialog.dismiss()
            self._dialog = None
            if self._on_cancel:
                self._on_cancel()

        def _confirm(*_):
            if self._dialog:
                self._dialog.dismiss()
            self._dialog = None
            if self._on_confirm:
                self._on_confirm()

        btns = [
            Widget(),
            MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
        ]
        if self._allow_proceed:
            btns.append(MDButton(
                MDButtonText(text=self._proceed_label),
                style="filled",
                on_release=_confirm,
            ))

        return MDDialog(
            MDDialogHeadlineText(text=self._title),
            MDDialogSupportingText(text="\n".join(self._lines) or "Validation issue."),
            MDDialogButtonContainer(*btns),
        )

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def for_queue(
        cls,
        errors: list,
        warnings: list,
        allow_proceed: bool = False,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ) -> "ValidationWarningDialog":
        lines = [f"[ERROR] {r.label}: {r.detail}" for r in errors]
        lines += [f"[WARN]  {r.label}: {r.detail}" for r in warnings]
        title = "Cannot Queue" if not allow_proceed else "Queue with Warnings?"
        return cls(
            title=title,
            lines=lines,
            allow_proceed=allow_proceed,
            proceed_label="Queue Anyway",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )

    @classmethod
    def for_install(
        cls,
        title: str,
        lines: list,
        allow_proceed: bool = False,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ) -> "ValidationWarningDialog":
        return cls(
            title=title,
            lines=lines,
            allow_proceed=allow_proceed,
            proceed_label="Install Anyway",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )
