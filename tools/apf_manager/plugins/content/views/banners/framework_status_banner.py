"""
FrameworkStatusBanner — parameterised framework/dependency status banner.

Covers the following states used across templates_section, downloads_tab,
install_tab, and content_tab:
  "no_framework"         — framework mod not installed (templates/mods locked)
  "no_registry_framework"— no AP Framework mod found in this registry
  "update_available"     — update available for framework/UE4SS
  "locked"               — section locked with custom title + notice text
"""

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel

from ..chrome.constants import COL_WARN

_COL_UPDATE = (0.25, 0.65, 1.0, 1)


class FrameworkStatusBanner(MDBoxLayout):
    """
    Parameterised banner for framework/dependency status conditions.

    Parameters
    ----------
    state   : str — one of "no_framework", "no_registry_framework",
                    "update_available", "locked"
    detail  : str — optional detail text (used for update version or locked notice)
    title   : str — optional title label (used when state="locked")
    color   : tuple — optional icon/text colour override (used when state="locked")
    """

    def __init__(
        self,
        state: str = "no_framework",
        detail: str = "",
        title: str = "",
        color=None,
        **kwargs,
    ):
        if state == "locked":
            bg = (0.11, 0.11, 0.11, 1)
            height = dp(36)
        elif state == "update_available":
            bg = (0.09, 0.13, 0.20, 1)
            height = dp(36)
        else:
            bg = (0.20, 0.14, 0.06, 1)
            height = dp(44)

        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=height,
            md_bg_color=bg,
            padding=[dp(12), 0],
            spacing=dp(8),
            **kwargs,
        )

        if state == "no_framework":
            icon = "alert"
            icon_color = color or COL_WARN
            text = (
                detail or
                "AP Framework mod not installed — Templates require it to deploy. "
                "Mods can still be deployed but will not function correctly at runtime. "
                "Find the AP Framework Mod in the Mods section after adding a registry."
            )
            text_color = color or COL_WARN

        elif state == "no_registry_framework":
            icon = "alert"
            icon_color = color or COL_WARN
            text = detail or "No AP Framework mod found in this registry"
            text_color = color or COL_WARN

        elif state == "update_available":
            icon = "arrow-up-circle"
            icon_color = color or _COL_UPDATE
            text = detail or "Update available"
            text_color = color or _COL_UPDATE

        elif state == "locked":
            icon = "lock-outline"
            icon_color = color or COL_WARN
            text = detail or notice_text_for_locked(title)
            text_color = color or COL_WARN

        else:
            icon = "information-outline"
            icon_color = color or COL_WARN
            text = detail
            text_color = color or COL_WARN

        self.add_widget(MDIcon(
            icon=icon,
            size_hint=(None, 1), width=dp(24),
            theme_icon_color="Custom", icon_color=icon_color,
        ))
        self.add_widget(MDLabel(
            text=text,
            theme_text_color="Custom", text_color=text_color,
            font_style="Label", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
        ))


def notice_text_for_locked(title: str) -> str:
    return f"{title} requires the AP Framework to be installed first."
