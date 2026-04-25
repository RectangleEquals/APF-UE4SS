"""
ContentRowWidget — universal typed content row for any ContentDescriptor subtype.

Replaces hand-built row builders in content, downloads, and installed tabs.
"""
from __future__ import annotations

from typing import Optional, Callable, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDButton, MDButtonText
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

from .constants import COL_DIM, COL_WARN, COL_CPP, COL_BP, COL_STATUS_OK, COL_STATUS_MISS
from .hover_row import HoverRow

if TYPE_CHECKING:
    from ..data.content_types import (
        ContentDescriptor, ModDescriptor, APModDescriptor, FrameworkModDescriptor,
        TemplateDescriptor, GithubReleaseBinary, ExternalUrlBinary, ManualBinary,
        BinaryDescriptor,
    )
    from ..data.pipeline_state import InstallRecord


_BG_ROW_EVEN = (0.11, 0.12, 0.15, 1)
_BG_ROW_ODD  = (0.09, 0.10, 0.13, 1)


class ContentRowWidget(MDBoxLayout):
    """
    Universal typed content row for any ContentDescriptor subtype.

    Layout (horizontal header):
      [checkbox?] [type-icon] [name + subline] [version badge] [action btns] [chevron?]

    Parameters
    ----------
    content        : ContentDescriptor subclass
    row_index      : int — used for alternating background
    checked        : bool | None — initial checkbox state (None = no checkbox)
    expanded       : bool — initial expanded state
    on_check       : Callable[[bool], None]
    on_expand      : Callable[[bool], None]
    actions        : list[dict] — [{icon, tooltip, callback}, ...]
    install_record : Optional[InstallRecord]
    """

    def __init__(
        self,
        content,
        row_index: int = 0,
        checked: Optional[bool] = None,
        expanded: bool = False,
        on_check: Optional[Callable[[bool], None]] = None,
        on_expand: Optional[Callable[[bool], None]] = None,
        actions: Optional[list] = None,
        install_record=None,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            md_bg_color=_BG_ROW_EVEN if row_index % 2 == 0 else _BG_ROW_ODD,
            **kwargs,
        )
        self._content = content
        self._checked = checked
        self._expanded = expanded
        self._on_check = on_check
        self._on_expand = on_expand
        self._actions = actions or []
        self._install_record = install_record

        self._build()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_expanded(self, value: bool) -> None:
        self._expanded = value
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.clear_widgets()
        from ..data.content_types import (
            GithubReleaseBinary as _GRB,
            ExternalUrlBinary as _EUB,
            ManualBinary as _MB,
            TemplateDescriptor as _TPL,
            ModDescriptor as _MOD,
        )
        c = self._content

        is_grb    = isinstance(c, _GRB)
        is_eub    = isinstance(c, _EUB)
        is_manual = isinstance(c, _MB)
        is_tpl    = isinstance(c, _TPL)
        is_mod    = isinstance(c, _MOD)

        # Interactable rows use HoverRow for mouse-over highlight
        if is_grb:
            header = HoverRow(
                orientation="horizontal", size_hint_y=None, height=dp(52),
                padding=[dp(8), dp(4)], spacing=dp(8),
            )
        else:
            header = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(52),
                padding=[dp(8), dp(4)], spacing=dp(8),
            )

        # --- Checkbox ---
        if self._checked is not None and not is_eub and not is_manual:
            cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                            pos_hint={"center_y": 0.5})
            cb.active = bool(self._checked)
            if self._on_check:
                cb.bind(active=lambda inst, val, fn=self._on_check: fn(val))
            header.add_widget(cb)
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(24)))

        # --- Type icon ---
        icon, icon_color = self._type_icon(c, is_grb, is_tpl, is_mod)
        header.add_widget(MDIcon(
            icon=icon, size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=icon_color,
        ))

        # --- Info column (name + subtitle + component badges) ---
        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        name_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(4),
        )
        name_row.add_widget(MDLabel(
            text=c.name or "Unknown",
            font_style="Body", size_hint=(1, 1),
            halign="left", valign="middle",
        ))

        # Component badges for mods
        if is_mod:
            _comp_raw = getattr(c, "components", None)
            comp_types = _comp_raw.types if hasattr(_comp_raw, "types") else (_comp_raw if isinstance(_comp_raw, list) else [])
            if "cpp" in comp_types:
                name_row.add_widget(MDIcon(
                    icon="code-braces", size_hint=(None, None), size=(dp(20), dp(20)),
                    pos_hint={"center_y": 0.5},
                    theme_icon_color="Custom", icon_color=COL_CPP,
                ))
            if "blueprint" in comp_types:
                name_row.add_widget(MDIcon(
                    icon="blueprint", size_hint=(None, None), size=(dp(20), dp(20)),
                    pos_hint={"center_y": 0.5},
                    theme_icon_color="Custom", icon_color=COL_BP,
                ))
        info.add_widget(name_row)

        # Subtitle
        subtitle = self._subtitle(c, is_grb, is_eub, is_manual, is_tpl, is_mod)
        if subtitle:
            info.add_widget(MDLabel(
                text=subtitle, font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

        # Duplicate source warning for GRB
        if is_grb:
            _tags = getattr(c, "tags", None)
            if _tags and _tags.has_duplicate_source:
                info.add_widget(MDLabel(
                    text="duplicate source",
                    font_style="Label", role="small",
                    size_hint_y=None, height=dp(14),
                    theme_text_color="Custom", text_color=(1.0, 0.75, 0.0, 1),
                ))

        # Expand touch binding (for expandable types)
        has_expand = not is_eub and not is_manual
        if has_expand and self._on_expand:
            info.bind(on_touch_down=lambda w, t, fn=self._on_expand, ex=self._expanded: (
                fn(not ex) if w.collide_point(*t.pos) else None
            ))
        header.add_widget(info)

        # --- Action buttons (external URL open, custom actions) ---
        for act in self._actions:
            btn = MDIconButton(
                icon=act.get("icon", "dots-vertical"),
                size_hint=(None, None), size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, cb=act.get("callback"): cb() if cb else None,
            )
            header.add_widget(btn)

        if is_eub:
            import webbrowser
            _url = getattr(c, "url", "")
            header.add_widget(MDButton(
                MDButtonText(text="Open"),
                style="outlined", size_hint=(None, None), size=(dp(72), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, u=_url: webbrowser.open(u) if u else None,
            ))
        elif has_expand and self._on_expand:
            chevron = "chevron-up" if self._expanded else "chevron-down"
            header.add_widget(MDIconButton(
                icon=chevron,
                size_hint=(None, None), size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, fn=self._on_expand, ex=self._expanded: fn(not ex),
            ))
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(40)))

        self.add_widget(header)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _type_icon(c, is_grb, is_tpl, is_mod):
        from ..data.content_types import FrameworkModDescriptor as _FW
        if is_grb:
            return "package-variant", (0.8, 0.55, 0.1, 1)
        if is_tpl:
            return "file-tree", (0.2, 0.7, 0.6, 1)
        if isinstance(c, _FW):
            return "puzzle-outline", (0.5, 0.8, 1.0, 1)
        if is_mod:
            return "layers-search", (0.3, 0.5, 0.9, 1)
        return "package-variant", (0.6, 0.6, 0.6, 1)

    @staticmethod
    def _subtitle(c, is_grb, is_eub, is_manual, is_tpl, is_mod):
        if is_grb:
            _src = c.source
            if c.install_type == "framework_binary":
                return f"framework binaries \u00b7 {_src.repo.full_name if _src else ''}"
            elif _src and _src.is_prerelease:
                return f"experimental \u00b7 {_src.repo.full_name}"
            else:
                return f"stable \u00b7 {_src.repo.full_name if _src else ''}"
        if is_tpl:
            _tags = getattr(c, "tags", None)
            has_conflict = _tags.has_conflict if _tags else False
            return "conflict detected" if has_conflict else ""
        if is_mod:
            mod_id = getattr(c, "mod_id", "")
            desc   = getattr(c, "description", "")
            if mod_id:
                return mod_id
            elif desc:
                return desc
            return "Non-AP Mod"
        if is_manual:
            return "Manual Installation"
        return ""
