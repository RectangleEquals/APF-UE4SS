"""
Tab 5 — Load Order

Row behaviour:
  - Framework mod row: ▲▼ work normally. ▼ cascades adjacent AP mods down
    when a non-AP slot exists below; blocked when no non-AP mod is below the cluster.
  - Keybinds row: shown at absolute bottom when present in mods.txt; not movable.
  - Non-AP mod rows: dimmed text, freely reorderable.
  - BP-only mods (neither "lua" nor "cpp" in components) are excluded — no mods.txt entry.
  - Manually installed (orphaned) mods: shown with folder-account badge and _ROW_BG_WARN background.
  - C++ mods: "code-braces" badge. UE4SS guarantees C++ loads before Lua regardless of list position.
  - Auto-validate after every toggle: update row colors.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDSwitch

from .....core.views.widgets.tip_icon_button import TipIconButton
from ...controllers.mods.service import _SCAN_EXCLUDE, _FRAMEWORK_MOD_RE
from ..rows.load_order_row import LoadOrderHeaderRow, LoadOrderModRow

if TYPE_CHECKING:
    from ...controllers.mods.service import ModInfo
    from ...models.mods.config import ModsTextManager
    from .....core.models.config import GameProfile
    from .....core.models.ue4ss import UE4SSResult


class LoadOrderTab(MDBoxLayout):
    """Tab 6 — Load Order."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        from ...controllers.tabs.load_order.controller import LoadOrderController
        self._ctrl = LoadOrderController(host)
        self._profile: Optional["GameProfile"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._rows: list[LoadOrderModRow] = []
        self._show_all: bool = False
        self._build_ui()

    @property
    def _deploy_svc(self):
        return self._ctrl._deploy_svc()

    @property
    def _mods_txt(self) -> Optional["ModsTextManager"]:
        return self._ctrl.get_mods_txt()

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
            icon="sort",
            tooltip_text="Fix load order — sort by dependency constraints",
            on_release=lambda *_: self._fix_order(),
        ))
        toolbar.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Rescan mods",
            on_release=lambda *_: self._on_rescan(),
        ))
        self.add_widget(toolbar)

        # Tab subtitle
        self.add_widget(MDLabel(
            text=(
                "Adjust the load order of your AP mods. The framework mod must stay above all "
                "other AP mods — use the arrow buttons to reorder. Non-AP mods (greyed out) "
                "can be placed anywhere. Keybinds is always pinned at the bottom. "
                "Note: UE4SS always loads C++ mods before Lua regardless of their position here."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
            padding=[dp(12), dp(4)],
        ))

        # Sticky header
        self._header_row = LoadOrderHeaderRow()
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

    def get_error_count(self) -> int:
        """Return the number of rows with dependency errors (for badge coloring)."""
        if not self._rows:
            return 0
        if not (self._detection and getattr(self._detection, "valid", False)):
            return 0
        all_mods = self._ctrl.scan_mods()
        mod_by_id = {m.mod_id: m for m in all_mods if m.mod_id}
        return sum(
            1 for row in self._rows
            if self._ctrl.get_dep_info(row._mod, mod_by_id)[0] == "error"
        )

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

        all_mods = [m for m in self._ctrl.scan_mods() if m.folder_name not in _SCAN_EXCLUDE]

        def _has_mods_txt_entry(m) -> bool:
            """BP-only mods have no mods.txt entry and are excluded from Load Order."""
            components = getattr(m, "components", ["lua"])
            return "lua" in components or "cpp" in components

        if self._mods_txt:
            order = self._mods_txt.get_order()
            order_idx = {name: i for i, name in enumerate(order)}
            visible = [
                m for m in all_mods
                if (m.is_ap_mod or self._show_all)
                and m.folder_name.lower() != "keybinds"
                and _has_mods_txt_entry(m)
            ]
            visible.sort(key=lambda m: order_idx.get(m.folder_name, len(order)))
        else:
            visible = [
                m for m in all_mods
                if (m.is_ap_mod or self._show_all)
                and m.folder_name.lower() != "keybinds"
                and _has_mods_txt_entry(m)
            ]

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

        # Load install_map for version numbers
        install_map: dict = {}
        if self._profile:
            game_id = (getattr(self._profile, "game_id", None)
                       or getattr(self._profile, "name", ""))
            if game_id:
                from ...models.state.install import InstallStateManager
                from ...models.state.pipeline import InstallRecord
                install_map = {
                    d.get("folder_name", ""): InstallRecord.from_dict(d)
                    for d in InstallStateManager(game_id).get_all()
                    if d.get("folder_name")
                }

        for mod in visible:
            status, dep_label = self._ctrl.get_dep_info(mod, mod_by_id)

            enabled = True
            if self._mods_txt:
                if self._mods_txt.contains(mod.folder_name):
                    enabled = self._mods_txt.is_enabled(mod.folder_name)

            row = LoadOrderModRow(
                mod=mod,
                status=status,
                enabled=enabled,
                on_toggle=self._on_toggle,
                on_move_up=self._on_move_up,
                on_move_down=self._on_move_down,
                install_record=install_map.get(mod.folder_name),
                dep_label=dep_label,
            )
            self._rows.append(row)
            self._list_layout.add_widget(row)

        # Keybinds row — always at absolute bottom when present
        if self._mods_txt and self._mods_txt.has_footer:
            from pathlib import Path
            from ...controllers.mods.service import ModInfo
            keybinds_mod = ModInfo(folder_name="Keybinds", folder_path=Path("."))
            kb_row = LoadOrderModRow(
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
        self._ctrl.rescan_mods()
        svc = self._deploy_svc
        if svc:
            svc.reload()
        self._do_refresh()

    def _fix_order(self) -> None:
        """Sort AP mods in dependency order (framework first, then by dep graph)."""
        svc = self._deploy_svc
        if not svc or not self._rows:
            return

        ap_mods  = [r._mod for r in self._rows if r._mod.is_ap_mod]
        non_ap   = [r._mod for r in self._rows if not r._mod.is_ap_mod]
        id_to_folder = {m.mod_id: m.folder_name for m in ap_mods if m.mod_id}

        sorted_ap = self._ctrl.topo_sort_ap_mods(ap_mods, id_to_folder)

        # Rebuild displayed order: non-AP slots stay, AP slots filled in dep order
        new_mods: list = []
        ap_it = iter(sorted_ap)
        for r in self._rows:
            if r._mod.is_ap_mod:
                try:
                    new_mods.append(next(ap_it))
                except StopIteration:
                    break
            else:
                new_mods.append(r._mod)

        displayed_set = {r._mod.folder_name for r in self._rows}
        new_names = [m.folder_name for m in new_mods]
        full_order = svc.get_load_order()
        new_full: list[str] = []
        di = 0
        for name in full_order:
            if name in displayed_set:
                if di < len(new_names):
                    new_full.append(new_names[di])
                    di += 1
            else:
                new_full.append(name)
        while di < len(new_names):
            new_full.append(new_names[di])
            di += 1

        svc.reorder(new_full)
        self._do_refresh()

    def _on_toggle(self, mod: "ModInfo", enabled: bool) -> None:
        self._ctrl.set_enabled(mod.folder_name, enabled)
        # Auto-validate and refresh row colors
        self._do_refresh()

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

        if mod.mod_id and _FRAMEWORK_MOD_RE.match(mod.mod_id):
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
