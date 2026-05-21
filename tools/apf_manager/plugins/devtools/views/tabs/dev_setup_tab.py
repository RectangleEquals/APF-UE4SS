from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer, MDDialogContentContainer,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from ...controllers.tabs.dev_setup import DevSetupController
from .....core.controllers.logging.manager import APFLogManager

_log = APFLogManager.get_logger(__name__)


class DevSetupTab(MDBoxLayout):
    """Dev Setup tab — repo root path, clone dialog, setup guide link."""

    def __init__(
        self,
        ctrl: DevSetupController,
        on_setup_changed: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            orientation="vertical",
            adaptive_height=True,
            size_hint_x=1,
            padding=dp(16),
            spacing=dp(8),
            **kwargs,
        )
        self._ctrl = ctrl
        self._on_setup_changed = on_setup_changed
        self._repo_state_icon: Optional[MDIconButton] = None
        self._repo_root_lbl: Optional[MDLabel] = None
        self._build()

    def _build(self) -> None:
        root_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=1, size_hint_y=None, height=dp(48),
            spacing=dp(4),
        )
        self._repo_state_icon = MDIconButton(
            icon="alert-circle-outline",
            theme_icon_color="Custom",
            icon_color=(1, 0.8, 0, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        root_row.add_widget(self._repo_state_icon)

        self._repo_root_lbl = MDLabel(
            text="Repo source folder not set — please choose a folder",
            theme_text_color="Custom",
            text_color=(1, 0.8, 0, 1),
            adaptive_height=True,
            adaptive_width=True,
            size_hint_x=None,
            shorten=True,
            shorten_from="left",
        )
        root_row.add_widget(self._repo_root_lbl)

        browse_btn = MDIconButton(
            icon="folder-open-outline",
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        browse_btn.bind(on_release=lambda *_: self._pick_repo_root())
        root_row.add_widget(browse_btn)
        self.add_widget(root_row)

        clone_btn = MDButton(
            MDButtonIcon(icon="source-repository"),
            MDButtonText(text="Clone Repo"),
        )
        clone_btn.bind(on_release=lambda *_: self._show_clone_dialog())
        self.add_widget(clone_btn)

        setup_btn = MDButton(
            MDButtonIcon(icon="book-open-variant"),
            MDButtonText(text="View Dev Environment Setup"),
        )
        setup_btn.bind(on_release=lambda *_: self._ctrl.open_setup_guide())
        self.add_widget(setup_btn)

        self.update_repo_root_display()

    def update_repo_root_display(self) -> None:
        if self._repo_state_icon is None or self._repo_root_lbl is None:
            return
        if self._ctrl.is_repo_valid():
            self._repo_state_icon.icon = "source-repository"
            self._repo_state_icon.theme_icon_color = "Secondary"
            self._repo_root_lbl.text = str(self._ctrl.repo_root)
            self._repo_root_lbl.theme_text_color = "Secondary"
        else:
            self._repo_state_icon.icon = "alert-circle-outline"
            self._repo_state_icon.theme_icon_color = "Custom"
            self._repo_state_icon.icon_color = (1, 0.8, 0, 1)
            self._repo_root_lbl.text = "Repo source folder not set — please choose a folder"
            self._repo_root_lbl.theme_text_color = "Custom"
            self._repo_root_lbl.text_color = (1, 0.8, 0, 1)

    def _pick_repo_root(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            tk_root = tk.Tk()
            tk_root.withdraw()
            path_str = filedialog.askdirectory(title="Select Repository Root")
            tk_root.destroy()
        except Exception as exc:
            _log.warning("[dev_tools] Folder picker unavailable: %s", exc)
            return
        if not path_str:
            return
        from pathlib import Path
        ok = self._ctrl.set_repo_root(Path(path_str))
        if ok:
            self.update_repo_root_display()
            if self._on_setup_changed:
                self._on_setup_changed()

    def _show_clone_dialog(self) -> None:
        dialog_ref: list = [None]

        def _dismiss(*_):
            if dialog_ref[0] is not None:
                d = dialog_ref[0]
                dialog_ref[0] = None
                d.dismiss()

        url_field = MDTextField(
            hint_text="Repository URL",
            text="https://github.com/RectangleEquals/APF-UE4SS.git",
        )
        dir_field = MDTextField(hint_text="Target directory (will be created)")

        def _run_clone(*_):
            url = url_field.text.strip()
            target = dir_field.text.strip()
            if not url or not target:
                return
            _dismiss()

            def _on_line(line: str):
                pass

            def _on_complete(ok: bool, new_root):
                def _upd(dt):
                    if ok:
                        self.update_repo_root_display()
                        if self._on_setup_changed:
                            self._on_setup_changed()
                Clock.schedule_once(_upd)

            self._ctrl.clone_repo(url, target, _on_line, _on_complete)

        clone_btn = MDButton(
            MDButtonIcon(icon="source-repository"),
            MDButtonText(text="Clone"),
        )
        clone_btn.bind(on_release=_run_clone)

        dialog = MDDialog(
            MDDialogHeadlineText(text="Clone Repository"),
            MDDialogContentContainer(url_field, dir_field),
            MDDialogButtonContainer(
                Widget(),
                clone_btn,
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_dismiss),
            ),
        )
        dialog_ref[0] = dialog
        dialog.open()
