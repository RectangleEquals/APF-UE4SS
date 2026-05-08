from __future__ import annotations

from typing import Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu

from ...controllers.tabs.versions import VersionsController

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
        self._version_rows: dict[str, dict] = {}
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
                row["local_lbl"].text = ver or "?"
                row["status_lbl"].text = ""
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

        hdr_row = MDBoxLayout(
            orientation="horizontal", adaptive_height=True, spacing=dp(8))
        for txt, sx in [("Component", 0.15), ("Local", 0.18), ("Remote", 0.18),
                        ("Status", 0.15), ("Bump", 0.18), ("Action", 0.16)]:
            hdr_row.add_widget(MDLabel(
                text=txt, size_hint_x=sx, adaptive_height=True,
                theme_text_color="Secondary", font_style="Body",
            ))
        self.add_widget(hdr_row)

        for component in _COMPONENTS:
            self.add_widget(self._make_version_row(component))

        self._status_lbl = MDLabel(
            text="", adaptive_height=True,
            font_style="Body", theme_text_color="Secondary",
        )
        self.add_widget(self._status_lbl)

    def _make_version_row(self, component: str) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal", adaptive_height=True,
            spacing=dp(8), padding=(0, dp(2), 0, dp(2)),
        )
        label      = MDLabel(
            text=_COMPONENT_LABELS[component], size_hint_x=0.15, adaptive_height=True)
        local_lbl  = MDLabel(
            text="—", size_hint_x=0.18, adaptive_height=True,
            theme_text_color="Secondary")
        remote_lbl = MDLabel(
            text="—", size_hint_x=0.18, adaptive_height=True,
            theme_text_color="Secondary")
        status_lbl = MDLabel(text="", size_hint_x=0.15, adaptive_height=True)
        bump_btn   = MDButton(
            MDButtonIcon(icon="chevron-up"),
            MDButtonText(text=self._ctrl.get_bump_part(component)),
            size_hint_x=0.18,
        )
        bump_btn.bind(
            on_release=lambda btn, c=component: self._open_bump_menu(btn, c))
        commit_btn = MDButton(
            MDButtonIcon(icon="tag-check"),
            MDButtonText(text="Commit & Tag"),
            size_hint_x=0.16,
        )
        commit_btn.bind(
            on_release=lambda *_, c=component: self._on_commit_tag(c))

        self._version_rows[component] = {
            "local_lbl":  local_lbl,
            "remote_lbl": remote_lbl,
            "status_lbl": status_lbl,
            "bump_btn":   bump_btn,
            "commit_btn": commit_btn,
        }
        for w in (label, local_lbl, remote_lbl, status_lbl, bump_btn, commit_btn):
            row.add_widget(w)
        return row

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
            for child in row["bump_btn"].walk(restrict=True):
                if isinstance(child, MDButtonText):
                    child.text = part
                    break
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
                row["remote_lbl"].text = rem_ver or "—"
                slbl = row["status_lbl"]
                if local_ver and rem_ver:
                    if local_ver == rem_ver:
                        slbl.text = "✓ Current"
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
