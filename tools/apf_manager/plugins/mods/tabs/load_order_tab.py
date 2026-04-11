"""
Tab 6 — Load Order

Current DeployPanel load order content minus Deploy All and Validate.
Calls DeployService / ModsTextManager with Bug A/B fixes applied.

Row behaviour:
  - Framework mod row: ▲▼ work normally.  ▼ cascades adjacent AP mods down
    when a non-AP slot exists below; blocked when no non-AP mod is below the cluster.
  - Keybinds row: shown at absolute bottom when present in mods.txt; not movable.
  - Non-AP mod rows: dimmed text, freely reorderable.
  - Enable/disable toggle for AP mods.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.button import MDIconButton

from ....gui.widgets.tip_icon_button import TipIconButton

if TYPE_CHECKING:
    from ...mods.mod_service import ModInfo
    from ...deploy.mods_txt import ModsTextManager
    from ....core.config import GameProfile
    from ....core.ue4ss import UE4SSResult

_SCAN_EXCLUDE = {"shared"}


def _mod_dep_status(mod, mod_by_id: dict, detection) -> str:
    """Return 'error', 'warn', or 'ok' based on manifest dependency checks."""
    for dep_str in mod.depends:
        dep_id = dep_str.split(" ")[0].strip()
        if dep_id not in mod_by_id:
            return "error"
    for incompat_id in mod.incompatible:
        if incompat_id in mod_by_id:
            return "error"
    for ext_name in mod.requires_external:
        folder = detection.mods_dir / ext_name if detection.mods_dir else None
        if not (folder and folder.is_dir()):
            return "warn"
    return "ok"

_ROW_BG_NORMAL   = (0.14, 0.14, 0.14, 1)
_ROW_BG_WARN     = (0.22, 0.18, 0.08, 1)
_ROW_BG_ERROR    = (0.22, 0.10, 0.10, 1)
_ROW_BG_DISABLED = (0.10, 0.10, 0.10, 1)
_ROW_BG_NONAP    = (0.11, 0.11, 0.11, 1)
_ROW_BG_KEYBINDS = (0.08, 0.08, 0.08, 1)

_COL_REORDER = dp(100)
_COL_STATUS  = dp(72)
_COL_VERSION = dp(72)
_COL_TOGGLE  = dp(52)


class _HeaderRow(MDBoxLayout):
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

        self.add_widget(_col("Order", width=_COL_REORDER, halign="center"))
        self.add_widget(_col("Status", width=_COL_STATUS, halign="center"))
        self.add_widget(_col("Mod Name"))
        self.add_widget(_col("Version", width=_COL_VERSION, halign="right"))
        self.add_widget(_col("Enabled", width=_COL_TOGGLE, halign="center"))


class _ModRow(MDBoxLayout):
    def __init__(
        self,
        mod: "ModInfo",
        status: str,
        enabled: bool,
        on_toggle,
        on_move_up,
        on_move_down,
        is_keybinds: bool = False,
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
        self.is_keybinds = is_keybinds

        from ....gui.theme import STATUS_ICONS

        if is_keybinds:
            self.md_bg_color = _ROW_BG_KEYBINDS
            # Keybinds row: spacer + lock icon + name — no buttons
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=_COL_REORDER))
            lock_box = AnchorLayout(
                anchor_x="center", anchor_y="center",
                size_hint=(None, 1), width=_COL_STATUS,
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
            self.add_widget(MDLabel(
                text="",
                size_hint=(None, 1),
                width=_COL_VERSION,
            ))
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=_COL_TOGGLE))
            return

        # Normal mod row
        if mod.is_ap_mod:
            self.md_bg_color = (
                _ROW_BG_DISABLED if not enabled
                else _ROW_BG_ERROR if status == "error"
                else _ROW_BG_WARN if status == "warn"
                else _ROW_BG_NORMAL
            )
        else:
            self.md_bg_color = _ROW_BG_NONAP

        # Column 1: Reorder buttons
        if mod.is_ap_mod:
            reorder_box = MDBoxLayout(size_hint=(None, 1), width=_COL_REORDER)
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
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=_COL_REORDER))

        # Column 2: Status badge
        icon_name, icon_color = STATUS_ICONS.get(status, STATUS_ICONS["unknown"])
        status_box = AnchorLayout(
            anchor_x="center", anchor_y="center",
            size_hint=(None, 1), width=_COL_STATUS,
        )
        status_box.add_widget(MDIcon(
            icon=icon_name,
            theme_icon_color="Custom",
            icon_color=icon_color,
        ))
        self.add_widget(status_box)

        # Column 3: Name
        self.add_widget(MDLabel(
            text=mod.display_name,
            font_style="Body",
            size_hint=(1, 1),
            halign="left",
            valign="middle",
            theme_text_color="Custom" if not mod.is_ap_mod else "Primary",
            text_color=(0.5, 0.5, 0.5, 1) if not mod.is_ap_mod else (1, 1, 1, 0.87),
        ))

        # Column 4: Version
        self.add_widget(MDLabel(
            text=f"v{mod.version}" if mod.version else "",
            font_style="Label",
            role="small",
            size_hint=(None, 1),
            width=_COL_VERSION,
            halign="right",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
            padding=[0, 0, dp(4), 0],
        ))

        # Column 6: Enable toggle
        toggle_box = MDBoxLayout(size_hint=(None, 1), width=_COL_TOGGLE)
        if mod.is_ap_mod:
            sw = MDSwitch(size_hint=(None, None), pos_hint={"center_x": 0.5, "center_y": 0.5})
            sw.active = enabled
            sw.bind(active=lambda inst, val, m=mod: on_toggle(m, val))
            toggle_box.add_widget(sw)
        self.add_widget(toggle_box)


class LoadOrderTab(MDBoxLayout):
    """Tab 6 — Load Order."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._rows: list[_ModRow] = []
        self._show_all: bool = False
        self._build_ui()

    @property
    def _deploy_svc(self):
        return self._host.get_service("deploy")

    @property
    def _mods_txt(self) -> Optional["ModsTextManager"]:
        svc = self._deploy_svc
        return svc.mods_txt if svc else None

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1),
            padding=(dp(8), 0),
            spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Load Order",
            font_style="Title",
            role="medium",
            size_hint_x=1,
            halign="left",
        ))
        toolbar.add_widget(MDLabel(
            text="Show All",
            size_hint=(None, 1),
            width=dp(64),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        ))
        self._show_all_switch = MDSwitch(size_hint=(None, None), pos_hint={"center_y": 0.5})
        self._show_all_switch.active = False
        self._show_all_switch.bind(active=lambda inst, val: self._on_show_all(val))
        toolbar.add_widget(self._show_all_switch)
        toolbar.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Rescan mods",
            on_release=lambda *_: self._on_rescan(),
        ))
        self.add_widget(toolbar)

        # Tab subtitle
        self.add_widget(MDLabel(
            text=(
                "Adjust the load order of your mods. The AP framework mod must stay above all "
                "other AP mods — use the arrow buttons to reorder. Non-AP mods (greyed out) "
                "can be placed anywhere. Keybinds is always pinned at the bottom."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
            padding=[dp(12), dp(4)],
        ))

        # Sticky header
        self._header_row = _HeaderRow()
        self._header_row.opacity = 0
        self.add_widget(self._header_row)

        # Scrollable list
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
        self._rows = []

        if not (self._detection and self._detection.valid):
            self._header_row.opacity = 0
            self._list_layout.add_widget(MDLabel(
                text="UE4SS is required to manage load order.\nInstall UE4SS in the Registries tab first.",
                halign="center",
                size_hint=(1, None),
                height=dp(80),
                theme_text_color="Secondary",
            ))
            return

        mods_svc = self._host.get_service("mods")
        all_mods = mods_svc.scan() if mods_svc else []
        all_mods = [m for m in all_mods if m.folder_name not in _SCAN_EXCLUDE]

        if self._mods_txt:
            order = self._mods_txt.get_order()
            order_idx = {name: i for i, name in enumerate(order)}
            visible = [m for m in all_mods if (m.is_ap_mod or self._show_all)
                       and m.folder_name.lower() != "keybinds"]
            visible.sort(key=lambda m: order_idx.get(m.folder_name, len(order)))
        else:
            visible = [m for m in all_mods if (m.is_ap_mod or self._show_all)
                       and m.folder_name.lower() != "keybinds"]

        if not visible and not (self._mods_txt and self._mods_txt.has_footer):
            self._header_row.opacity = 0
            self._list_layout.add_widget(MDLabel(
                text=(
                    "No mods found in the game directory.\n"
                    "Install mods from the Queue tab, then deploy them to manage load order here."
                ),
                halign="center",
                size_hint=(1, None),
                adaptive_height=True,
                height=dp(80),
            ))
            return

        self._header_row.opacity = 1

        mod_by_id = {m.mod_id: m for m in all_mods if m.mod_id}

        for mod in visible:
            status = _mod_dep_status(mod, mod_by_id, self._detection)

            enabled = True
            if self._mods_txt:
                if self._mods_txt.contains(mod.folder_name):
                    enabled = self._mods_txt.is_enabled(mod.folder_name)

            row = _ModRow(
                mod=mod,
                status=status,
                enabled=enabled,
                on_toggle=self._on_toggle,
                on_move_up=self._on_move_up,
                on_move_down=self._on_move_down,
            )
            self._rows.append(row)
            self._list_layout.add_widget(row)

        # Keybinds row — always at absolute bottom when present
        if self._mods_txt and self._mods_txt.has_footer:
            from ...mods.mod_service import ModInfo
            from pathlib import Path
            keybinds_mod = ModInfo(folder_name="Keybinds", folder_path=Path("."))
            kb_row = _ModRow(
                mod=keybinds_mod,
                status="ok",
                enabled=True,
                on_toggle=lambda *_: None,
                on_move_up=lambda *_: None,
                on_move_down=lambda *_: None,
                is_keybinds=True,
            )
            self._list_layout.add_widget(kb_row)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_show_all(self, val: bool) -> None:
        self._show_all = val
        self._do_refresh()

    def _on_rescan(self) -> None:
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            mods_svc.rescan()
        svc = self._deploy_svc
        if svc:
            svc.reload()
        self._do_refresh()

    def _on_toggle(self, mod: "ModInfo", enabled: bool) -> None:
        svc = self._deploy_svc
        if svc:
            svc.set_enabled(mod.folder_name, enabled)

    def _on_move_up(self, mod: "ModInfo") -> None:
        idx = next(
            (i for i, r in enumerate(self._rows) if r._mod.folder_name == mod.folder_name),
            None,
        )
        if idx is None or idx == 0:
            return
        self._swap_displayed(idx, idx - 1)

    def _on_move_down(self, mod: "ModInfo") -> None:
        idx = next(
            (i for i, r in enumerate(self._rows) if r._mod.folder_name == mod.folder_name),
            None,
        )
        if idx is None or idx >= len(self._rows) - 1:
            return

        if mod.mod_id and mod.mod_id.endswith(".framework"):
            self._cascade_framework_down(idx)
        else:
            self._swap_displayed(idx, idx + 1)

    def _cascade_framework_down(self, fw_idx: int) -> None:
        """
        Move the framework mod down one non-AP slot, cascading adjacent AP mods.

        Finds all directly adjacent AP mod rows below the framework mod, then
        finds the next non-AP row below the cluster.  That non-AP row bubbles
        up to just above the framework mod (the whole cluster shifts down by 1).
        Blocked when no non-AP row exists below the cluster.
        """
        rows = self._rows

        # Find the end of the adjacent-AP cluster below the framework mod
        cluster_end = fw_idx + 1
        while cluster_end < len(rows) and rows[cluster_end]._mod.is_ap_mod:
            cluster_end += 1

        if cluster_end >= len(rows):
            return  # No non-AP mod below — blocked

        # Bubble the non-AP row up to just before the framework mod
        non_ap_row = rows[cluster_end]
        new_rows = (
            rows[:fw_idx]
            + [non_ap_row]
            + rows[fw_idx:cluster_end]
            + rows[cluster_end + 1:]
        )

        svc = self._deploy_svc
        if not svc:
            return

        new_names = [r._mod.folder_name for r in new_rows]
        displayed_set = {r._mod.folder_name for r in self._rows}

        full_order = svc.get_load_order()
        new_full: list[str] = []
        di = 0
        for name in full_order:
            if name in displayed_set:
                new_full.append(new_names[di])
                di += 1
            else:
                new_full.append(name)
        while di < len(new_names):
            new_full.append(new_names[di])
            di += 1

        svc.reorder(new_full)
        self._do_refresh()

    def _swap_displayed(self, i: int, j: int) -> None:
        """Swap rows[i] and rows[j], rebuild mods.txt order."""
        svc = self._deploy_svc
        if not svc:
            return

        rows = self._rows[:]
        rows[i], rows[j] = rows[j], rows[i]
        new_names = [r._mod.folder_name for r in rows]
        displayed_set = {r._mod.folder_name for r in self._rows}

        full_order = svc.get_load_order()
        new_full: list[str] = []
        di = 0
        for name in full_order:
            if name in displayed_set:
                new_full.append(new_names[di])
                di += 1
            else:
                new_full.append(name)
        while di < len(new_names):
            new_full.append(new_names[di])
            di += 1

        svc.reorder(new_full)
        self._do_refresh()

