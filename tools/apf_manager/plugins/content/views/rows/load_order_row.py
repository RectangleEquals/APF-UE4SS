"""LoadOrderHeaderRow and LoadOrderModRow — load-order tab row widgets."""
from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.button import MDIconButton

if TYPE_CHECKING:
    from ...controllers.mods.service import ModInfo


# Column widths shared between header and data rows
COL_REORDER = dp(100)
COL_STATUS  = dp(72)
COL_VERSION = dp(72)
COL_TOGGLE  = dp(52)

# Row background colours
ROW_BG_NORMAL   = (0.14, 0.14, 0.14, 1)
ROW_BG_WARN     = (0.22, 0.18, 0.08, 1)
ROW_BG_ERROR    = (0.22, 0.10, 0.10, 1)
ROW_BG_DISABLED = (0.10, 0.10, 0.10, 1)
ROW_BG_NONAP    = (0.11, 0.11, 0.11, 1)
ROW_BG_KEYBINDS = (0.08, 0.08, 0.08, 1)


class LoadOrderHeaderRow(MDBoxLayout):
    """Sticky header row showing column labels for the load-order list."""

    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(28),
            padding=[dp(4), 0],
            spacing=dp(4),
            md_bg_color=(0.12, 0.12, 0.12, 1),
            **kwargs,
        )

        def _col(text, width=None, halign="left"):
            kw = dict(
                text=text, font_style="Label", role="small",
                valign="middle", halign=halign,
                theme_text_color="Custom", text_color=(0.55, 0.55, 0.55, 1),
            )
            if width is not None:
                kw["size_hint"] = (None, 1)
                kw["width"] = width
            else:
                kw["size_hint"] = (1, 1)
            return MDLabel(**kw)

        self.add_widget(_col("Order",   width=COL_REORDER, halign="center"))
        self.add_widget(_col("Status",  width=COL_STATUS,  halign="center"))
        self.add_widget(_col("Mod Name"))
        self.add_widget(_col("Version", width=COL_VERSION, halign="right"))
        self.add_widget(_col("Enabled", width=COL_TOGGLE,  halign="center"))


