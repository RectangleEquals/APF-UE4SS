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
from kivymd.uix.textfield import MDTextField

from .....core.controllers.logging.manager import APFLogManager
from ...controllers.tabs.ci_ctrl import CITabController
from ..widgets.workflow_row import WorkflowRow, make_workflow_header
from ..widgets.release_row import ReleaseRow, make_release_header

import webbrowser

logger = APFLogManager.get_logger(__name__)


def _write_tier_placeholder() -> MDBoxLayout:
    outer = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(16))
    outer.add_widget(Widget(size_hint_y=None, height=dp(60)))
    outer.add_widget(MDLabel(
        text="Sign in with write access to use this section.",
        adaptive_height=True, halign="center", theme_text_color="Secondary",
    ))
    return outer


class CITab(MDBoxLayout):
    """CI tab — workflow runs and release management."""

    def __init__(self, ctrl: CITabController, **kwargs) -> None:
        super().__init__(
            orientation="vertical",
            adaptive_height=True,
            padding=dp(16),
            spacing=dp(8),
            **kwargs,
        )
        self._ctrl = ctrl
        self._workflows_list: Optional[MDBoxLayout] = None
        self._releases_list: Optional[MDBoxLayout] = None
        self._wf_status_lbl: Optional[MDLabel] = None
        self._rel_status_lbl: Optional[MDLabel] = None

    def rebuild(self, write_tier: bool) -> None:
        self.clear_widgets()
        self._workflows_list = None
        self._releases_list = None
        self._wf_status_lbl = None
        self._rel_status_lbl = None

        if not write_tier:
            self.add_widget(_write_tier_placeholder())
            return
        self._build_content()

    def refresh_workflows(self) -> None:
        if not self._workflows_list:
            return
        self._set_wf_status("Loading...")
        self._ctrl.refresh_workflows(on_done=self._on_workflows_loaded)

    def refresh_releases(self) -> None:
        if not self._releases_list:
            return
        self._set_rel_status("Loading...")
        self._ctrl.refresh_releases(on_done=self._on_releases_loaded)

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_content(self) -> None:
        wf_hdr = MDBoxLayout(
            orientation="horizontal", adaptive_height=True, spacing=dp(8))
        wf_hdr.add_widget(MDLabel(
            text="CI / Workflows", font_style="Title", adaptive_height=True, size_hint_x=1))
        refresh_wf = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_wf.bind(on_release=lambda *_: self.refresh_workflows())
        wf_hdr.add_widget(refresh_wf)
        self.add_widget(wf_hdr)
        self.add_widget(make_workflow_header())

        self._workflows_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(2))
        self.add_widget(self._workflows_list)

        self._wf_status_lbl = MDLabel(
            text="", adaptive_height=True,
            font_style="Body", theme_text_color="Secondary",
        )
        self.add_widget(self._wf_status_lbl)

        self.add_widget(MDDivider())

        rel_hdr = MDBoxLayout(
            orientation="horizontal", adaptive_height=True, spacing=dp(8))
        rel_hdr.add_widget(MDLabel(
            text="Releases", font_style="Title", adaptive_height=True, size_hint_x=1))
        refresh_rel = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_rel.bind(on_release=lambda *_: self.refresh_releases())
        rel_hdr.add_widget(refresh_rel)
        create_rel = MDButton(
            MDButtonIcon(icon="tag-plus"),
            MDButtonText(text="Create Release"),
            size_hint_x=None,
        )
        create_rel.bind(on_release=lambda *_: self._show_create_release_dialog())
        rel_hdr.add_widget(create_rel)
        self.add_widget(rel_hdr)
        self.add_widget(make_release_header())

        self._releases_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(2))
        self.add_widget(self._releases_list)

        self._rel_status_lbl = MDLabel(
            text="", adaptive_height=True,
            font_style="Body", theme_text_color="Secondary",
        )
        self.add_widget(self._rel_status_lbl)

    # -----------------------------------------------------------------------
    # Workflows
    # -----------------------------------------------------------------------

    def _on_workflows_loaded(
        self, workflows: Optional[list], error: Optional[str]
    ) -> None:
        def _on_wf_run(wf_id, wf_name, status_lbl):
            branch = self._ctrl.get_current_branch()
            status_lbl.text = "Dispatching..."
            def _on_status(s: str, lbl=status_lbl, name=wf_name):
                if s.startswith("error:"):
                    logger.error(f"[ci] Workflow '{name}' dispatch failed: {s[6:].strip()}")
                    display = "Error — see app log"
                else:
                    display = s
                Clock.schedule_once(lambda dt: setattr(lbl, "text", display))
            self._ctrl.dispatch_workflow(str(wf_id), branch, _on_status)

        def _upd(dt):
            if not self._workflows_list:
                return
            self._workflows_list.clear_widgets()
            if error:
                self._set_wf_status(f"Error: {error}", ok=False)
                return
            if not workflows:
                self._workflows_list.add_widget(MDLabel(
                    text="No workflows found in .github/workflows/",
                    adaptive_height=True, theme_text_color="Secondary",
                ))
                self._set_wf_status("")
                return
            for i, wf in enumerate(workflows):
                self._workflows_list.add_widget(
                    WorkflowRow(wf, on_run=_on_wf_run, on_view=self._open_url, row_index=i))
            self._set_wf_status(f"{len(workflows)} workflow(s) loaded.", ok=True)
        Clock.schedule_once(_upd)

    # -----------------------------------------------------------------------
    # Releases
    # -----------------------------------------------------------------------

    def _on_releases_loaded(
        self, releases: Optional[list], error: Optional[str]
    ) -> None:
        def _upd(dt):
            if not self._releases_list:
                return
            self._releases_list.clear_widgets()
            if error:
                self._set_rel_status(str(error), ok=False)
                return
            if not releases:
                self._releases_list.add_widget(MDLabel(
                    text="No releases yet.",
                    adaptive_height=True, theme_text_color="Secondary",
                ))
                self._set_rel_status("")
                return
            for i, rel in enumerate(releases[:5]):
                self._releases_list.add_widget(ReleaseRow(rel, on_view=self._open_url, row_index=i))
            self._set_rel_status(f"{len(releases)} release(s).", ok=True)
        Clock.schedule_once(_upd)

    def _show_create_release_dialog(self) -> None:
        self._ctrl.fetch_unreleased_tags(on_done=self._on_unreleased_tags_loaded)

    def _on_unreleased_tags_loaded(
        self, unreleased: Optional[list], error: Optional[str]
    ) -> None:
        def _upd(dt):
            if error:
                self._set_rel_status(str(error), ok=False)
                return
            if not unreleased:
                self._set_rel_status("No unreleased tags available.", ok=False)
                return
            self._open_create_release_dialog(unreleased)
        Clock.schedule_once(_upd)

    def _open_create_release_dialog(self, unreleased_tags: list) -> None:
        tag_field   = MDTextField(hint_text="Tag name")
        name_field  = MDTextField(hint_text="Release name (optional)")
        notes_field = MDTextField(
            hint_text="Release notes (leave empty to auto-generate)",
            multiline=True, size_hint_y=None, height=dp(120),
        )
        tag_field.text = unreleased_tags[0]
        dialog_ref: list = [None]

        def _publish(*_):
            tag   = tag_field.text.strip()
            name  = name_field.text.strip() or tag
            notes = notes_field.text.strip()
            if not tag:
                return
            if dialog_ref[0]:
                dialog_ref[0].dismiss()
            self._set_rel_status(f"Creating release for {tag}...")
            self._ctrl.create_release(
                tag, name, notes,
                on_done=lambda ok, err, url: Clock.schedule_once(
                    lambda dt: self._on_release_created(ok, err, tag, url)
                ),
            )

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="Create Release"),
            MDDialogContentContainer(
                tag_field, name_field, notes_field,
                orientation="vertical", spacing=dp(8),
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(
                    MDButtonIcon(icon="publish"),
                    MDButtonText(text="Publish"),
                    style="filled", on_release=_publish,
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _on_release_created(
        self, ok: bool, err: str, tag: str, url: str
    ) -> None:
        if ok:
            self._set_rel_status(f"Release {tag} created.", ok=True)
            self.refresh_releases()
        else:
            self._set_rel_status(str(err), ok=False)

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as exc:
            logger.warning("[ci_tab] Failed to open URL %r: %s", url, exc)

    def _set_wf_status(self, msg: str, ok: bool = True) -> None:
        if not self._wf_status_lbl:
            return
        self._wf_status_lbl.text = msg
        self._wf_status_lbl.theme_text_color = "Custom"
        self._wf_status_lbl.text_color = (0.2, 0.8, 0.2, 1) if ok else (0.9, 0.3, 0.3, 1)

    def _set_rel_status(self, msg: str, ok: bool = True) -> None:
        if not self._rel_status_lbl:
            return
        self._rel_status_lbl.text = msg
        self._rel_status_lbl.theme_text_color = "Custom"
        self._rel_status_lbl.text_color = (0.2, 0.8, 0.2, 1) if ok else (0.9, 0.3, 0.3, 1)
