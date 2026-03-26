"""
Markdown → HTML conversion utilities.

convert(md_text)       — full standalone HTML document (for simple single-doc viewing)
convert_body(md_text)  — HTML body fragment only (for SPA content injection)
"""

from __future__ import annotations

from pathlib import Path

import markdown as _md

_CSS_PATH = Path(__file__).parent / "assets" / "github-markdown-dark.css"

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
        except Exception:
            pass
    return ""


def convert_body(md_text: str) -> str:
    """Convert markdown → HTML fragment (body only). Used in SPA content injection."""
    return _md.markdown(
        md_text,
        extensions=_EXTENSIONS,
        extension_configs=_EXTENSION_CONFIGS,
    )


def convert(md_text: str, title: str = "") -> str:
    """Convert markdown → full standalone HTML document."""
    body = convert_body(md_text)
    github_css = _load_css()
    title_tag = f"<title>{title}</title>" if title else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{title_tag}
<style>
{_BASE_STYLES}
{github_css}
</style>
</head>
<body class="markdown-body">
{body}
</body>
</html>"""
