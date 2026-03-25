"""
APConfigPanel — hub_panel for editing framework_config.json.

Sections:
    AP Server   — host, port, slot_name, password
    Logging     — level, file, console, append
    Timeouts    — connect_timeout_ms, recv_timeout_ms, retry_delay_ms, max_retries
    Threading   — poll_interval_ms
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from ...gui.widgets.tip_icon_button import TipIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.textfield import MDTextField

from ...gui.widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from .config_service import APConfigService


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
        self._dirty: bool = False
        self._unsaved_dialog: Optional[MDDialog] = None
        self._pending_nav_label: Optional[str] = None
        self._build_ui()

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        svc = self._host.get_service("ap_config")
        if svc:
            self._svc = svc
            svc.load()  # always reload from disk on activate
            if not self._dirty:
                Clock.schedule_once(lambda dt: self._populate(), 0)
        else:
            self._host.log("ap_config service not available.")

    def on_deactivate(self) -> None:
        pass

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

    def _build_form(self) -> None:
        f = self._form

        # AP Server
        f.add_widget(_SectionHeader("AP Server"))
        f.add_widget(_Row("Host", self._mk_field("server.host", "localhost")))
        f.add_widget(_Row("Port", self._mk_field("server.port", "38281", "int")))
        f.add_widget(_Row("Slot name", self._mk_field("server.slot_name", "Player1")))
        f.add_widget(_Row("Password", self._mk_field("server.password", "(leave blank if none)")))

        # Logging
        f.add_widget(_SectionHeader("Logging"))
        f.add_widget(_Row("Level", self._mk_field("logging.level", "info / debug / warning / error")))
        f.add_widget(_Row("Write to file", self._mk_check("logging.file")))
        f.add_widget(_Row("Console output", self._mk_check("logging.console")))
        f.add_widget(_Row("Append log", self._mk_check("logging.append")))

        # Timeouts
        f.add_widget(_SectionHeader("Timeouts"))
        f.add_widget(_Row("Connect (ms)", self._mk_field("timeouts.connect_timeout_ms", "5000", "int")))
        f.add_widget(_Row("Receive (ms)", self._mk_field("timeouts.recv_timeout_ms", "10000", "int")))
        f.add_widget(_Row("Retry delay (ms)", self._mk_field("timeouts.retry_delay_ms", "2000", "int")))
        f.add_widget(_Row("Max retries", self._mk_field("timeouts.max_retries", "5", "int")))

        # Threading
        f.add_widget(_SectionHeader("Threading"))
        f.add_widget(_Row("Poll interval (ms)", self._mk_field("threading.poll_interval_ms", "100", "int")))

    # -----------------------------------------------------------------------
    # Populate / collect
    # -----------------------------------------------------------------------

    def _populate(self) -> None:
        if not self._svc:
            return
        if not self._svc.has_config:
            path_str = str(self._svc.config_path) if self._svc.config_path else "unknown"
            self._set_status(f"No config found at: {path_str}")
        else:
            self._set_status("")

        cfg = self._svc.get_config()

        server = cfg.get("server", {})
        self._fields["server.host"].text = str(server.get("host", "localhost"))
        self._fields["server.port"].text = str(server.get("port", 38281))
        self._fields["server.slot_name"].text = str(server.get("slot_name", ""))
        self._fields["server.password"].text = str(server.get("password", ""))

        logging_ = cfg.get("logging", {})
        self._fields["logging.level"].text = str(logging_.get("level", "info"))
        self._checks["logging.file"].active = bool(logging_.get("file", True))
        self._checks["logging.console"].active = bool(logging_.get("console", True))
        self._checks["logging.append"].active = bool(logging_.get("append", False))

        timeouts = cfg.get("timeouts", {})
        self._fields["timeouts.connect_timeout_ms"].text = str(timeouts.get("connect_timeout_ms", 5000))
        self._fields["timeouts.recv_timeout_ms"].text = str(timeouts.get("recv_timeout_ms", 10000))
        self._fields["timeouts.retry_delay_ms"].text = str(timeouts.get("retry_delay_ms", 2000))
        self._fields["timeouts.max_retries"].text = str(timeouts.get("max_retries", 5))

        threading_ = cfg.get("threading", {})
        self._fields["threading.poll_interval_ms"].text = str(threading_.get("poll_interval_ms", 100))

        # Reset dirty BEFORE binding so populate assignments don't trigger it
        self._dirty = False

        # Bind fields to dirty flag (schedule to run after this frame completes)
        Clock.schedule_once(lambda dt: self._bind_dirty(), 0)

    def _bind_dirty(self) -> None:
        """Bind all fields to mark dirty on user changes."""
        for f in self._fields.values():
            f.bind(text=self._on_field_change)
        for sw in self._checks.values():
            sw.bind(active=self._on_field_change)
        # Clear any spurious dirty caused by layout-induced events during this frame
        self._dirty = False

    def _on_field_change(self, *_) -> None:
        self._dirty = True

    def _collect(self) -> dict:
        def _int(key: str, default: int) -> int:
            try:
                return int(self._fields[key].text.strip())
            except (ValueError, KeyError):
                return default

        return {
            "server": {
                "host": self._fields["server.host"].text.strip(),
                "port": _int("server.port", 38281),
                "slot_name": self._fields["server.slot_name"].text.strip(),
                "password": self._fields["server.password"].text.strip(),
            },
            "logging": {
                "level": self._fields["logging.level"].text.strip() or "info",
                "file": self._checks["logging.file"].active,
                "console": self._checks["logging.console"].active,
                "append": self._checks["logging.append"].active,
            },
            "timeouts": {
                "connect_timeout_ms": _int("timeouts.connect_timeout_ms", 5000),
                "recv_timeout_ms": _int("timeouts.recv_timeout_ms", 10000),
                "retry_delay_ms": _int("timeouts.retry_delay_ms", 2000),
                "max_retries": _int("timeouts.max_retries", 5),
            },
            "threading": {
                "poll_interval_ms": _int("threading.poll_interval_ms", 100),
            },
        }

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
        self._svc.load()
        self._dirty = False
        self._populate()
        self._set_status("Reloaded.")

    def _set_status(self, msg: str) -> None:
        self._status_label.text = msg
