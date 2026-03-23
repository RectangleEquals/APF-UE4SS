"""
MarkdownRenderer — render a Markdown string as KivyMD widgets.

Supported elements:
    # / ## / ###    Headings (H1, H2, H3)
    **bold**        Bold text
    *italic*        Italic text
    `code`          Inline code (monospace label)
    ```...```       Fenced code blocks
    - / * item      Unordered list items
    ---             Horizontal rule (divider)
    Plain paragraphs

Returns a MDBoxLayout (vertical) containing the rendered widgets.
"""

from __future__ import annotations

import re

from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel


_CODE_BG = (0.10, 0.10, 0.10, 1)
_CODE_COLOR = (0.65, 0.85, 0.65, 1)


def render_markdown(text: str) -> MDBoxLayout:
    """Parse markdown text and return a vertical MDBoxLayout of widgets."""
    container = MDBoxLayout(
        orientation="vertical",
        size_hint_y=None,
        adaptive_height=True,
        spacing=dp(4),
        padding=[dp(4), 0],
    )

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            container.add_widget(_code_block("\n".join(code_lines)))
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}\s*$", line.strip()):
            container.add_widget(MDDivider(size_hint=(1, None), height=dp(1)))
            i += 1
            continue

        # Headings
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            style, role = {
                1: ("Headline", "medium"),
                2: ("Headline", "small"),
                3: ("Title", "large"),
            }[level]
            container.add_widget(_label(heading_text, style, role))
            i += 1
            continue

        # List item
        if re.match(r"^[-*]\s+", line):
            item_text = re.sub(r"^[-*]\s+", "• ", line)
            container.add_widget(_paragraph(_inline(item_text)))
            i += 1
            continue

        # Blank line
        if not line.strip():
            container.add_widget(Widget(size_hint=(1, None), height=dp(6)))
            i += 1
            continue

        # Paragraph (collect consecutive non-special lines)
        para_lines = []
        while i < len(lines):
            l = lines[i]
            if (
                not l.strip()
                or re.match(r"^#{1,3}\s", l)
                or re.match(r"^[-*]\s+", l)
                or l.strip().startswith("```")
                or re.match(r"^[-*_]{3,}\s*$", l.strip())
            ):
                break
            para_lines.append(l)
            i += 1
        text_block = " ".join(para_lines)
        container.add_widget(_paragraph(_inline(text_block)))

    return container


def _inline(text: str) -> str:
    """Convert inline markdown to KivyMD markup."""
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"[b]\1[/b]", text)
    text = re.sub(r"__(.+?)__", r"[b]\1[/b]", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"[i]\1[/i]", text)
    text = re.sub(r"_(.+?)_", r"[i]\1[/i]", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"[font=RobotoMono-Regular][color=#88cc88]\1[/color][/font]", text)
    return text


def _label(text: str, font_style: str, role: str = "medium") -> MDLabel:
    return MDLabel(
        text=text,
        font_style=font_style,
        role=role,
        size_hint=(1, None),
        height=dp(36) if (font_style == "Headline" and role == "medium") else dp(30),
        halign="left",
        valign="middle",
    )


def _paragraph(markup_text: str) -> MDLabel:
    return MDLabel(
        text=markup_text,
        markup=True,
        size_hint=(1, None),
        text_size=(None, None),
        halign="left",
        valign="top",
        adaptive_height=True,
    )


def _code_block(code: str) -> MDBoxLayout:
    box = MDBoxLayout(
        orientation="vertical",
        size_hint=(1, None),
        adaptive_height=True,
        padding=[dp(8), dp(6)],
        md_bg_color=_CODE_BG,
    )
    box.add_widget(MDLabel(
        text=code,
        font_style="Body",
        size_hint=(1, None),
        adaptive_height=True,
        theme_text_color="Custom",
        text_color=_CODE_COLOR,
    ))
    return box
