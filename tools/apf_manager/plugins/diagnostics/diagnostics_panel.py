"""
DiagnosticsPanel — hub_panel for diagnostics plugin.

Features:
  - Run Validation: checks mods, dependencies, file presence via deploy validator (if available)
  - Package Logs: collect ap_framework.log + UE4SS.log + session_state.json + sanitized config → ZIP
  - Copy results to clipboard (hidden until results are available)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

from ...core.views.theme import STATUS_ICONS
from ...core.views.widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.models.config import GameProfile


class _ResultRow(MDBoxLayout):
    def __init__(self, label: str, detail: str, status: str, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(40),
            spacing=dp(8),
            padding=[dp(4), 0],
            **kwargs,
        )
        icon_name, icon_color = STATUS_ICONS.get(status, STATUS_ICONS["unknown"])
        self.add_widget(MDIcon(
            icon=icon_name,
            theme_icon_color="Custom",
            icon_color=icon_color,
            size_hint=(None, 1),
            width=dp(24),
            halign="center",
            valign="middle",
        ))
        self.add_widget(MDLabel(
            text=f"[b]{label}[/b]  {detail}" if detail else f"[b]{label}[/b]",
            markup=True,
            size_hint=(1, 1),
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.9, 0.9, 0.9, 1),
        ))


class DiagnosticsPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._detection = None
        self._result_text: str = ""
        self._build_ui()

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._profile = game_profile
        self._detection = self._host.get_detection()
        self._clear_results()

    def on_deactivate(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.orientation = "vertical"

        toolbar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56),
                              md_bg_color=(0.15, 0.2, 0.25, 1), padding=(dp(8), 0), spacing=dp(4))
        toolbar.add_widget(MDLabel(text="Diagnostics", font_style="Title", role="large",
                                   size_hint_x=1, halign="left"))

        # Copy button — hidden until results are available
        from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
        self._copy_btn = MDButton(
            MDButtonIcon(icon="content-copy"),
            MDButtonText(text="Copy to Clipboard"),
            style="tonal",
            on_release=lambda *_: self._on_copy(),
            opacity=0,
            disabled=True,
        )
        toolbar.add_widget(self._copy_btn)
        self._toolbar = toolbar
        self.add_widget(toolbar)

        # Action buttons
        btn_row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(56),
            spacing=dp(12),
            padding=[dp(16), dp(8)],
        )
        btn_row.add_widget(MDButton(
            MDButtonText(text="Run Validation"),
            style="filled",
            on_release=lambda *_: self._on_validate(),
        ))
        btn_row.add_widget(MDButton(
            MDButtonText(text="Package Logs"),
            style="filled",
            on_release=lambda *_: threading.Thread(
                target=self._on_package_logs, daemon=True
            ).start(),
        ))
        if self._host.dev_mode:
            btn_row.add_widget(MDButton(
                MDButtonText(text="Import Diagnostics\u2026"),
                style="tonal",
                on_release=lambda *_: self._on_import_diagnostics(),
            ))
        self.add_widget(btn_row)

        # Results area
        self._scroll = ScrollView(size_hint=(1, 1))
        self._results_layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(16), dp(8)],
        )
        self._scroll.add_widget(self._results_layout)
        self.add_widget(self._scroll)

    def _clear_results(self) -> None:
        self._result_text = ""
        self._copy_btn.opacity = 0
        self._copy_btn.disabled = True
        self._clear_zip_viewer()
        self._results_layout.clear_widgets()
        self._results_layout.add_widget(MDLabel(
            text="Press 'Run Validation' to check your setup.",
            halign="center",
            size_hint=(1, None),
            height=dp(48),
        ))

    # -----------------------------------------------------------------------
    # Copy
    # -----------------------------------------------------------------------

    def _on_copy(self) -> None:
        if self._result_text:
            Clipboard.copy(self._result_text)
        self._copy_btn.opacity = 0
        self._copy_btn.disabled = True
        MDSnackbar(
            MDSnackbarText(text="Results copied to clipboard."),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            duration=2,
        ).open()

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    def _on_validate(self) -> None:
        if not self._detection:
            self._show_error("No game context — cannot validate.")
            return

        self._clear_zip_viewer()
        self._results_layout.clear_widgets()
        result_lines: list[str] = []

        def _add(label: str, detail: str, status: str) -> None:
            self._add_result(label, detail, status)
            icon_map = {"ok": "✓", "warn": "⚠", "error": "✗"}
            line = f"{icon_map.get(status, '?')} {label}"
            if detail:
                line += f"  — {detail}"
            result_lines.append(line)

        # UE4SS presence
        _add(
            "UE4SS detected",
            str(self._detection.ue4ss_dir or ""),
            "ok" if self._detection.valid else "error",
        )

        # Missing components
        for missing in (self._detection.missing or []):
            _add(f"Missing: {missing}", "", "error")

        # Mod validation (via ValidationService)
        validation_svc = self._host.get_service("validation")
        mods_svc = self._host.get_service("mods")
        if validation_svc and mods_svc:
            mods = mods_svc.scan()
            results = validation_svc.validate_installed(mods, self._detection)
            for r in results:
                if r.status != "ok":
                    _add(f"{r.source}: {r.label}", r.detail, r.status)
            if not any(r.status != "ok" for r in results):
                _add("All mod checks passed", "", "ok")
        else:
            _add("Mod validation skipped", "Validation service not available", "warn")

        self._host.log("Validation complete.")

        # Store result text and show copy button
        self._result_text = "\n".join(result_lines)
        self._copy_btn.opacity = 1
        self._copy_btn.disabled = False

    def _add_result(self, label: str, detail: str, status: str) -> None:
        self._results_layout.add_widget(
            _ResultRow(label=label, detail=detail, status=status)
        )

    def _show_error(self, msg: str) -> None:
        self._clear_zip_viewer()
        self._results_layout.clear_widgets()
        self._results_layout.add_widget(MDLabel(
            text=msg,
            halign="center",
            size_hint=(1, None),
            height=dp(48),
        ))

    # -----------------------------------------------------------------------
    # Import diagnostics ZIP (dev mode)
    # -----------------------------------------------------------------------

    def _on_import_diagnostics(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Open Diagnostics ZIP",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            )
            root.destroy()
            if path:
                self._show_zip(path)
        except Exception as exc:
            self._show_error(f"Could not open file picker: {exc}")

    def _show_zip(self, zip_path: str) -> None:
        from .zip_viewer import ZipViewer
        self._result_text = ""
        self._copy_btn.opacity = 0
        self._copy_btn.disabled = True
        # Replace the scroll content area with the zip viewer directly
        self.remove_widget(self._scroll)
        viewer = ZipViewer(zip_path=zip_path, size_hint=(1, 1))
        self._zip_viewer = viewer
        self.add_widget(viewer)

    def _clear_zip_viewer(self) -> None:
        """Restore the normal results scroll area if a zip viewer was shown."""
        viewer = getattr(self, "_zip_viewer", None)
        if viewer is not None and viewer in self.children:
            self.remove_widget(viewer)
            self._zip_viewer = None
            if self._scroll not in self.children:
                self.add_widget(self._scroll)

    # -----------------------------------------------------------------------
    # Log packaging
    # -----------------------------------------------------------------------

    def _on_package_logs(self) -> None:
        if not self._profile or not self._detection:
            Clock.schedule_once(
                lambda dt: self._host.log("No game context — cannot package logs."), 0
            )
            return
        # Open folder picker on the main thread, then save on a background thread.
        Clock.schedule_once(lambda dt: self._prompt_and_save_logs(), 0)

    def _prompt_and_save_logs(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="Save Log Package To...")
            root.destroy()
        except Exception:
            # Fallback: save to Desktop
            folder = str(Path.home() / "Desktop")
        if not folder:
            return  # user cancelled
        import threading
        threading.Thread(target=self._do_save_logs, args=(folder,), daemon=True).start()

    def _do_save_logs(self, folder: str) -> None:
        from .log_packager import LogPackager
        packager = LogPackager(self._profile, self._detection)
        filename = LogPackager.suggested_filename(self._profile.display_name)
        out_path = Path(folder) / filename
        included = packager.collect(out_path)
        log_msg = f"Log package saved: {out_path}\n  Included: {', '.join(included)}"
        Clock.schedule_once(lambda dt, m=log_msg: self._host.log(m), 0)
        Clock.schedule_once(lambda dt: self._show_save_snackbar(out_path.name), 0)

    def _show_save_snackbar(self, filename: str) -> None:
        MDSnackbar(
            MDSnackbarText(text=f"Saved: {filename}"),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            duration=3,
        ).open()
