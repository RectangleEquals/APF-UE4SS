"""
Markdown → HTML conversion utilities.

convert(md_text)       — full standalone HTML document (for simple single-doc viewing)
convert_body(md_text)  — HTML body fragment only (for SPA content injection)
"""

from __future__ import annotations

import logging
from pathlib import Path

import markdown as _md

_log = logging.getLogger(__name__)

_CSS_PATH = Path(__file__).parent.parent / "assets" / "github-markdown-dark.css"

_BASE_STYLES = """
* { box-sizing: border-box; }
body {
  background: #0d1117;
  color: #e6edf3;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 32px 48px;
}
.markdown-body a { color: #58a6ff; }
.markdown-body a:hover { text-decoration: underline; }
pre { overflow-x: auto; }
"""

_EXTENSIONS = ["tables", "fenced_code", "codehilite", "toc", "nl2br"]
_EXTENSION_CONFIGS = {
    "codehilite": {"guess_lang": False, "css_class": "highlight"},
}


def _load_css() -> str:
    if _CSS_PATH.exists():
        try:
            return _CSS_PATH.read_text(encoding="utf-8")
        except Exception as exc:
            _log.debug("[html_builder] Failed to load CSS: %s", exc)
    return ""


def convert_body(md_text: str) -> str:
    """Convert markdown → HTML fragment (body only). Used in SPA content injection."""
    return _md.markdown(
        md_text,
        extensions=_EXTENSIONS,
        extension_configs=_EXTENSION_CONFIGS,
    )


def convert(md_text: str, title: str = "Documentation") -> str:
    """Convert markdown → full standalone HTML document."""
    body = convert_body(md_text)
    css = _load_css()
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{_BASE_STYLES}</style>
<style>{css}</style>
</head>
<body class="markdown-body">
{body}
</body>
</html>"""
