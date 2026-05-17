from __future__ import annotations

from typing import Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer, MDDialogContentContainer,
)
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivymd.uix.textfield import MDTextField

from ...controllers.tabs.source_control import SourceControlController
from ..widgets.branch_row import BranchRow, make_branch_header


def _write_tier_placeholder() -> MDBoxLayout:
    outer = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(16))
    outer.add_widget(Widget(size_hint_y=None, height=dp(60)))
    outer.add_widget(MDLabel(
        text="Sign in with write access to use this section.",
        adaptive_height=True, halign="center", theme_text_color="Secondary",
    ))
    return outer


class SourceControlTab(MDBoxLayout):
    """Source Control tab — PR opener and branch management."""

    def __init__(self, ctrl: SourceControlController, **kwargs) -> None:
        super().__init__(
            orientation="vertical",
            adaptive_height=True,
            padding=dp(16),
            spacing=dp(8),
            **kwargs,
        )
        self._ctrl = ctrl
        self._pr_branch_lbl: Optional[MDLabel] = None
        self._pr_title: Optional[MDTextField] = None
        self._pr_body: Optional[MDTextField] = None
        self._branches_list: Optional[MDBoxLayout] = None
        self._status_lbl: Optional[MDLabel] = None

    def rebuild(self, logged_in: bool, write_tier: bool) -> None:
        self.clear_widgets()
        self._pr_branch_lbl = None
        self._pr_title = None
        self._pr_body = None
        self._branches_list = None
        self._status_lbl = None

        if not logged_in:
            self.add_widget(_write_tier_placeholder())
            return
        self._build_content(write_tier)
        self.refresh_pr_branch()

    def refresh_pr_branch(self) -> None:
        branch = self._ctrl.get_current_branch()
        if branch and self._pr_branch_lbl:
            self._pr_branch_lbl.text = f"Branch: {branch} -> master"

    def refresh_branches(self) -> None:
        if not self._branches_list:
            return
        self._set_status("Loading...")
        self._ctrl.refresh_branches(on_done=self._on_branches_loaded)

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_content(self, write_tier: bool) -> None:
        self.add_widget(MDLabel(
            text="Pull Requests", font_style="Title", adaptive_height=True))

        self._pr_branch_lbl = MDLabel(
            text="Branch: — -> master",
            adaptive_height=True,
            theme_text_color="Secondary",
        )
        self.add_widget(self._pr_branch_lbl)

        if not write_tier:
            self.add_widget(MDLabel(
                text=(
                    "Fill in the title and description, then click the button "
                    "to open your PR on GitHub."
                ),
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            ))

        self.add_widget(MDLabel(
            text="PR Title", adaptive_height=True,
            theme_text_color="Secondary", font_style="Body",
        ))
        self._pr_title = MDTextField(hint_text="PR title")
        self.add_widget(self._pr_title)

        self.add_widget(MDLabel(
            text="PR Description (optional)", adaptive_height=True,
            theme_text_color="Secondary", font_style="Body",
        ))
        self._pr_body = MDTextField(
            hint_text="PR description (optional)",
            multiline=True,
            size_hint_y=None,
            height=dp(120),
        )
        self.add_widget(self._pr_body)

        pr_btn = MDButton(
            MDButtonIcon(icon="source-pull"),
            MDButtonText(text="Open PR on GitHub"),
        )
        pr_btn.bind(on_release=lambda *_: self._open_pr())
        self.add_widget(pr_btn)

        self.add_widget(MDDivider())

        if write_tier:
            self._build_branches_section()
        else:
            self.add_widget(MDLabel(
                text="Branches", font_style="Title", adaptive_height=True))
            self.add_widget(MDLabel(
                text="Branch management requires collaborator access.",
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            ))

    def _build_branches_section(self) -> None:
        br_hdr = MDBoxLayout(
            orientation="horizontal", adaptive_height=True, spacing=dp(8))
        br_hdr.add_widget(MDLabel(
            text="Branches", font_style="Title", adaptive_height=True, size_hint_x=1))
        refresh_br = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_br.bind(on_release=lambda *_: self.refresh_branches())
        br_hdr.add_widget(refresh_br)
        new_br_btn = MDButton(
            MDButtonIcon(icon="source-branch-plus"),
            MDButtonText(text="New Branch"),
            size_hint_x=None,
        )
        new_br_btn.bind(on_release=lambda *_: self._show_new_branch_dialog())
        br_hdr.add_widget(new_br_btn)
        self.add_widget(br_hdr)

        self.add_widget(MDLabel(
            text="Manages remote branches on GitHub. Deletions cannot be undone.",
            adaptive_height=True, theme_text_color="Secondary", font_style="Body",
        ))
        self.add_widget(make_branch_header())

        self._branches_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(4))
        self.add_widget(self._branches_list)

        self._status_lbl = MDLabel(
            text="", adaptive_height=True,
            font_style="Body", theme_text_color="Secondary",
        )
        self.add_widget(self._status_lbl)

    # -----------------------------------------------------------------------
    # PR
    # -----------------------------------------------------------------------

    def _open_pr(self) -> None:
        branch = self._ctrl.get_current_branch()
        title  = self._pr_title.text.strip() if self._pr_title else ""
        if not branch:
            return
        self._ctrl.open_pr_in_browser(branch, title)

    # -----------------------------------------------------------------------
    # Branches
    # -----------------------------------------------------------------------

    def _on_branches_loaded(
        self, branches: Optional[list], error: Optional[str]
    ) -> None:
        def _upd(dt):
            if not self._branches_list:
                return
            self._branches_list.clear_widgets()
            if error:
                self._set_status(f"Error: {error}", ok=False)
                return
            for i, br in enumerate(branches or []):
                self._branches_list.add_widget(
                    BranchRow(br, on_delete=self._confirm_delete_branch, row_index=i))
            self._set_status(f"{len(branches or [])} branch(es).", ok=True)
        Clock.schedule_once(_upd)

    def _show_new_branch_dialog(self) -> None:
        name_field = MDTextField(hint_text="New branch name")
        dialog_ref: list = [None]

        def _create(*_):
            name = name_field.text.strip()
            if not name:
                return
            if dialog_ref[0]:
                dialog_ref[0].dismiss()
            self._set_status(f"Creating branch '{name}'...")
            self._ctrl.create_branch(name, on_done=self._on_branch_created)

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="New Branch"),
            MDDialogSupportingText(
                text="Branch will be created from current local HEAD."),
            MDDialogContentContainer(name_field, orientation="vertical"),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(
                    MDButtonIcon(icon="plus"),
                    MDButtonText(text="Create"),
                    style="filled", on_release=_create,
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _on_branch_created(self, ok: bool, name_or_err: str) -> None:
        def _upd(dt):
            if ok:
                self._set_status(f"Branch '{name_or_err}' created.", ok=True)
                self.refresh_branches()
            else:
                self._set_status(f"Failed: {name_or_err}", ok=False)
        Clock.schedule_once(_upd)

    def _confirm_delete_branch(self, name: str) -> None:
        dialog_ref: list = [None]

        def _delete(*_):
            if dialog_ref[0]:
                dialog_ref[0].dismiss()
            self._set_status(f"Deleting '{name}'...")
            self._ctrl.delete_branch(name, on_done=self._on_branch_deleted)

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="Delete Branch"),
            MDDialogSupportingText(text=f"Delete '{name}'? This cannot be undone."),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(
                    MDButtonIcon(icon="delete-outline"),
                    MDButtonText(text="Delete"),
                    style="filled", on_release=_delete,
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _on_branch_deleted(self, ok: bool, name_or_err: str) -> None:
        def _upd(dt):
            if ok:
                self._set_status(f"Branch '{name_or_err}' deleted.", ok=True)
                MDSnackbar(
                    MDSnackbarText(text=f"Branch '{name_or_err}' deleted."),
                    pos_hint={"center_x": 0.5, "y": 0.05},
                    size_hint_x=0.6, duration=3,
                ).open()
                self.refresh_branches()
            else:
                self._set_status(f"Failed: {name_or_err}", ok=False)
        Clock.schedule_once(_upd)

    def _set_status(self, msg: str, ok: bool = True) -> None:
        if not self._status_lbl:
            return
        self._status_lbl.text = msg
        self._status_lbl.theme_text_color = "Custom"
        self._status_lbl.text_color = (0.2, 0.8, 0.2, 1) if ok else (0.9, 0.3, 0.3, 1)
