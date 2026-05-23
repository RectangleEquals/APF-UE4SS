"""
APConfigPanel — hub_panel for editing framework_config.json.

Sections (collapsible):
    AP Server   — host, port, slot_name, password, auto_reconnect  [expanded]
    Logging     — level (dropdown), file, console, append           [expanded]
    Timeouts    — connection/registration/ipc/action + retry        [collapsed]
    Threading   — polling interval, queue size, shutdown timeout    [collapsed]

Dependency guard:
    Requires BOTH UE4SS and the AP Framework Mod.
    Subscribes to both "detection" and "install" state changes.
    Shows a full-screen guard view when either dependency is missing;
    live-swaps to the config form when both are present.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from ....core.views.widgets.tip_icon_button import TipIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.textfield import MDTextField

from ....core.views.widgets.plugin_panel import PluginPanel
from ..controllers.controller import APConfigController

if TYPE_CHECKING:
    from ....core.models.config import GameProfile


_LOG_LEVELS = ["trace", "debug", "info", "warn", "error", "fatal"]


class _ClickableRow(ButtonBehavior, MDBoxLayout):
    """Full-width clickable row that delegates release to _toggle()."""
    pass


class _CollapsibleSection(MDBoxLayout):
    """Header row that toggles visibility of a content MDBoxLayout."""

    def __init__(self, title: str, content: MDBoxLayout, collapsed: bool = False, **kwargs):
        super().__init__(orientation="vertical", size_hint=(1, None), height=dp(40), **kwargs)
        self._collapsed = collapsed

        header = _ClickableRow(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(40),
            md_bg_color=(0.1, 0.14, 0.18, 1),
            padding=(dp(4), 0),
            spacing=dp(4),
            on_release=lambda *_: self._toggle(),
        )
        self._chevron = MDIconButton(
            icon="chevron-right" if collapsed else "chevron-down",
            size_hint_x=None,
            width=dp(32),
        )
        header.add_widget(self._chevron)
        header.add_widget(MDLabel(
            text=title,
            font_style="Title",
            role="large",
            theme_text_color="Custom",
            text_color=(0.55, 0.75, 0.95, 1),
            size_hint_x=1,
        ))
        self.add_widget(header)

        self._content = content
        content.size_hint_y = None
        content.fbind("minimum_height", self._on_content_height)
        self.add_widget(content)

        if collapsed:
            Clock.schedule_once(lambda dt: self._apply_state(), 0)

    def _on_content_height(self, content, min_h):
        if not self._collapsed:
            content.height = min_h
            self.height = dp(40) + min_h

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._apply_state()

    def _apply_state(self):
        if self._collapsed:
            self._content.opacity = 0
            self._content.height = 0
            self.height = dp(40)
            self._chevron.icon = "chevron-right"
        else:
            self._content.opacity = 1
            self._content.height = self._content.minimum_height
            self.height = dp(40) + self._content.minimum_height
            self._chevron.icon = "chevron-down"


class _Row(MDBoxLayout):
    """Label + input field row."""
    def __init__(self, label: str, widget, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(64),
            spacing=dp(8),
            padding=[dp(4), 0],
            **kwargs,
        )
        self.add_widget(MDLabel(
            text=label,
            size_hint=(0.4, 1),
            halign="right",
            valign="middle",
        ))
        self.add_widget(widget)


class APConfigPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._ctrl = APConfigController(host)
        self._profile: Optional["GameProfile"] = None
        # Form state
        self._fields: dict[str, MDTextField] = {}
        self._checks: dict[str, MDSwitch] = {}
        self._menus: dict[str, MDDropdownMenu] = {}
        self._dirty: bool = False
        self._dirty_bound: bool = False
        self._form_built: bool = False
        # Dialog / nav state
        self._unsaved_dialog: Optional[MDDialog] = None
        self._pending_nav_label: Optional[str] = None
        # Subscription guard
        self._subscribed: bool = False
        self._build_chrome()

    # -----------------------------------------------------------------------
    # Chrome build (always-visible toolbar + dynamic body container)
    # -----------------------------------------------------------------------

    def _build_chrome(self) -> None:
        self.orientation = "vertical"

        toolbar = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(56),
            md_bg_color=(0.15, 0.2, 0.25, 1), padding=(dp(8), 0), spacing=dp(4),
        )
        title_box = MDBoxLayout(orientation="vertical", size_hint_x=1, spacing=0,
                                padding=(0, dp(4), 0, dp(4)))
        title_box.add_widget(MDLabel(
            text="Configure", font_style="Title", role="large",
            size_hint_y=None, height=dp(28), halign="left",
        ))
        self._mod_subtitle = MDLabel(
            text="", font_style="Body", role="small",
            size_hint_y=None, height=dp(16), halign="left",
            theme_text_color="Secondary",
        )
        title_box.add_widget(self._mod_subtitle)
        toolbar.add_widget(title_box)

        self._save_btn = TipIconButton(
            icon="content-save", tooltip_text="Save config",
            on_release=lambda *_: self._on_save(),
        )
        self._reload_btn = TipIconButton(
            icon="refresh", tooltip_text="Reload from disk",
            on_release=lambda *_: self._on_reload(),
        )
        toolbar.add_widget(self._save_btn)
        toolbar.add_widget(self._reload_btn)
        self.add_widget(toolbar)

        # Dynamic body: swapped between guard view and content view
        self._body = MDBoxLayout(orientation="vertical", size_hint=(1, 1))
        self.add_widget(self._body)

    # -----------------------------------------------------------------------
    # Lazy form build (only when first showing content view)
    # -----------------------------------------------------------------------

    def _ensure_form_built(self) -> None:
        if self._form_built:
            return
        self._form_built = True

        self._form_scroll = ScrollView(size_hint=(1, 1))
        form = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            padding=[dp(16), dp(8)],
            spacing=dp(4),
        )
        self._form_scroll.add_widget(form)
        self._form = form

        self._status_label = MDLabel(
            text="",
            size_hint=(1, None),
            height=dp(32),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
        )

        self._build_form()

    def _mk_field(self, key: str, hint: str = "", input_filter: str = "") -> MDTextField:
        kw = dict(hint_text=hint, mode="outlined", size_hint=(0.6, 1))
        if input_filter:
            kw["input_filter"] = input_filter
        f = MDTextField(**kw)
        self._fields[key] = f
        return f

    def _mk_check(self, key: str) -> MDSwitch:
        sw = MDSwitch(size_hint=(None, None), pos_hint={"center_y": 0.5})
        self._checks[key] = sw
        return sw

    def _mk_dropdown(self, key: str, items: list, hint: str = "") -> MDTextField:
        field = MDTextField(hint_text=hint, mode="outlined", size_hint=(0.6, 1))
        self._fields[key] = field
        menu_items = [
            {"text": v, "on_release": lambda x=v, k=key: self._on_dropdown_select(k, x)}
            for v in items
        ]
        menu = MDDropdownMenu(caller=field, items=menu_items, width_mult=3)
        self._menus[key] = menu
        field.bind(on_touch_down=lambda w, t: menu.open() if w.collide_point(*t.pos) else None)
        return field

    def _on_dropdown_select(self, key: str, value: str) -> None:
        self._fields[key].text = value
        if key in self._menus:
            self._menus[key].dismiss()

    def _build_form(self) -> None:
        f = self._form

        ap_content = MDBoxLayout(orientation="vertical", size_hint=(1, None), spacing=dp(4))
        ap_content.add_widget(_Row("Host",           self._mk_field("ap_server.host",      "archipelago.gg")))
        ap_content.add_widget(_Row("Port",           self._mk_field("ap_server.port",      "38281", "int")))
        ap_content.add_widget(_Row("Slot name",      self._mk_field("ap_server.slot_name", "Player1")))
        ap_content.add_widget(_Row("Password",       self._mk_field("ap_server.password",  "(leave blank if none)")))
        ap_content.add_widget(_Row("Auto reconnect", self._mk_check("ap_server.auto_reconnect")))
        f.add_widget(_CollapsibleSection("AP Server", ap_content, collapsed=False))

        log_content = MDBoxLayout(orientation="vertical", size_hint=(1, None), spacing=dp(4))
        log_content.add_widget(_Row("Level",          self._mk_dropdown("logging.level", _LOG_LEVELS, "info")))
        log_content.add_widget(_Row("Log file",       self._mk_field("logging.file",    "ap_framework.log")))
        log_content.add_widget(_Row("Console output", self._mk_check("logging.console")))
        log_content.add_widget(_Row("Append log",     self._mk_check("logging.append")))
        f.add_widget(_CollapsibleSection("Logging", log_content, collapsed=False))

        to_content = MDBoxLayout(orientation="vertical", size_hint=(1, None), spacing=dp(4))
        to_content.add_widget(_Row("Connect (ms)",           self._mk_field("timeouts.connection_ms",             "30000", "int")))
        to_content.add_widget(_Row("Priority register (ms)", self._mk_field("timeouts.priority_registration_ms",  "30000", "int")))
        to_content.add_widget(_Row("Register (ms)",          self._mk_field("timeouts.registration_ms",           "60000", "int")))
        to_content.add_widget(_Row("IPC message (ms)",       self._mk_field("timeouts.ipc_message_ms",            "5000",  "int")))
        to_content.add_widget(_Row("Action exec (ms)",       self._mk_field("timeouts.action_execution_ms",       "5000",  "int")))
        to_content.add_widget(_Row("Max conn retries",       self._mk_field("timeouts.retry.max_connection",      "3",     "int")))
        to_content.add_widget(_Row("Max IPC retries",        self._mk_field("timeouts.retry.max_ipc_message",     "3",     "int")))
        to_content.add_widget(_Row("Retry delay (ms)",       self._mk_field("timeouts.retry.initial_delay_ms",    "1000",  "int")))
        to_content.add_widget(_Row("Backoff multiplier",     self._mk_field("timeouts.retry.backoff_multiplier",  "2.0")))
        to_content.add_widget(_Row("Max retry delay (ms)",   self._mk_field("timeouts.retry.max_delay_ms",        "10000", "int")))
        f.add_widget(_CollapsibleSection("Timeouts", to_content, collapsed=True))

        th_content = MDBoxLayout(orientation="vertical", size_hint=(1, None), spacing=dp(4))
        th_content.add_widget(_Row("Poll interval (ms)",  self._mk_field("threading.polling_interval_ms", "16",   "int")))
        th_content.add_widget(_Row("Queue max size",      self._mk_field("threading.queue_max_size",       "1000", "int")))
        th_content.add_widget(_Row("Shutdown (ms)",       self._mk_field("threading.shutdown_timeout_ms",  "5000", "int")))
        f.add_widget(_CollapsibleSection("Threading", th_content, collapsed=True))

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._profile = game_profile
        for menu in self._menus.values():
            menu.dismiss()
        # Subscribe to both detection and install — once per panel lifetime.
        if not self._subscribed:
            self._host.subscribe_state_change("detection", self._on_state_changed)
            self._host.subscribe_state_change("install", self._on_state_changed)
            self._subscribed = True
        if self._ctrl.has_service():
            self._ctrl.activate(game_profile)
        Clock.schedule_once(lambda dt: self._refresh_view(), 0)

    def on_deactivate(self) -> None:
        for menu in self._menus.values():
            menu.dismiss()

    def can_deactivate(self) -> bool:
        if self._dirty:
            self._show_unsaved_dialog()
            return False
        return True

    def _on_state_changed(self) -> None:
        """Fires on both 'detection' and 'install' changes."""
        if self._profile and self._ctrl.has_service():
            self._ctrl.activate(self._profile)
        Clock.schedule_once(lambda dt: self._refresh_view(), 0)

    # -----------------------------------------------------------------------
    # View switching: guard ↔ content
    # -----------------------------------------------------------------------

    def _refresh_view(self) -> None:
        dep = self._ctrl.get_dependency_state()
        ue4ss_ok = dep["ue4ss_ok"]
        fw_installed = dep["fw_installed"]

        self._body.clear_widgets()

        if ue4ss_ok and fw_installed:
            self._save_btn.disabled = False
            self._reload_btn.disabled = not self._ctrl.config_exists
            self._mod_subtitle.text = self._ctrl.framework_mod_name or ""
            self._show_content_view()
        else:
            self._save_btn.disabled = True
            self._reload_btn.disabled = True
            self._mod_subtitle.text = ""
            self._body.add_widget(self._build_guard_view(dep))

    def _show_content_view(self) -> None:
        """Add the pre-built form scroll to the body and populate if clean."""
        self._ensure_form_built()
        self._body.add_widget(self._form_scroll)
        self._body.add_widget(self._status_label)
        if not self._dirty:
            self._populate()

    def _build_guard_view(self, dep: dict) -> MDBoxLayout:
        """Build and return a full-screen guard widget explaining what's missing."""
        ue4ss_ok = dep["ue4ss_ok"]
        fw_installed = dep["fw_installed"]

        guard = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            padding=[dp(40), dp(48), dp(40), dp(48)],
            spacing=dp(20),
        )

        # Large alert icon
        icon_row = MDBoxLayout(
            orientation="horizontal", size_hint=(1, None), height=dp(72),
        )
        icon_row.add_widget(Widget(size_hint_x=1))
        icon_row.add_widget(MDIcon(
            icon="alert-circle-outline",
            font_size=dp(60),
            size_hint=(None, None), size=(dp(72), dp(72)),
            pos_hint={"center_y": 0.5},
            theme_icon_color="Custom",
            icon_color=(0.85, 0.55, 0.1, 1),
        ))
        icon_row.add_widget(Widget(size_hint_x=1))
        guard.add_widget(icon_row)

        # Title
        guard.add_widget(MDLabel(
            text="Configure Unavailable",
            font_style="Title", role="large",
            size_hint=(1, None), height=dp(40),
            halign="center",
        ))

        # Explanation
        guard.add_widget(MDLabel(
            text=(
                "Configuration requires both UE4SS and the AP Framework Mod.\n"
                "All settings are written to the framework mod's configuration file."
            ),
            size_hint=(1, None), adaptive_height=True,
            halign="center",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
        ))

        # Live status indicator rows
        status_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None), adaptive_height=True,
            spacing=dp(8), padding=[dp(24), 0],
        )
        for req_label, ok in [("UE4SS", ue4ss_ok), ("AP Framework Mod", fw_installed)]:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint=(1, None), height=dp(32),
                spacing=dp(10),
            )
            row.add_widget(Widget(size_hint_x=1))
            icon_color = (0.25, 0.8, 0.35, 1) if ok else (0.6, 0.6, 0.6, 1)
            row.add_widget(MDIcon(
                icon="check-circle-outline" if ok else "close-circle-outline",
                font_size=dp(18),
                size_hint=(None, 1), width=dp(22),
                theme_icon_color="Custom", icon_color=icon_color,
            ))
            status_color = (0.25, 0.8, 0.35, 1) if ok else (0.6, 0.6, 0.6, 1)
            row.add_widget(MDLabel(
                text=f"{req_label}  {'— installed' if ok else '— not installed'}",
                font_style="Body",
                size_hint=(None, 1), width=dp(280),
                halign="left", valign="middle",
                theme_text_color="Custom", text_color=status_color,
            ))
            row.add_widget(Widget(size_hint_x=1))
            status_box.add_widget(row)
        guard.add_widget(status_box)

        # Install instructions for missing components
        if not ue4ss_ok or not fw_installed:
            instr_box = MDBoxLayout(
                orientation="vertical",
                size_hint=(1, None), adaptive_height=True,
                spacing=dp(4), padding=[dp(24), 0],
            )
            instr_box.add_widget(MDLabel(
                text="To resolve:",
                font_style="Label", role="medium",
                size_hint=(1, None), height=dp(22),
                halign="center",
                theme_text_color="Secondary",
            ))
            if not ue4ss_ok:
                instr_box.add_widget(MDLabel(
                    text="→  UE4SS: install via the Content hub, Other section",
                    font_style="Body", role="small",
                    size_hint=(1, None), height=dp(24),
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(0.85, 0.85, 0.25, 1),
                ))
            if not fw_installed:
                instr_box.add_widget(MDLabel(
                    text="→  AP Framework Mod: install via the Content hub, Mods section",
                    font_style="Body", role="small",
                    size_hint=(1, None), height=dp(24),
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(0.85, 0.85, 0.25, 1),
                ))
            guard.add_widget(instr_box)

        # Spacer to push content to vertical center
        guard.add_widget(Widget(size_hint_y=1))
        return guard

    # -----------------------------------------------------------------------
    # Populate / collect
    # -----------------------------------------------------------------------

    def _populate(self) -> None:
        load_ok, load_error, config_path = self._ctrl.get_load_status()
        if config_path and config_path.exists():
            if load_ok:
                self._set_status(f"Loaded from: {config_path.name}")
            else:
                self._set_status(f"Error reading {config_path.name}: {load_error}")
        elif config_path:
            self._set_status(f"No config found at: {config_path}  (showing defaults)")
        else:
            self._set_status("No game context.")

        cfg = self._ctrl.get_config()
        ap = cfg.get("ap_server", {})
        self._host.log(
            f"[Configure] ap_server keys={list(ap.keys())}  "
            f"host={ap.get('host', '?')}  port={ap.get('port', '?')}"
        )

        self._fields["ap_server.host"].text      = str(ap.get("host",      "archipelago.gg"))
        self._fields["ap_server.port"].text      = str(ap.get("port",      38281))
        self._fields["ap_server.slot_name"].text = str(ap.get("slot_name", ""))
        self._fields["ap_server.password"].text  = str(ap.get("password",  ""))
        self._checks["ap_server.auto_reconnect"].active = bool(ap.get("auto_reconnect", True))

        log = cfg.get("logging", {})
        self._fields["logging.level"].text = str(log.get("level", "info"))
        self._fields["logging.file"].text  = str(log.get("file",  "ap_framework.log"))
        self._checks["logging.console"].active = bool(log.get("console", True))
        self._checks["logging.append"].active  = bool(log.get("append",  False))

        to = cfg.get("timeouts", {})
        retry = to.get("retry", {})
        self._fields["timeouts.connection_ms"].text            = str(to.get("connection_ms",            30000))
        self._fields["timeouts.priority_registration_ms"].text = str(to.get("priority_registration_ms", 30000))
        self._fields["timeouts.registration_ms"].text          = str(to.get("registration_ms",          60000))
        self._fields["timeouts.ipc_message_ms"].text           = str(to.get("ipc_message_ms",           5000))
        self._fields["timeouts.action_execution_ms"].text      = str(to.get("action_execution_ms",      5000))
        self._fields["timeouts.retry.max_connection"].text     = str(retry.get("max_connection",        3))
        self._fields["timeouts.retry.max_ipc_message"].text    = str(retry.get("max_ipc_message",       3))
        self._fields["timeouts.retry.initial_delay_ms"].text   = str(retry.get("initial_delay_ms",      1000))
        self._fields["timeouts.retry.backoff_multiplier"].text = str(retry.get("backoff_multiplier",    2.0))
        self._fields["timeouts.retry.max_delay_ms"].text       = str(retry.get("max_delay_ms",          10000))

        th = cfg.get("threading", {})
        self._fields["threading.polling_interval_ms"].text = str(th.get("polling_interval_ms", 16))
        self._fields["threading.queue_max_size"].text       = str(th.get("queue_max_size",       1000))
        self._fields["threading.shutdown_timeout_ms"].text = str(th.get("shutdown_timeout_ms",  5000))

        self._dirty = False
        Clock.schedule_once(lambda dt: self._bind_dirty(), 0)

    def _bind_dirty(self) -> None:
        if self._dirty_bound:
            self._dirty = False
            return
        self._dirty_bound = True
        for f in self._fields.values():
            f.bind(text=self._on_field_change)
        for sw in self._checks.values():
            sw.bind(active=self._on_field_change)
        self._dirty = False

    def _on_field_change(self, *_) -> None:
        self._dirty = True

    def _collect(self) -> dict:
        data = self._ctrl.get_config_deep()

        def _int(key: str, default: int) -> int:
            try:
                return int(self._fields[key].text.strip())
            except (ValueError, KeyError):
                return default

        def _float(key: str, default: float) -> float:
            try:
                return float(self._fields[key].text.strip())
            except (ValueError, KeyError):
                return default

        ap = data.setdefault("ap_server", {})
        ap["host"]           = self._fields["ap_server.host"].text.strip()
        ap["port"]           = _int("ap_server.port", 38281)
        ap["slot_name"]      = self._fields["ap_server.slot_name"].text.strip()
        ap["password"]       = self._fields["ap_server.password"].text.strip()
        ap["auto_reconnect"] = self._checks["ap_server.auto_reconnect"].active

        lg = data.setdefault("logging", {})
        lg["level"]   = self._fields["logging.level"].text.strip() or "info"
        lg["file"]    = self._fields["logging.file"].text.strip()
        lg["console"] = self._checks["logging.console"].active
        lg["append"]  = self._checks["logging.append"].active

        to = data.setdefault("timeouts", {})
        to["connection_ms"]            = _int("timeouts.connection_ms",            30000)
        to["priority_registration_ms"] = _int("timeouts.priority_registration_ms", 30000)
        to["registration_ms"]          = _int("timeouts.registration_ms",          60000)
        to["ipc_message_ms"]           = _int("timeouts.ipc_message_ms",           5000)
        to["action_execution_ms"]      = _int("timeouts.action_execution_ms",      5000)

        r = to.setdefault("retry", {})
        r["max_connection"]     = _int("timeouts.retry.max_connection",      3)
        r["max_ipc_message"]    = _int("timeouts.retry.max_ipc_message",     3)
        r["initial_delay_ms"]   = _int("timeouts.retry.initial_delay_ms",    1000)
        r["backoff_multiplier"] = _float("timeouts.retry.backoff_multiplier", 2.0)
        r["max_delay_ms"]       = _int("timeouts.retry.max_delay_ms",        10000)
        r.pop("max", None)

        th = data.setdefault("threading", {})
        th["polling_interval_ms"] = _int("threading.polling_interval_ms", 16)
        th["queue_max_size"]      = _int("threading.queue_max_size",       1000)
        th["shutdown_timeout_ms"] = _int("threading.shutdown_timeout_ms",  5000)

        return data

    # -----------------------------------------------------------------------
    # Unsaved changes dialog
    # -----------------------------------------------------------------------

    def _show_unsaved_dialog(self) -> None:
        if self._unsaved_dialog:
            return

        def _on_dismissed(*_):
            self._unsaved_dialog = None
            self._pending_nav_label = None

        def _dismiss(*_):
            if self._unsaved_dialog:
                self._unsaved_dialog.dismiss()

        def _save(*_):
            _dismiss()
            self._on_save()
            self._trigger_pending_nav()

        def _discard(*_):
            _dismiss()
            self._dirty = False
            self._populate()
            self._trigger_pending_nav()

        self._unsaved_dialog = MDDialog(
            MDDialogHeadlineText(text="Unsaved Changes"),
            MDDialogSupportingText(text="You have unsaved changes in Configure."),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_dismiss),
                MDButton(MDButtonText(text="Discard"), style="text", on_release=_discard),
                MDButton(MDButtonText(text="Save"), style="filled", on_release=_save),
            ),
        )
        self._unsaved_dialog.bind(on_dismiss=_on_dismissed)
        self._unsaved_dialog.open()

    def _trigger_pending_nav(self) -> None:
        from kivymd.app import MDApp
        app = MDApp.get_running_app()
        if not app or not hasattr(app, "_game_hub") or not app._game_hub:
            return
        hub = app._game_hub
        label = hub._pending_nav_label
        if not label:
            return
        hub._pending_nav_label = None
        if label == "__home__":
            hub._go_home()
        elif label == "__settings__":
            hub._go_settings()
        else:
            hub._select_panel(label)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_save(self) -> None:
        if self._ctrl.save(self._collect()):
            self._dirty = False
            self._reload_btn.disabled = False
            self._set_status("Saved.")
            self._host.log("framework_config.json saved.")
        else:
            self._set_status("Save failed — check path.")
            self._host.log("Failed to save framework_config.json.")

    def _on_reload(self) -> None:
        ok, load_error = self._ctrl.reload_status()
        self._host.log(
            f"[Configure] reload: ok={ok}"
            + (f"  error={load_error!r}" if not ok else "")
        )
        self._dirty = False
        self._populate()
        self._set_status("Reloaded.")

    def _set_status(self, msg: str) -> None:
        if hasattr(self, "_status_label"):
            self._status_label.text = msg
