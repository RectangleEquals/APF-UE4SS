"""
ui/panels/palette_panel.py

Scrollable block palette — left sidebar shown beside the logic canvas.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDFlatButton

from ...core.manifest_model import ManifestModel
from ...core.mod_registry import ModRegistry

if TYPE_CHECKING:
    from ..canvas.logic_canvas import LogicCanvas

_CHIP_COLORS = {
    "item":      (0.29, 0.56, 0.89, 1),
    "can_access":(0.48, 0.41, 0.93, 1),
    "option":    (0.96, 0.65, 0.14, 1),
    "and":       (0.18, 0.25, 0.34, 1),
    "or":        (0.43, 0.36, 0.59, 1),
    "const":     (0.36, 0.72, 0.36, 1),
}

_SCOPE_ALLOWED = {
    "region":        {"item", "can_access", "option", "and", "or", "const"},
    "location":      {"item", "can_access", "option", "and", "or", "const"},
    "item":          {"option", "and", "or", "const"},
    "item_override": {"option", "and", "or", "const"},
}


class _Chip(MDFlatButton):
    def __init__(self, label: str, node_type: str, drop_kwargs: dict,
                 canvas: "LogicCanvas", allowed: bool = True, **kwargs):
        r, g, b, a = _CHIP_COLORS.get(node_type, (0.5, 0.5, 0.5, 1))
        super().__init__(
            text=label,
            size_hint=(1, None),
            height=dp(40),
            md_bg_color=(r, g, b, a if allowed else 0.3),
            **kwargs,
        )
        self._node_type   = node_type
        self._drop_kwargs = drop_kwargs
        self._canvas      = canvas
        self._allowed     = allowed
        if not allowed:
            self.disabled = True

    def on_release(self):
        if not self._allowed or self._canvas is None:
            return
        w = self._canvas
        cx = w.x + w.width  * 0.5
        cy = w.y + w.height * 0.5
        w.drop_block(self._node_type, x=cx, y=cy, **self._drop_kwargs)


def _section_header(text: str) -> MDLabel:
    return MDLabel(
        text=text,
        font_style="Overline",
        theme_text_color="Hint",
        size_hint_y=None,
        height=dp(28),
        padding=(dp(4), 0),
    )


class PalettePanel(BoxLayout):
    def __init__(
        self,
        model: ManifestModel,
        registry: ModRegistry,
        canvas: Optional["LogicCanvas"],
        scope: str = "region",
        **kwargs,
    ):
        # Strip any width/size_hint_x from kwargs before passing to super —
        # we set them as attributes after __init__ to avoid the Kivy
        # "multiple values for keyword argument 'width'" error.
        kwargs.pop("width", None)
        kwargs.pop("size_hint_x", None)
        kwargs.pop("size_hint", None)
        super().__init__(orientation="vertical", **kwargs)
        self.size_hint_x = None
        self.width = dp(220)

        self._model    = model
        self._registry = registry
        self._canvas   = canvas
        self._scope    = scope
        self._allowed  = _SCOPE_ALLOWED.get(scope, set())
        self._build()

    def _build(self):
        self.add_widget(MDLabel(
            text="Block Palette",
            font_style="Caption",
            bold=True,
            size_hint_y=None,
            height=dp(36),
            halign="center",
        ))

        scroll = ScrollView()
        lst = BoxLayout(orientation="vertical", spacing=dp(2),
                        padding=(dp(6), dp(4)), size_hint_y=None)
        lst.bind(minimum_height=lst.setter("height"))
        scroll.add_widget(lst)
        self.add_widget(scroll)

        lst.add_widget(_section_header(f"▾ THIS MOD  ({self._model.mod_id})"))

        for region in (self._model.capabilities.regions or []):
            lst.add_widget(self._chip(
                f"⬤ Can Access: {region.name}", "can_access",
                dict(region_name=region.name),
            ))
        for item in (self._model.capabilities.items or []):
            lst.add_widget(self._chip(
                f"▪ Item: {item.name}", "item",
                dict(item_name=item.name),
            ))
        for opt_key in (self._model.options or {}).keys():
            lst.add_widget(self._chip(
                f"⚙ Option: {opt_key}", "option",
                dict(option_key=opt_key),
            ))

        lst.add_widget(_section_header("▾ LOGIC OPERATORS"))
        lst.add_widget(self._chip("& AND", "and", {}))
        lst.add_widget(self._chip("| OR",  "or",  {}))

        lst.add_widget(_section_header("▾ CONSTANTS"))
        lst.add_widget(self._chip("✓ True",  "const", dict(const_value=True)))
        lst.add_widget(self._chip("✗ False", "const", dict(const_value=False)))

    def _chip(self, label: str, node_type: str, drop_kwargs: dict) -> _Chip:
        return _Chip(
            label=label,
            node_type=node_type,
            drop_kwargs=drop_kwargs,
            canvas=self._canvas,
            allowed=node_type in self._allowed,
        )
