"""
APF Manager — Draggable mod list widget with load-order constraints and color coding.

Row colors:
  Normal    — enabled AP mod, no issues
  Yellow    — warning (dep ordering violation, incompatible mods both enabled, prefers_after)
  Red       — error (hard dep missing/uninstalled entirely)
  Grey      — disabled mod (': 0' in mods.txt)
  Dimmed    — non-AP mod (shown for context, uninteractable)

Hard constraints (drag rejected):
  - APFrameworkMod must remain first among all AP mods
  - (All other issues are warnings only)
"""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ListProperty, ObjectProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDIconButton, MDFlatButton
from kivymd.uix.tooltip import MDTooltip
from kivymd.uix.card import MDCard

from ...discovery import ModInfo
from ...load_order import ModsEntry, FRAMEWORK_MOD

# Color palette (RGBA)
_COLOR_NORMAL = (0.97, 0.97, 0.97, 1)
_COLOR_WARNING = (1.0, 0.95, 0.7, 1)
_COLOR_ERROR = (1.0, 0.85, 0.85, 1)
_COLOR_DISABLED = (0.85, 0.85, 0.85, 1)
_COLOR_NON_AP = (0.92, 0.92, 0.92, 0.7)


class ModRowButton(MDFlatButton, MDTooltip):
    """A flat button with tooltip support — used for manual_steps 'button' items."""
    tooltip_text = StringProperty("")


class ModRow(MDCard):
    """
    A single row in the mod list.
    Shows mod name, version, status, warning/error icons, and drag handle.
    """

    mod_name = StringProperty("")
    display_name = StringProperty("")
    version_text = StringProperty("")
    status_text = StringProperty("")
    is_ap_mod = BooleanProperty(True)
    is_core = BooleanProperty(False)
    is_enabled = BooleanProperty(True)
    row_state = StringProperty("normal")  # "normal" | "warning" | "error" | "disabled" | "non_ap"
    warnings = ListProperty([])
    on_toggle = ObjectProperty(None, allownone=True)
    on_drag_start = ObjectProperty(None, allownone=True)

    def __init__(self, entry: ModsEntry | None, mod_info: ModInfo | None, **kwargs):
        super().__init__(**kwargs)
        self.entry = entry
        self.mod_info = mod_info
        self.size_hint_y = None
        self.height = "56dp"
        self.padding = "8dp"
        self.spacing = "8dp"
        self.elevation = 1
        self._build()

    def _build(self):
        self.orientation = "horizontal"

        # Drag handle (only for draggable AP mods)
        if self.is_ap_mod and not self.is_core:
            drag_handle = MDIconButton(
                icon="drag",
                size_hint=(None, None),
                size=("32dp", "32dp"),
                theme_icon_color="Secondary",
            )
            drag_handle.bind(on_touch_down=self._on_drag_touch)
            self.add_widget(drag_handle)
        else:
            spacer = BoxLayout(size_hint=(None, None), size=("32dp", "32dp"))
            self.add_widget(spacer)

        # Checkbox (enabled/disabled toggle)
        from kivymd.uix.selectioncontrol import MDCheckbox
        self._checkbox = MDCheckbox(
            active=self.is_enabled,
            size_hint=(None, None),
            size=("32dp", "32dp"),
            disabled=not self.is_ap_mod or self.is_core,
        )
        self._checkbox.bind(active=self._on_checkbox)
        self.add_widget(self._checkbox)

        # Main label area
        label_box = BoxLayout(orientation="vertical")
        self._name_label = MDLabel(
            text=self.display_name or self.mod_name,
            font_style="Subtitle2",
            theme_text_color="Primary" if self.is_ap_mod else "Secondary",
        )
        self._sub_label = MDLabel(
            text=self._sub_text(),
            font_style="Caption",
            theme_text_color="Secondary",
            size_hint_y=None,
            height="16dp",
        )
        label_box.add_widget(self._name_label)
        label_box.add_widget(self._sub_label)
        self.add_widget(label_box)

        # Warning/error icon
        self._status_icon = MDIconButton(
            icon="check-circle-outline",
            theme_icon_color="Custom",
            icon_color=(0.2, 0.7, 0.2, 1),
            size_hint=(None, None),
            size=("32dp", "32dp"),
        )
        self.add_widget(self._status_icon)

        # Manual step buttons (from manual_steps with when='button')
        if self.mod_info:
            for step in self.mod_info.manual_steps:
                if step.get("when") == "button":
                    btn = ModRowButton(
                        text=step.get("caption", "Info"),
                        size_hint=(None, None),
                        width="80dp",
                        height="36dp",
                        tooltip_text=step.get("title", ""),
                    )
                    btn._step = step
                    btn.bind(on_release=lambda b, s=step: self._show_step_dialog(s))
                    self.add_widget(btn)

        self._apply_state()

    def _sub_text(self) -> str:
        parts = []
        if self.mod_info:
            parts.append(f"v{self.mod_info.version}")
        if self.status_text:
            parts.append(self.status_text)
        return "  |  ".join(parts) if parts else ""

    def _apply_state(self):
        colors = {
            "normal": _COLOR_NORMAL,
            "warning": _COLOR_WARNING,
            "error": _COLOR_ERROR,
            "disabled": _COLOR_DISABLED,
            "non_ap": _COLOR_NON_AP,
        }
        self.md_bg_color = colors.get(self.row_state, _COLOR_NORMAL)

        if self.row_state == "warning":
            self._status_icon.icon = "alert-circle-outline"
            self._status_icon.icon_color = (0.9, 0.7, 0.0, 1)
        elif self.row_state == "error":
            self._status_icon.icon = "close-circle-outline"
            self._status_icon.icon_color = (0.8, 0.2, 0.2, 1)
        else:
            self._status_icon.icon = "check-circle-outline"
            self._status_icon.icon_color = (0.2, 0.7, 0.2, 1) if self.is_ap_mod else (0.7, 0.7, 0.7, 1)

    def set_warnings(self, warnings: list[str], errors: list[str]):
        self.warnings = warnings
        if errors:
            self.row_state = "error"
        elif warnings:
            self.row_state = "warning"
        elif not self.is_enabled:
            self.row_state = "disabled"
        elif not self.is_ap_mod:
            self.row_state = "non_ap"
        else:
            self.row_state = "normal"
        self._apply_state()
        # Update tooltip on status icon
        all_msgs = errors + warnings
        if all_msgs:
            self._status_icon.tooltip_text = "\n".join(all_msgs)

    def _on_checkbox(self, instance, value):
        self.is_enabled = value
        if not value:
            self.row_state = "disabled"
        else:
            self.row_state = "normal"
        self._apply_state()
        if self.on_toggle:
            self.on_toggle(self.mod_name, value)

    def _on_drag_touch(self, instance, touch):
        if instance.collide_point(*touch.pos) and self.on_drag_start:
            self.on_drag_start(self)

    def _show_step_dialog(self, step: dict):
        from ..dialogs import show_step_dialog
        show_step_dialog(step, self.app.config_data.source_project)


