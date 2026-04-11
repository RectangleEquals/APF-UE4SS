"""
Tab 5 — Install

Shows mods installed from registries (those with a manifest.json containing mod_id).
Per-row: status badge, enable/disable toggle, Uninstall button.
No "Deploy All" or reordering — that's the Load Order tab's job.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDSwitch

from ....gui.widgets.tip_icon_button import TipIconButton

if TYPE_CHECKING:
    from ....core.config import GameProfile
    from ....core.ue4ss import UE4SSResult


class InstallTab(MDBoxLayout):
    """Tab 5 — Install (manage and uninstall registry-installed mods)."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._build_ui()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1),
            padding=(dp(8), 0),
            spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Install",
            font_style="Title",
            role="medium",
            size_hint_x=1,
            halign="left",
        ))
        toolbar.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Rescan installed mods",
            on_release=lambda *_: self._do_refresh(),
        ))
        self.add_widget(toolbar)

        self.add_widget(MDLabel(
            text=(
                "Mods installed from your registries. "
                "Uninstalling removes them from your game directory."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
            padding=[dp(12), dp(4)],
        ))

        self._scroll = ScrollView(size_hint=(1, 1))
        self._list_layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(8), dp(4)],
        )
        self._scroll.add_widget(self._list_layout)
        self.add_widget(self._scroll)

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def refresh(self, profile: Optional["GameProfile"], detection) -> None:
        self._profile = profile
        self._detection = detection
        self._do_refresh()

    def _do_refresh(self) -> None:
        self._list_layout.clear_widgets()

        if not (self._detection and self._detection.valid):
            self._list_layout.add_widget(MDLabel(
                text=(
                    "UE4SS is required to manage installed mods.\n"
                    "Install UE4SS in the Registries tab first."
                ),
                halign="center",
                size_hint=(1, None),
                height=dp(80),
                theme_text_color="Secondary",
            ))
            return

        mods_svc = self._host.get_service("mods")
        all_mods = mods_svc.scan() if mods_svc else []
        # Show only registry-installed mods (have a mod_id from manifest.json)
        ap_mods = [m for m in all_mods if m.is_ap_mod]

        if not ap_mods:
            self._list_layout.add_widget(MDLabel(
                text=(
                    "No mods installed yet.\n"
                    "Stage mods in the Mods tab and install them from the Queue tab."
                ),
                halign="center",
                size_hint=(1, None),
                height=dp(80),
                theme_text_color="Secondary",
            ))
            return

        deploy_svc = self._host.get_service("deploy")
        mods_txt = deploy_svc.mods_txt if deploy_svc else None

        if mods_txt:
            order = mods_txt.get_order()
            order_idx = {name: i for i, name in enumerate(order)}
            ap_mods.sort(key=lambda m: order_idx.get(m.folder_name, len(order)))

        for mod in ap_mods:
            enabled = True
            if mods_txt and mods_txt.contains(mod.folder_name):
                enabled = mods_txt.is_enabled(mod.folder_name)
            self._list_layout.add_widget(
                self._build_mod_row(mod, enabled, deploy_svc)
            )

    def _build_mod_row(self, mod, enabled: bool, deploy_svc) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            padding=[dp(8), dp(4)],
            spacing=dp(8),
        )

        # Status icon
        status_icon = MDIcon(
            icon="check-circle" if enabled else "circle-off-outline",
            size_hint=(None, None),
            size=(dp(20), dp(20)),
            pos_hint={"center_y": 0.5},
            theme_icon_color="Custom",
            icon_color=(0.3, 0.8, 0.4, 1) if enabled else (0.5, 0.5, 0.5, 1),
        )
        row.add_widget(status_icon)

        # Name + mod_id
        info_col = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        info_col.add_widget(MDLabel(
            text=mod.display_name,
            font_style="Body",
            size_hint_y=None,
            height=dp(22),
        ))
        info_col.add_widget(MDLabel(
            text=mod.mod_id,
            font_style="Label",
            role="small",
            size_hint_y=None,
            height=dp(18),
            theme_text_color="Custom",
            text_color=(0.5, 0.5, 0.5, 1),
        ))
        row.add_widget(info_col)

        # Enable/disable toggle
        toggle = MDSwitch(size_hint=(None, None), size=(dp(36), dp(24)),
                          pos_hint={"center_y": 0.5})
        toggle.active = enabled
        toggle.bind(
            active=lambda inst, val, m=mod, svc=deploy_svc: self._on_toggle(m, val, svc)
        )
        row.add_widget(toggle)

        # Uninstall button
        row.add_widget(MDButton(
            MDButtonText(text="Uninstall"),
            style="text",
            size_hint=(None, None),
            size=(dp(88), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, m=mod: self._on_uninstall(m),
        ))

        return row

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_toggle(self, mod, enabled: bool, deploy_svc) -> None:
        if deploy_svc:
            deploy_svc.set_enabled(mod.folder_name, enabled)

    def _on_uninstall(self, mod) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        from kivymd.uix.button import MDButton, MDButtonText
        from kivy.uix.widget import Widget

        def _confirm(*_):
            dlg.dismiss()
            self._do_uninstall(mod)

        def _cancel(*_):
            dlg.dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text=f"Uninstall {mod.display_name}?"),
            MDDialogSupportingText(
                text=(
                    f"This will remove {mod.folder_name} from your game directory "
                    "and from mods.txt. This cannot be undone."
                )
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Uninstall"), style="filled",
                         on_release=_confirm),
            ),
        )
        dlg.open()

    def _do_uninstall(self, mod) -> None:
        import shutil
        from kivy.clock import Clock

        deploy_svc = self._host.get_service("deploy")
        mods_svc = self._host.get_service("mods")

        try:
            # Remove folder from game directory
            if mod.folder_path and mod.folder_path.exists():
                shutil.rmtree(mod.folder_path)

            # Remove from mods.txt
            if deploy_svc:
                deploy_svc.remove_entry(mod.folder_name)

            # Rescan
            if mods_svc:
                mods_svc.rescan()

            self._host.log(f"[install] Uninstalled {mod.display_name} ({mod.folder_name})")
        except Exception as exc:
            self._host.log(f"[install] [ERROR] Uninstall failed for {mod.folder_name}: {exc}")

        Clock.schedule_once(lambda dt: self._do_refresh(), 0)
