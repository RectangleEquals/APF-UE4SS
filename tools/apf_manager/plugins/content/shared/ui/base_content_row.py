"""
BaseContentRow — abstract base widget for all content pipeline row widgets.

Provides the shared skeleton:
  [checkbox?] [info_col] [actions] [right_side]

Subclasses implement:
  _build_header_content(header, info_col) — fill info_col; optionally bind header
  _build_detail_content()                 — return Optional widget for expanded detail
  _build_right_side(header)               — override to customise the right-side slot

Change-detection guard: when _do_refresh() rebuilds the widget and sets cb.active
programmatically, Kivy fires the active observer even if the value didn't change.
The guard compares the new value against the captured initial value and skips
_on_check if unchanged — prevents infinite rebuild loops.
"""
from __future__ import annotations

from typing import Optional, Callable

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.selectioncontrol import MDCheckbox

from .hover_row import HoverRow, RowHeader

_BG_ROW_EVEN = (0.11, 0.12, 0.15, 1)
_BG_ROW_ODD  = (0.09, 0.10, 0.13, 1)


class BaseContentRow(MDBoxLayout):
    """
    Abstract base for all content pipeline row widgets.

    Parameters
    ----------
    row_index         : int — alternating background (even/odd)
    checked           : bool | None — initial checkbox state; None = no checkbox
    expanded          : bool — initial expanded state
    on_check          : Callable[[bool], None] — fired when checkbox value changes
    on_expand         : Callable[[bool], None] — fired when expand is triggered
    actions           : list[dict] — [{icon, callback, tooltip?}, ...]
    has_hover         : bool — True = HoverRow header, False = RowHeader header
    header_height     : int — header row height in dp units (default 52)
    show_chevron      : bool — show expand/collapse chevron on the right (default True)
    expand_on_header  : bool — True = whole header click triggers on_expand (PackageHeaderWidget)
    """

    def __init__(
        self,
        row_index: int = 0,
        checked: Optional[bool] = None,
        expanded: bool = False,
        on_check: Optional[Callable[[bool], None]] = None,
        on_expand: Optional[Callable[[bool], None]] = None,
        actions: Optional[list] = None,
        has_hover: bool = True,
        header_height: int = 52,
        show_chevron: bool = True,
        expand_on_header: bool = False,
        **kwargs,
    ):
        bg = kwargs.pop("md_bg_color", _BG_ROW_EVEN if row_index % 2 == 0 else _BG_ROW_ODD)
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            md_bg_color=bg,
            **kwargs,
        )
        self._row_index = row_index
        self._checked = checked
        self._expanded = expanded
        self._on_check = on_check
        self._on_expand = on_expand
        self._actions = actions or []
        self._has_hover = has_hover
        self._header_height = header_height
        self._show_chevron = show_chevron
        self._expand_on_header = expand_on_header

        self._build()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_expanded(self, value: bool) -> None:
        self._expanded = value
        self._build()

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement
    # ------------------------------------------------------------------

    def _build_header_content(self, header, info_col) -> None:
        """Fill info_col with header content. May also bind header events."""
        raise NotImplementedError

    def _build_detail_content(self):
        """Return an optional widget to show below the header when expanded."""
        return None

    # ------------------------------------------------------------------
    # Overridable right-side slot
    # ------------------------------------------------------------------

    def _build_right_side(self, header) -> None:
        """Add the right-side widget to header. Default: chevron or spacer."""
        if self._show_chevron and self._on_expand:
            chevron = "chevron-up" if self._expanded else "chevron-down"
            header.add_widget(MDIconButton(
                icon=chevron,
                size_hint=(None, None),
                size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, fn=self._on_expand, ex=self._expanded: fn(not ex),
            ))
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(40)))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.clear_widgets()

        if self._has_hover:
            header = HoverRow(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(self._header_height),
                padding=[dp(8), dp(4)],
                spacing=dp(8),
            )
        else:
            header = RowHeader(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(self._header_height),
                padding=[dp(8), dp(4)],
                spacing=dp(8),
            )

        # Bind whole header click to on_expand (for PackageHeaderWidget-style rows)
        if self._expand_on_header and self._on_expand:
            _fn = self._on_expand
            _ex = self._expanded
            header.bind(on_touch_down=lambda w, t, fn=_fn, ex=_ex: (
                fn(not ex) if w.collide_point(*t.pos) else None
            ))

        # --- Checkbox (change-detection guard) ---
        if self._checked is not None:
            _initial = bool(self._checked)
            cb = MDCheckbox(
                size_hint=(None, None),
                size=(dp(24), dp(24)),
                pos_hint={"center_y": 0.5},
            )
            cb.active = _initial
            if self._on_check:
                def _guard(inst, val, fn=self._on_check, was=_initial):
                    if val != was:
                        fn(val)
                cb.bind(active=_guard)
            header.add_widget(cb)
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(24)))

        # --- Info column (filled by subclass) ---
        info_col = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            size_hint=(1, 1),
        )
        self._build_header_content(header, info_col)
        header.add_widget(info_col)

        # --- Action buttons ---
        for act in self._actions:
            btn = MDIconButton(
                icon=act.get("icon", "dots-vertical"),
                size_hint=(None, None),
                size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, cb=act.get("callback"): cb() if cb else None,
            )
            header.add_widget(btn)

        # --- Right side (chevron / "Open" / spacer) ---
        self._build_right_side(header)

        self.add_widget(header)

        # --- Detail panel (when expanded) ---
        if self._expanded:
            detail = self._build_detail_content()
            if detail is not None:
                self.add_widget(detail)
