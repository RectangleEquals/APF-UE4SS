"""UE4SSStatusCard — UE4SS detection status + optional update notice."""
from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel


class UE4SSStatusCard(MDBoxLayout):
    """
    Self-contained card showing UE4SS detection status and an optional update banner.

    Call `refresh(ue4ss_detected, ue4ss_info)` after construction to set the state.
    The update notice row is managed internally — no duck-type tagging needed.

    Parameters
    ----------
    ue4ss_info : object | None — UpdateInfo-like with .current, .is_update_available,
                                 .latest_stable.tag_name
    """

    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(8), dp(8)],
            spacing=dp(4),
            md_bg_color=(0.1, 0.14, 0.18, 1),
            **kwargs,
        )
        self.add_widget(MDLabel(
            text="UE4SS",
            font_style="Label",
            role="medium",
            size_hint_y=None,
            height=dp(24),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        ))

        status_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(24),
            spacing=dp(6),
        )
        self._status_icon = MDIcon(
            icon="loading",
            size_hint=(None, 1),
            width=dp(20),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        self._status_lbl = MDLabel(
            text="Checking\u2026",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        status_row.add_widget(self._status_icon)
        status_row.add_widget(self._status_lbl)
        self.add_widget(status_row)

        self._update_row: MDBoxLayout | None = None

    # ------------------------------------------------------------------

    def refresh(self, ue4ss_detected: bool, ue4ss_info=None) -> None:
        """Update the card to reflect current UE4SS detection state."""
        self._remove_update_row()

        if not ue4ss_detected:
            self._status_icon.icon = "alert"
            self._status_icon.text_color = (0.9, 0.6, 0.1, 1)
            self._status_lbl.text = "UE4SS not detected"
            self._status_lbl.text_color = (0.9, 0.6, 0.1, 1)
            return

        current_ver = getattr(ue4ss_info, "current", "unknown") if ue4ss_info else "unknown"
        status_text = (
            f"UE4SS detected  v{current_ver}"
            if current_ver != "unknown"
            else "UE4SS detected (version unknown)"
        )
        self._status_icon.icon = "check-circle"
        self._status_icon.text_color = (0.3, 0.8, 0.4, 1)
        self._status_lbl.text = status_text
        self._status_lbl.text_color = (0.3, 0.8, 0.4, 1)

        if ue4ss_info and ue4ss_info.is_update_available and ue4ss_info.latest_stable:
            latest_tag = ue4ss_info.latest_stable.tag_name
            update_row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(24),
                spacing=dp(6),
            )
            update_row.add_widget(MDIcon(
                icon="arrow-up-circle",
                size_hint=(None, 1), width=dp(20),
                theme_text_color="Custom", text_color=(0.25, 0.55, 1.0, 1),
            ))
            update_row.add_widget(MDLabel(
                text=f"Update available: v{latest_tag}",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=(0.25, 0.55, 1.0, 1),
            ))
            self._update_row = update_row
            self.add_widget(update_row)

    def _remove_update_row(self) -> None:
        if self._update_row is not None:
            self.remove_widget(self._update_row)
            self._update_row = None
