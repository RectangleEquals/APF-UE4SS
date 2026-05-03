"""
ContentRowWidget — universal typed content row for any ContentDescriptor subtype.

Extends BaseContentRow. Subclass provides:
  _build_header_content() — type icon, name label, subtitle
  _build_detail_content() — ContentDetailPanel
  _build_right_side()     — chevron for most types, "Open" button for ExternalUrlBinary
"""
from __future__ import annotations

import webbrowser
from typing import Optional, Callable, TYPE_CHECKING

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDIcon, MDLabel

from .base_content_row import BaseContentRow
from .constants import COL_DIM

if TYPE_CHECKING:
    from ..data.content_types import (
        ContentDescriptor, ModDescriptor, APModDescriptor, FrameworkModDescriptor,
        TemplateDescriptor, GithubReleaseBinary, ExternalUrlBinary, ManualBinary,
        BinaryDescriptor,
    )
    from ..data.pipeline_state import InstallRecord


class ContentRowWidget(BaseContentRow):
    """
    Universal typed content row for any ContentDescriptor subtype.

    Parameters
    ----------
    content        : ContentDescriptor subclass
    row_index      : int — alternating background
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
        known_mod_ids: Optional[set] = None,
        detail_widget=None,
        **kwargs,
    ):
        from ..data.content_types import ExternalUrlBinary as _EUB, ManualBinary as _MB

        self._content = content
        self._install_record = install_record
        self._known_mod_ids = known_mod_ids
        self._detail_widget = detail_widget

        # EUB and ManualBinary have no expand; EUB still gets hover for the "Open" button
        _is_eub    = isinstance(content, _EUB)
        _is_manual = isinstance(content, _MB)
        _has_hover = (on_expand is not None and not _is_eub and not _is_manual) or _is_eub
        _show_chev = not _is_eub and not _is_manual

        super().__init__(
            row_index=row_index,
            checked=checked if not _is_eub and not _is_manual else None,
            expanded=expanded,
            on_check=on_check,
            on_expand=on_expand if not _is_eub and not _is_manual else None,
            actions=actions or [],
            has_hover=_has_hover,
            show_chevron=_show_chev,
            expand_on_header=False,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_expanded(self, value: bool) -> None:
        self._expanded = value
        self._build()

    # ------------------------------------------------------------------
    # BaseContentRow interface
    # ------------------------------------------------------------------

    def _build_header_content(self, header, info_col) -> None:
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

        # Type icon (inserted between checkbox and info_col by header, not here)
        icon, icon_color = self._type_icon(c, is_grb, is_tpl, is_mod)
        # Insert the icon right after the checkbox (before info_col is added)
        header.add_widget(MDIcon(
            icon=icon, size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=icon_color,
        ))

        # Name row — no C++/BP icon badges (redundant with subtitle type label)
        name_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(4),
        )
        name_row.add_widget(MDLabel(
            text=c.name or "Unknown",
            font_style="Body", size_hint=(1, 1),
            halign="left", valign="middle",
        ))
        info_col.add_widget(name_row)

        # Subtitle
        subtitle = self._subtitle(c, is_grb, is_eub, is_manual, is_tpl, is_mod)
        if subtitle:
            info_col.add_widget(MDLabel(
                text=subtitle, font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

        # Duplicate-source warning (GRB only)
        if is_grb:
            _tags = getattr(c, "tags", None)
            if _tags and _tags.has_duplicate_source:
                info_col.add_widget(MDLabel(
                    text="duplicate source",
                    font_style="Label", role="small",
                    size_hint_y=None, height=dp(14),
                    theme_text_color="Custom", text_color=(1.0, 0.75, 0.0, 1),
                ))

        # Expand touch binding on info_col (non-EUB, non-Manual types)
        has_expand = not is_eub and not is_manual
        if has_expand and self._on_expand:
            info_col.bind(on_touch_down=lambda w, t, fn=self._on_expand, ex=self._expanded: (
                fn(not ex) if w.collide_point(*t.pos) else None
            ))

    def _build_right_side(self, header) -> None:
        from ..data.content_types import ExternalUrlBinary as _EUB, ManualBinary as _MB
        c = self._content
        is_eub    = isinstance(c, _EUB)
        is_manual = isinstance(c, _MB)
        has_expand = not is_eub and not is_manual

        if is_eub:
            _url = getattr(c, "url", "")
            header.add_widget(MDButton(
                MDButtonText(text="Open"),
                style="outlined",
                size_hint=(None, None), size=(dp(72), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, u=_url: webbrowser.open(u) if u else None,
            ))
        elif has_expand and self._on_expand:
            from kivymd.uix.button import MDIconButton
            chevron = "chevron-up" if self._expanded else "chevron-down"
            header.add_widget(MDIconButton(
                icon=chevron,
                size_hint=(None, None), size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, fn=self._on_expand, ex=self._expanded: fn(not ex),
            ))
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(40)))

    def _build_detail_content(self):
        if self._detail_widget is not None:
            return self._detail_widget
        from .content_detail import ContentDetailPanel
        return ContentDetailPanel(
            content=self._content,
            install_record=self._install_record,
            known_mod_ids=self._known_mod_ids,
        )

    # ------------------------------------------------------------------
    # Static helpers
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
    def _mod_type_label(c) -> str:
        from ..data.content_types import FrameworkModDescriptor as _FW, APModDescriptor as _AP
        comps = getattr(c, "components", None)
        types = (
            comps.types if hasattr(comps, "types")
            else (comps if isinstance(comps, list) else [])
        )
        cpp_count       = 1 if "cpp"       in types else 0
        blueprint_count = 1 if "blueprint" in types else 0
        lua_count       = 1 if "lua"       in types else 0
        total = cpp_count + blueprint_count + lua_count
        if total > 1:
            comp_label = "Combo"
        elif cpp_count:
            comp_label = "C++"
        elif blueprint_count:
            comp_label = "Blueprint"
        else:
            comp_label = "Lua"
        if isinstance(c, _FW):
            return f"Framework {comp_label} Mod"
        elif isinstance(c, _AP):
            return f"AP {comp_label} Mod"
        else:
            return f"Non-AP {comp_label} Mod"

    @staticmethod
    def _subtitle(c, is_grb, is_eub, is_manual, is_tpl, is_mod) -> str:
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
            parts = [ContentRowWidget._mod_type_label(c)]
            ver = getattr(c, "version", "")
            if ver:
                parts.append(f"v{ver}")
            desc = getattr(c, "description", "")
            if desc:
                parts.append(desc)
            return " \u2022 ".join(parts)
        if is_manual:
            return "Manual Installation"
        return ""
