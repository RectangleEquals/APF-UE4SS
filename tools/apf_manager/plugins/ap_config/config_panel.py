"""
APConfigPanel — hub_panel for editing framework_config.json.

Sections (collapsible):
    AP Server   — host, port, slot_name, password, auto_reconnect  [expanded]
    Logging     — level (dropdown), file, console, append           [expanded]
    Timeouts    — connection/registration/ipc/action + retry        [collapsed]
    Threading   — polling interval, queue size, shutdown timeout    [collapsed]
"""

from __future__ import annotations

import copy
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from ...core.views.widgets.tip_icon_button import TipIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.textfield import MDTextField

from ...core.views.widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.models.config import GameProfile
    from .config_service import APConfigService


_LOG_LEVELS = ["trace", "debug", "info", "warn", "error", "fatal"]


class _SectionHeader(MDLabel):
    def __init__(self, text: str, **kwargs):
        super().__init__(
            text=text,
            font_style="Title",
            role="large",
            size_hint=(1, None),
            height=dp(36),
            padding=[dp(4), 0],
            theme_text_color="Custom",
            text_color=(0.55, 0.75, 0.95, 1),
            **kwargs,
        )


class _CollapsibleSection(MDBoxLayout):
    """Header row that toggles visibility of a content MDBoxLayout."""

    def __init__(self, title: str, content: MDBoxLayout, collapsed: bool = False, **kwargs):
        super().__init__(orientation="vertical", size_hint=(1, None), height=dp(40), **kwargs)
        self._collapsed = collapsed

        # Header row
        header = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(40),
            md_bg_color=(0.1, 0.14, 0.18, 1),
            padding=(dp(4), 0),
            spacing=dp(4),
        )
        self._chevron = MDIconButton(
            icon="chevron-right" if collapsed else "chevron-down",
            size_hint_x=None,
            width=dp(32),
            on_release=lambda *_: self._toggle(),
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
        content.size_hint_y = None  # height managed explicitly — no adaptive_height
        # Update our height whenever content's minimum_height changes, but only if expanded
        content.fbind("minimum_height", self._on_content_height)
        self.add_widget(content)

        if collapsed:
            # Defer until after first layout pass so minimum_height values are real
            Clock.schedule_once(lambda dt: self._apply_state(), 0)
        # If not collapsed, _on_content_height fires after layout and sets self.height

    def _on_content_height(self, content, min_h):
        """Called when content's minimum_height changes. Only updates if expanded."""
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
        self._svc: Optional["APConfigService"] = None
        self._fields: dict[str, MDTextField] = {}
        self._checks: dict[str, MDSwitch] = {}
        self._menus: dict[str, MDDropdownMenu] = {}
        self._dirty: bool = False
        self._dirty_bound: bool = False
        self._unsaved_dialog: Optional[MDDialog] = None
        self._pending_nav_label: Optional[str] = None
        self._build_ui()

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        for menu in self._menus.values():
            menu.dismiss()
        svc = self._host.get_service("ap_config")
        if svc:
            self._svc = svc
            ok = svc.load()
            self._host.log(
                f"[Configure] load()={ok}  path={svc.config_path}"
                + (f"  error={svc.load_error!r}" if not ok else "")
            )
            if not self._dirty:
                Clock.schedule_once(lambda dt: self._populate(), 0)
        else:
            self._host.log("ap_config service not available.")

    def on_deactivate(self) -> None:
        for menu in self._menus.values():
            menu.dismiss()

    def can_deactivate(self) -> bool:
        if self._dirty:
            self._show_unsaved_dialog()
            return False  # block nav; dialog will trigger nav itself on Save/Discard
        return True

    # -----------------------------------------------------------------------
    # UI build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.orientation = "vertical"

        toolbar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56),
                              md_bg_color=(0.15, 0.2, 0.25, 1), padding=(dp(8), 0), spacing=dp(4))
        toolbar.add_widget(MDLabel(text="Configure", font_style="Title", role="large",
                                   size_hint_x=1, halign="left"))
        toolbar.add_widget(TipIconButton(icon="content-save", tooltip_text="Save config",
                                         on_release=lambda *_: self._on_save()))
        toolbar.add_widget(TipIconButton(icon="refresh", tooltip_text="Reload from disk",
                                         on_release=lambda *_: self._on_reload()))
        self._toolbar = toolbar
        self.add_widget(toolbar)

        scroll = ScrollView(size_hint=(1, 1))
        form = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            padding=[dp(16), dp(8)],
            spacing=dp(4),
        )
        scroll.add_widget(form)
        self.add_widget(scroll)
        self._form = form

        self._status_label = MDLabel(
            text="",
            size_hint=(1, None),
            height=dp(32),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
        )
        self.add_widget(self._status_label)

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
        """Text field that opens a dropdown on direct tap."""
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

        # ── AP Server (expanded) ──────────────────────────────────────────
        ap_content = MDBoxLayout(orientation="vertical", size_hint=(1, None),
                                 spacing=dp(4))
        ap_content.add_widget(_Row("Host",           self._mk_field("ap_server.host",      "archipelago.gg")))
        ap_content.add_widget(_Row("Port",           self._mk_field("ap_server.port",      "38281", "int")))
        ap_content.add_widget(_Row("Slot name",      self._mk_field("ap_server.slot_name", "Player1")))
        ap_content.add_widget(_Row("Password",       self._mk_field("ap_server.password",  "(leave blank if none)")))
        ap_content.add_widget(_Row("Auto reconnect", self._mk_check("ap_server.auto_reconnect")))
        f.add_widget(_CollapsibleSection("AP Server", ap_content, collapsed=False))

        # ── Logging (expanded) ───────────────────────────────────────────
        log_content = MDBoxLayout(orientation="vertical", size_hint=(1, None),
                                  spacing=dp(4))
        log_content.add_widget(_Row("Level",          self._mk_dropdown("logging.level", _LOG_LEVELS, "info")))
        log_content.add_widget(_Row("Log file",       self._mk_field("logging.file",    "ap_framework.log")))
        log_content.add_widget(_Row("Console output", self._mk_check("logging.console")))
        log_content.add_widget(_Row("Append log",     self._mk_check("logging.append")))
        f.add_widget(_CollapsibleSection("Logging", log_content, collapsed=False))

        # ── Timeouts (collapsed) ─────────────────────────────────────────
        to_content = MDBoxLayout(orientation="vertical", size_hint=(1, None),
                                 spacing=dp(4))
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

        # ── Threading (collapsed) ────────────────────────────────────────
        th_content = MDBoxLayout(orientation="vertical", size_hint=(1, None),
                                 spacing=dp(4))
        th_content.add_widget(_Row("Poll interval (ms)",  self._mk_field("threading.polling_interval_ms", "16",   "int")))
        th_content.add_widget(_Row("Queue max size",      self._mk_field("threading.queue_max_size",       "1000", "int")))
        th_content.add_widget(_Row("Shutdown (ms)",       self._mk_field("threading.shutdown_timeout_ms",  "5000", "int")))
        f.add_widget(_CollapsibleSection("Threading", th_content, collapsed=True))

    # -----------------------------------------------------------------------
    # Populate / collect
    # -----------------------------------------------------------------------

    def _populate(self) -> None:
        if not self._svc:
            return
        path = self._svc.config_path
        if path and path.exists():
            if self._svc.load_ok:
                self._set_status(f"Loaded from: {path.name}")
            else:
                self._set_status(f"Error reading {path.name}: {self._svc.load_error}")
        elif path:
            self._set_status(f"No config found at: {path}  (showing defaults)")
        else:
            self._set_status("No game context.")

        cfg = self._svc.get_config()
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

        # Reset dirty BEFORE binding so populate assignments don't trigger it
        self._dirty = False

        # Bind fields to dirty flag (schedule to run after this frame completes)
        Clock.schedule_once(lambda dt: self._bind_dirty(), 0)

    def _bind_dirty(self) -> None:
        """Bind all fields to mark dirty on user changes (only binds once)."""
        if self._dirty_bound:
            self._dirty = False
            return
        self._dirty_bound = True
        for f in self._fields.values():
            f.bind(text=self._on_field_change)
        for sw in self._checks.values():
            sw.bind(active=self._on_field_change)
        # Clear any spurious dirty caused by layout-induced events during this frame
        self._dirty = False

    def _on_field_change(self, *_) -> None:
        self._dirty = True

    def _collect(self) -> dict:
        # Deep-copy existing data to preserve game_name, and any unknown fields
        data = copy.deepcopy(self._svc._data) if (self._svc and self._svc._data) else {}

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
        # Write correct C++ schema (flat max_connection, NOT legacy nested max.connection)
        r["max_connection"]     = _int("timeouts.retry.max_connection",      3)
        r["max_ipc_message"]    = _int("timeouts.retry.max_ipc_message",     3)
        r["initial_delay_ms"]   = _int("timeouts.retry.initial_delay_ms",    1000)
        r["backoff_multiplier"] = _float("timeouts.retry.backoff_multiplier", 2.0)
        r["max_delay_ms"]       = _int("timeouts.retry.max_delay_ms",        10000)
        # Remove legacy nested "max" key if present (schema bug in old files)
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
            return  # already open

        def _on_dismissed(*_):
            """Fired for any dismiss — button click OR outside-click."""
            self._unsaved_dialog = None
            # Outside-click = implicit cancel; clear pending nav so future nav works.
            self._pending_nav_label = None

        def _dismiss(*_):
            if self._unsaved_dialog:
                self._unsaved_dialog.dismiss()
                # _on_dismissed will fire automatically via on_dismiss binding

        def _save(*_):
            _dismiss()
            self._on_save()
            # Navigate away after save — dirty is now False
            self._trigger_pending_nav()

        def _discard(*_):
            _dismiss()
            self._dirty = False
            self._populate()
            self._trigger_pending_nav()

        # _cancel: do nothing — user stays on Configure
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
        """After resolving dirty state, resume the pending navigation."""
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
        if not self._svc:
            return
        self._svc.update(self._collect())
        if self._svc.save():
            self._dirty = False
            self._set_status("Saved.")
            self._host.log("framework_config.json saved.")
        else:
            self._set_status("Save failed — check path.")
            self._host.log("Failed to save framework_config.json.")

    def _on_reload(self) -> None:
        if not self._svc:
            return
        ok = self._svc.load()
        self._host.log(
            f"[Configure] reload: ok={ok}"
            + (f"  error={self._svc.load_error!r}" if not ok else "")
        )
        self._dirty = False
        self._populate()
        self._set_status("Reloaded.")

    def _set_status(self, msg: str) -> None:
        self._status_label.text = msg
