from __future__ import annotations

from typing import Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu

from ...controllers.tabs.versions import VersionsController
from ..widgets.version_row import VersionRow, make_version_header

_COMPONENTS = ("framework", "manager", "apworld")
_COMPONENT_LABELS = {"framework": "Framework", "manager": "Manager", "apworld": "Apworld"}
_BUMP_PARTS = ["patch", "minor", "major"]


def _write_tier_placeholder() -> MDBoxLayout:
    outer = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(16))
    outer.add_widget(Widget(size_hint_y=None, height=dp(60)))
    outer.add_widget(MDLabel(
        text="Sign in with write access to use this section.",
        adaptive_height=True, halign="center", theme_text_color="Secondary",
    ))
    return outer


class VersionsTab(MDBoxLayout):
    """Versions tab — local/remote version table, bump, commit & tag."""

    def __init__(self, ctrl: VersionsController, **kwargs) -> None:
        super().__init__(
            orientation="vertical",
            adaptive_height=True,
            padding=dp(16),
            spacing=dp(8),
            **kwargs,
        )
        self._ctrl = ctrl
        self._version_rows: dict[str, VersionRow] = {}
        self._bump_menus: dict[str, MDDropdownMenu] = {}
        self._status_lbl: Optional[MDLabel] = None

    def rebuild(self, write_tier: bool) -> None:
        self.clear_widgets()
        self._version_rows.clear()
        self._status_lbl = None

        if not write_tier:
            self.add_widget(_write_tier_placeholder())
            return
        self._build_content()

    def refresh(self) -> None:
        versions = self._ctrl.load_local_versions()
        for component, ver in versions.items():
            row = self._version_rows.get(component)
            if row:
                row.local_lbl.text = ver or "?"
                row.status_lbl.text = ""
        self._ctrl.refresh_remote_versions(on_done=self._on_remote_loaded)

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_content(self) -> None:
        self.add_widget(MDLabel(
            text="Version Management", font_style="Title", adaptive_height=True))

        if not self._ctrl.is_repo_valid():
            self.add_widget(MDLabel(
                text="Repo source folder not configured — see Dev Setup tab.",
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(1, 0.8, 0, 1),
            ))
            return

        self.add_widget(MDLabel(
            text=(
                "Shows local vs. remote version for each component. "
                "Use Bump to increment the version, then Commit & Tag to push a git tag."
            ),
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
        ))
        self.add_widget(MDDivider())
        self.add_widget(make_version_header())

        self._versions_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(2))

        for i, component in enumerate(_COMPONENTS):
            row = VersionRow(
                component=component,
                label=_COMPONENT_LABELS[component],
                bump_part=self._ctrl.get_bump_part(component),
                on_bump_menu=self._open_bump_menu,
                on_commit_tag=self._on_commit_tag,
                row_index=i,
            )
            self._version_rows[component] = row
            self._versions_list.add_widget(row)

        self.add_widget(self._versions_list)

        self._status_lbl = MDLabel(
            text="", adaptive_height=True,
            font_style="Body", theme_text_color="Secondary",
        )
        self.add_widget(self._status_lbl)

    # -----------------------------------------------------------------------
    # Bump menu
    # -----------------------------------------------------------------------

    def _open_bump_menu(self, caller, component: str) -> None:
        items = [
            {
                "text": part,
                "on_release": lambda x, c=component, p=part: self._set_bump(c, p),
            }
            for part in _BUMP_PARTS
        ]
        menu = MDDropdownMenu(caller=caller, items=items)
        self._bump_menus[component] = menu
        menu.open()

    def _set_bump(self, component: str, part: str) -> None:
        self._ctrl.set_bump_part(component, part)
        row = self._version_rows.get(component)
        if row:
            row.set_bump_label(part)
        menu = self._bump_menus.get(component)
        if menu:
            menu.dismiss()

    # -----------------------------------------------------------------------
    # Commit & tag
    # -----------------------------------------------------------------------

    def _on_commit_tag(self, component: str) -> None:
        self._set_status(f"Committing {component}...")
        self._ctrl.commit_and_tag(
            component,
            on_done=lambda ok, err, ver: Clock.schedule_once(
                lambda dt: self._on_committed(ok, err, ver, component)
            ),
        )

    def _on_committed(
        self, ok: bool, err: str, new_ver: str, component: str
    ) -> None:
        if ok:
            self._set_status(f"{component} v{new_ver} tagged.", ok=True)
            self.refresh()
            Clock.schedule_once(
                lambda dt: self._ctrl.refresh_remote_versions(
                    on_done=self._on_remote_loaded), 8)
        else:
            self._set_status(f"Failed: {err}", ok=False)

    # -----------------------------------------------------------------------
    # Remote versions
    # -----------------------------------------------------------------------

    def _on_remote_loaded(
        self, remote: Optional[dict], error: Optional[str]
    ) -> None:
        def _upd(dt):
            if error:
                self._set_status(f"Tag fetch failed: {error}", ok=False)
                return
            for component, rem_ver in (remote or {}).items():
                row = self._version_rows.get(component)
                if not row:
                    continue
                local_ver = self._ctrl._local_versions.get(component)
                row.remote_lbl.text = rem_ver or "--"
                slbl = row.status_lbl
                if local_ver and rem_ver:
                    if local_ver == rem_ver:
                        slbl.text = "Current"
                        slbl.theme_text_color = "Custom"
                        slbl.text_color = (0.2, 0.8, 0.2, 1)
                    elif local_ver > rem_ver:
                        slbl.text = "Ahead"
                        slbl.theme_text_color = "Custom"
                        slbl.text_color = (0.3, 0.6, 1.0, 1)
                    else:
                        slbl.text = "Behind"
                        slbl.theme_text_color = "Custom"
                        slbl.text_color = (1.0, 0.6, 0.2, 1)
                else:
                    slbl.text = "No tag" if local_ver else "?"
                    slbl.theme_text_color = "Secondary"
        Clock.schedule_once(_upd)

    def _set_status(self, msg: str, ok: bool = True) -> None:
        if not self._status_lbl:
            return
        self._status_lbl.text = msg
        self._status_lbl.theme_text_color = "Custom"
        self._status_lbl.text_color = (0.2, 0.8, 0.2, 1) if ok else (0.9, 0.3, 0.3, 1)
