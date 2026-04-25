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
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.button import MDIconButton

from ......gui.widgets.tip_icon_button import TipIconButton
from ....services.mod_service import _SCAN_EXCLUDE, _FRAMEWORK_MOD_RE

if TYPE_CHECKING:
    from ....services.mod_service import ModInfo
    from ....utils.mods_txt import ModsTextManager
    from ......core.config import GameProfile
    from ......core.ue4ss import UE4SSResult


def _get_dep_info(mod, mod_by_id: dict) -> tuple:
    """Return (status, label) — status is 'error', 'warn', or 'ok'."""
    missing, incompat = [], []
    for dep_str in (getattr(mod, "depends", None) or []):
        dep_id = dep_str.split(" ")[0].strip()
        if dep_id not in mod_by_id:
            short = dep_id.split(".")[-1] if "." in dep_id else dep_id
            missing.append(short)
    for dep_str in (getattr(mod, "incompatible", None) or []):
        dep_id = dep_str.split(" ")[0].strip()
        if dep_id in mod_by_id:
            short = dep_id.split(".")[-1] if "." in dep_id else dep_id
            incompat.append(short)
    if missing:
        return "error", f"Missing: {', '.join(missing)}"
    if incompat:
        return "error", f"Conflicts: {', '.join(incompat)}"
    return "ok", ""


def _topo_sort_ap_mods(ap_mods: list, id_to_folder: dict) -> list:
    """Topological sort: framework first, then other AP mods in dependency order."""
    from ....services.mod_service import _FRAMEWORK_MOD_RE
    fw   = [m for m in ap_mods if m.mod_id and _FRAMEWORK_MOD_RE.match(m.mod_id)]
    rest = [m for m in ap_mods if m not in fw]

    folder_deps: dict = {}
    for m in rest:
        deps: set = set()
        for dep_str in (getattr(m, "depends", None) or []):
            dep_id = dep_str.split(" ")[0].strip()
            df = id_to_folder.get(dep_id)
            if df:
                deps.add(df)
        folder_deps[m.folder_name] = deps

    resolved: set = {m.folder_name for m in fw}
    result   = list(fw)
    remaining = list(rest)

    for _ in range(len(rest) + 1):
        if not remaining:
            break
        for mod in list(remaining):
            if folder_deps[mod.folder_name].issubset(resolved):
                result.append(mod)
                resolved.add(mod.folder_name)
                remaining.remove(mod)
                break
        else:
            result.extend(remaining)
            break
    return result

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
        self.is_keybinds = is_keybinds

        from ......gui.theme import STATUS_ICONS

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
        is_orphaned = getattr(mod, "is_orphaned", False)
        if mod.is_ap_mod:
            self.md_bg_color = (
                _ROW_BG_DISABLED if not enabled
                else _ROW_BG_ERROR if status == "error"
                else _ROW_BG_WARN if (status == "warn" or is_orphaned)
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

        # Column 3: Name (with optional C++ badge and orphaned marker)
        name_box = MDBoxLayout(
            orientation="horizontal", size_hint=(1, 1), spacing=dp(4),
        )
        components = getattr(mod, "components", ["lua"])
        if "cpp" in components:
            name_box.add_widget(MDIcon(
                icon="code-braces",
                size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=(0.4, 0.7, 1.0, 1),
            ))

        is_orphaned = getattr(mod, "is_orphaned", False)
        if is_orphaned:
            name_box.add_widget(MDIcon(
                icon="folder-account",
                size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=(0.85, 0.60, 0.15, 1),
            ))

        # Name + optional sub-labels stacked vertically
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

    def get_error_count(self) -> int:
        """Return the number of rows with dependency errors (for badge coloring)."""
        if not self._rows:
            return 0
        mods_svc = self._host.get_service("mods")
        if not mods_svc or not (self._detection and getattr(self._detection, "valid", False)):
            return 0
        mod_by_id = {m.mod_id: m for m in mods_svc.scan() if m.mod_id}
        return sum(
            1 for row in self._rows
            if _get_dep_info(row._mod, mod_by_id)[0] == "error"
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

        mods_svc = self._host.get_service("mods")
        all_mods = mods_svc.scan() if mods_svc else []
        all_mods = [m for m in all_mods if m.folder_name not in _SCAN_EXCLUDE]

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
                from ....shared.data.install_state import InstallStateManager
                from ....shared.data.pipeline_state import InstallRecord
                install_map = {
                    d.get("folder_name", ""): InstallRecord.from_dict(d)
                    for d in InstallStateManager(game_id).get_all()
                    if d.get("folder_name")
                }

        for mod in visible:
            status, dep_label = _get_dep_info(mod, mod_by_id)

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
                install_record=install_map.get(mod.folder_name),
                dep_label=dep_label,
            )
            self._rows.append(row)
            self._list_layout.add_widget(row)

        # Keybinds row — always at absolute bottom when present
        if self._mods_txt and self._mods_txt.has_footer:
            from pathlib import Path
            from ....services.mod_service import ModInfo
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

    def _fix_order(self) -> None:
        """Sort AP mods in dependency order (framework first, then by dep graph)."""
        svc = self._deploy_svc
        if not svc or not self._rows:
            return

        ap_mods  = [r._mod for r in self._rows if r._mod.is_ap_mod]
        non_ap   = [r._mod for r in self._rows if not r._mod.is_ap_mod]
        id_to_folder = {m.mod_id: m.folder_name for m in ap_mods if m.mod_id}

        sorted_ap = _topo_sort_ap_mods(ap_mods, id_to_folder)

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
        svc = self._deploy_svc
        if svc:
            svc.set_enabled(mod.folder_name, enabled)
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