class ModList(MDBoxLayout):
    """
    Vertical list of ModRow widgets with drag-and-drop reordering.
    Enforces APFrameworkMod-first constraint; all other violations emit warnings.
    """

    def __init__(self, app, **kwargs):
        super().__init__(orientation="vertical", spacing="4dp", padding="8dp",
                         size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.app = app
        self._rows: list[ModRow] = []
        self._drag_row: ModRow | None = None

    def populate(self, entries: list[ModsEntry], mod_infos: dict[str, ModInfo],
                 installed: set[str]) -> None:
        """Rebuild the list from current mods.txt entries."""
        self.clear_widgets()
        self._rows.clear()

        for entry in entries:
            mod_info = mod_infos.get(entry.name)
            row = ModRow(
                entry=entry,
                mod_info=mod_info,
                mod_name=entry.name,
                display_name=(mod_info.display_name if mod_info else entry.name),
                is_ap_mod=entry.is_ap_mod,
                is_core=(entry.name == FRAMEWORK_MOD),
                is_enabled=entry.enabled,
            )
            row.on_drag_start = self._begin_drag
            row.on_toggle = self._on_toggle
            self._rows.append(row)
            self.add_widget(row)

        self._recompute_warnings()

    def _recompute_warnings(self):
        """Check load order constraints and annotate rows with warnings/errors."""
        from ...discovery import ModDiscovery, _parse_dep_mod_id

        ap_order = [r.mod_name for r in self._rows if r.is_ap_mod]
        ap_set = set(ap_order)

        discovery: ModDiscovery = self.app.discovery
        mod_infos_by_folder = {m.folder_name: m for m in discovery.discover()}
        mod_infos_by_id = {m.mod_id: m for m in discovery.discover() if m.mod_id}

        for row in self._rows:
            if not row.is_ap_mod:
                row.set_warnings([], [])
                continue

            warnings: list[str] = []
            errors: list[str] = []
            mod_info = mod_infos_by_folder.get(row.mod_name)
            my_pos = ap_order.index(row.mod_name) if row.mod_name in ap_order else -1

            if mod_info:
                # Check 'depends' — hard deps must appear before this mod in ap_order
                for dep_str in mod_info.depends:
                    dep_id = _parse_dep_mod_id(dep_str)
                    dep_info = mod_infos_by_id.get(dep_id)
                    dep_folder = dep_info.folder_name if dep_info else None
                    if dep_folder:
                        if dep_folder not in ap_set:
                            errors.append(f"Required mod '{dep_folder}' is not installed")
                        elif ap_order.index(dep_folder) > my_pos:
                            warnings.append(f"'{dep_folder}' should load before this mod")
                    # else: external dep — not our concern here

                # Check 'incompatible'
                for inc_str in mod_info.incompatible:
                    inc_id = _parse_dep_mod_id(inc_str)
                    inc_info = mod_infos_by_id.get(inc_id)
                    inc_folder = inc_info.folder_name if inc_info else None
                    if inc_folder and inc_folder in ap_set:
                        warnings.append(f"Incompatible with '{inc_folder}'")

                # Check 'prefers_after'
                for pref_folder in mod_info.prefers_after:
                    if pref_folder in ap_set and ap_order.index(pref_folder) > my_pos:
                        warnings.append(f"Prefers loading after '{pref_folder}'")

            row.set_warnings(warnings, errors)

    def _begin_drag(self, row: ModRow):
        self._drag_row = row

    def move_row(self, from_name: str, to_name: str) -> bool:
        """
        Move from_name to just before to_name in the AP mod order.
        Returns False if the move violates a hard constraint.
        """
        ap_rows = [r for r in self._rows if r.is_ap_mod]
        names = [r.mod_name for r in ap_rows]
        if from_name not in names or to_name not in names:
            return False

        # Hard constraint: APFrameworkMod cannot be moved below anything
        if from_name == FRAMEWORK_MOD:
            return False
        # Hard constraint: nothing can be moved above APFrameworkMod
        to_pos = names.index(to_name)
        if to_pos == 0 and names[0] == FRAMEWORK_MOD:
            return False

        # Apply move
        names.remove(from_name)
        new_to_pos = names.index(to_name) if to_name in names else len(names)
        names.insert(new_to_pos, from_name)

        # Write new order to mods.txt
        detection = self.app.detection
        if detection and detection.mods_txt.exists():
            from ...load_order import ModsTextManager
            mgr = ModsTextManager()
            mgr.reorder(detection.mods_txt, names, self.app.discovery.known_ap_mod_names())

        # Rebuild display
        self._reorder_display(names)
        self._recompute_warnings()
        return True

    def _reorder_display(self, ap_order: list[str]):
        """Reorder the row widgets to match the given AP mod order."""
        # Separate AP and non-AP rows
        ap_by_name = {r.mod_name: r for r in self._rows if r.is_ap_mod}
        non_ap_rows = [r for r in self._rows if not r.is_ap_mod]

        # Build new rows list: non-AP rows stay, AP rows reordered
        new_rows: list[ModRow] = []
        ap_iter = iter(ap_order)
        for row in self._rows:
            if row.is_ap_mod:
                name = next(ap_iter, None)
                if name and name in ap_by_name:
                    new_rows.append(ap_by_name[name])
            else:
                new_rows.append(row)

        self._rows = new_rows
        self.clear_widgets()
        for r in self._rows:
            self.add_widget(r)

    def _on_toggle(self, mod_name: str, enabled: bool):
        """Write the enabled/disabled state change to mods.txt."""
        detection = self.app.detection
        if not detection or not detection.mods_txt.exists():
            return
        from ...load_order import ModsTextManager
        mgr = ModsTextManager()
        known = self.app.discovery.known_ap_mod_names()
        body, footer = mgr.parse(detection.mods_txt, known)
        for item in body:
            from ...load_order import ModsEntry as ME
            if isinstance(item, ME) and item.name == mod_name:
                item.enabled = enabled
                break
        mgr.write(detection.mods_txt, body, footer)
        self._recompute_warnings()