class LoadOrderModRow(MDBoxLayout):
    """
    Single row in the load-order list.

    Parameters
    ----------
    mod            : ModInfo
    status         : str — "ok", "warn", "error"
    enabled        : bool
    on_toggle      : Callable[[ModInfo, bool], None]
    on_move_up     : Callable[[ModInfo], None]
    on_move_down   : Callable[[ModInfo], None]
    is_keybinds    : bool — when True renders a locked, non-movable Keybinds row
    install_record : InstallRecord | None — used for version display
    dep_label      : str — dependency error/warn text shown below mod name
    """

    def __init__(
        self,
        mod: "ModInfo",
        status: str,
        enabled: bool,
        on_toggle,
        on_move_up,
        on_move_down,
        is_keybinds: bool = False,
        install_record=None,
        dep_label: str = "",
        **kwargs,
    ):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(48),
            padding=[dp(4), dp(4)],
            spacing=dp(4),
            **kwargs,
        )
        self._mod = mod
        self._enabled = enabled
        self._is_keybinds = is_keybinds

        from .....gui.theme import STATUS_ICONS

        if is_keybinds:
            self.md_bg_color = ROW_BG_KEYBINDS
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=COL_REORDER))
            lock_box = AnchorLayout(
                anchor_x="center", anchor_y="center",
                size_hint=(None, 1), width=COL_STATUS,
            )
            lock_box.add_widget(MDIcon(
                icon="lock",
                theme_icon_color="Custom",
                icon_color=(0.4, 0.4, 0.4, 1),
            ))
            self.add_widget(lock_box)
            self.add_widget(MDLabel(
                text=mod.folder_name,
                font_style="Body",
                size_hint=(1, 1),
                halign="left",
                valign="middle",
                theme_text_color="Custom",
                text_color=(0.4, 0.4, 0.4, 1),
            ))
            self.add_widget(MDLabel(text="", size_hint=(None, 1), width=COL_VERSION))
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=COL_TOGGLE))
            return

        # Normal mod row
        is_orphaned = getattr(mod, "is_orphaned", False)
        if mod.is_ap_mod:
            self.md_bg_color = (
                ROW_BG_DISABLED if not enabled
                else ROW_BG_ERROR if status == "error"
                else ROW_BG_WARN if (status == "warn" or is_orphaned)
                else ROW_BG_NORMAL
            )
        else:
            self.md_bg_color = ROW_BG_NONAP

        # Column 1: Reorder buttons (AP mods only)
        if mod.is_ap_mod:
            reorder_box = MDBoxLayout(size_hint=(None, 1), width=COL_REORDER)
            reorder_box.add_widget(MDIconButton(
                icon="chevron-up",
                size_hint=(1, 1),
                on_release=lambda *_: on_move_up(mod),
            ))
            reorder_box.add_widget(MDIconButton(
                icon="chevron-down",
                size_hint=(1, 1),
                on_release=lambda *_: on_move_down(mod),
            ))
            self.add_widget(reorder_box)
        else:
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=COL_REORDER))

        # Column 2: Status badge
        icon_name, icon_color = STATUS_ICONS.get(status, STATUS_ICONS["unknown"])
        status_box = AnchorLayout(
            anchor_x="center", anchor_y="center",
            size_hint=(None, 1), width=COL_STATUS,
        )
        status_box.add_widget(MDIcon(
            icon=icon_name,
            theme_icon_color="Custom",
            icon_color=icon_color,
        ))
        self.add_widget(status_box)

        # Column 3: Name (with optional C++ badge and orphaned marker)
        name_box = MDBoxLayout(orientation="horizontal", size_hint=(1, 1), spacing=dp(4))
        components = getattr(mod, "components", ["lua"])
        if "cpp" in components:
            name_box.add_widget(MDIcon(
                icon="code-braces",
                size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=(0.4, 0.7, 1.0, 1),
            ))
        if is_orphaned:
            name_box.add_widget(MDIcon(
                icon="folder-account",
                size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=(0.85, 0.60, 0.15, 1),
            ))

        name_col = MDBoxLayout(orientation="vertical", size_hint=(1, 1))
        name_col.add_widget(MDLabel(
            text=mod.display_name,
            font_style="Body",
            size_hint=(1, None),
            height=dp(20),
            halign="left",
            valign="middle",
            theme_text_color="Custom" if not mod.is_ap_mod else "Primary",
            text_color=(0.5, 0.5, 0.5, 1) if not mod.is_ap_mod else (1, 1, 1, 0.87),
        ))
        if is_orphaned:
            name_col.add_widget(MDLabel(
                text="Manually installed",
                font_style="Label",
                role="small",
                size_hint=(1, None),
                height=dp(14),
                halign="left",
                valign="middle",
                theme_text_color="Custom",
                text_color=(0.85, 0.60, 0.15, 0.75),
            ))
        if dep_label:
            dep_color = (1.0, 0.35, 0.35, 1) if status == "error" else (0.9, 0.65, 0.1, 1)
            name_col.add_widget(MDLabel(
                text=dep_label,
                font_style="Label",
                role="small",
                size_hint=(1, None),
                height=dp(14),
                halign="left",
                valign="middle",
                theme_text_color="Custom",
                text_color=dep_color,
            ))
        name_box.add_widget(name_col)
        self.add_widget(name_box)

        # Column 4: Version (prefer InstallRecord, fall back to ModInfo)
        version = (install_record.version if install_record and install_record.version
                   else getattr(mod, "version", ""))
        self.add_widget(MDLabel(
            text=f"v{version}" if version else "",
            font_style="Label",
            role="small",
            size_hint=(None, 1),
            width=COL_VERSION,
            halign="right",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
            padding=[0, 0, dp(4), 0],
        ))

        # Column 5: Enable toggle (AP mods only)
        toggle_box = MDBoxLayout(size_hint=(None, 1), width=COL_TOGGLE)
        if mod.is_ap_mod:
            sw = MDSwitch(size_hint=(None, None), pos_hint={"center_x": 0.5, "center_y": 0.5})
            sw.active = enabled
            sw.bind(active=lambda inst, val, m=mod: on_toggle(m, val))
            toggle_box.add_widget(sw)
        self.add_widget(toggle_box)
