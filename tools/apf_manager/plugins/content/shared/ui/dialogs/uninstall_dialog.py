"""UninstallDialog — confirmation dialog for mod uninstall (normal and cascade)."""
from __future__ import annotations

from typing import Optional, Callable

from kivy.uix.widget import Widget
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)


class UninstallDialog:
    """
    Confirmation dialog for uninstalling a mod or triggering a cascade removal.

    Parameters
    ----------
    name          : str — mod name shown in the headline
    body_text     : str — supporting text describing what will be removed
    confirm_label : str — label for the confirm button (default "Uninstall")
    on_confirm    : Callable[[], None]
    on_cancel     : Callable[[], None] | None
    """

    def __init__(
        self,
        name: str,
        body_text: str,
        confirm_label: str = "Uninstall",
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ):
        self._name = name
        self._body_text = body_text
        self._confirm_label = confirm_label
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._dialog: Optional[MDDialog] = None

    def open(self) -> None:
        if self._dialog:
            return
        self._dialog = self._build()
        self._dialog.open()

    def _build(self) -> MDDialog:
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

        return MDDialog(
            MDDialogHeadlineText(text=f"Uninstall {self._name}?"),
            MDDialogSupportingText(text=self._body_text),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text=self._confirm_label), style="filled", on_release=_confirm),
            ),
        )

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def for_mod(
        cls,
        install_record,
        is_orphaned: bool = False,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ) -> "UninstallDialog":
        """Build an UninstallDialog for a normal (non-framework) mod."""
        components = install_record.components or ["lua"]
        comp_names = {
            "lua":       "Lua scripts (scripts/)",
            "cpp":       "C++ module (dlls/main.dll)",
            "blueprint": (
                f"Blueprint files ({', '.join(install_record.bp_pak_files_deployed or ['LogicMods/*.pak'])})"
            ),
        }
        comp_text = "\n".join(
            f"  \u2022 {comp_names[c]}" for c in components if c in comp_names
        )
        manual_note = (
            "\n\nThis mod was installed manually — APF Manager will remove it, "
            "but no backup was tracked."
            if is_orphaned else ""
        )
        body = f"The following will be removed:\n{comp_text}{manual_note}"
        return cls(
            name=install_record.name,
            body_text=body,
            confirm_label="Uninstall",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )

    @classmethod
    def for_cascade(
        cls,
        install_record,
        affected_mods: list,
        template_dirs: list,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ) -> "UninstallDialog":
        """Build an UninstallDialog for a cascade removal (framework mod)."""
        if affected_mods or template_dirs:
            affected_lines = "\n".join(
                f"  \u2022 {getattr(m, 'name', getattr(m, 'display_name', str(m)))}"
                for m in affected_mods
            )
            template_lines = "\n".join(f"  \u2022 {p}" for p in template_dirs)
            body = "Uninstalling the framework mod will also remove its entire Templates/ folder."
            if template_dirs:
                body += f"\n\nTemplate directories that will be removed:\n{template_lines}"
            if affected_mods:
                body += (
                    f"\n\nThe following mods will not function correctly without the templates:\n"
                    f"{affected_lines}\n\n"
                    "These mods will need to be reinstalled after reinstalling the framework mod."
                )
        else:
            body = (
                "Uninstalling the framework mod will remove the AP runtime and all templates.\n"
                "No currently installed mods appear to depend on its templates."
            )
        return cls(
            name=install_record.name,
            body_text=body,
            confirm_label="Uninstall Anyway",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )
