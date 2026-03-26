"""
DocsPanel — GitHub-backed documentation browser for APF Manager.

Two modes of operation:
  1. Remote browse (default): fetches doc tree from GitHub, renders in an SPA
     pywebview window with sidebar navigation.
  2. Local file: reads a local .md path directly and opens it in a simple
     pywebview window (used by the deploy panel Setup Guide button).

Usage:
    panel = DocsPanel(host)
    panel.open()                         # remote browse, default entry
    panel.open(path="docs/public/README.md")  # remote path (repo-relative)
    panel.open(path="C:\\...\\setup.md")  # absolute local file
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost

_HERE = Path(__file__).parent


def _load_plugin_meta() -> dict:
    """Read plugin.json from this plugin's directory."""
    meta_path = _HERE / "plugin.json"
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_spa_template() -> str:
    """Load the docs_spa.html template from this plugin's directory."""
    return (_HERE / "docs_spa.html").read_text(encoding="utf-8")


def _load_github_css() -> str:
    """Load the bundled GitHub Markdown dark CSS."""
    css_path = _HERE / "assets" / "github-markdown-dark.css"
    if css_path.exists():
        try:
            return css_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------------------
# DocsPanel
# ---------------------------------------------------------------------------

class DocsPanel:
    """
    Provides the docs_viewer service interface.
    Registered as both a service and dialog contribution by setup().
    """

    def __init__(self, host: "PluginHost") -> None:
        self._host = host
        self._api = None        # GitHubAPI — lazy init
        self._docs_svc = None   # GitHubDocsService — lazy init
        self._meta = _load_plugin_meta()

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def open(self, path: str | None = None) -> None:
        """
        Open documentation.

        path=None          → remote SPA browser (fetches tree from GitHub)
        path="docs/..."    → remote single-file view (repo-relative path)
        path="C:\\..."     → local file view (absolute filesystem path)
        """
        viewer = self._html_viewer()
        if viewer is None:
            self._host.log("[docs_viewer] html_viewer service not available")
            return

        if path is not None:
            p = Path(path)
            if p.is_absolute() and p.exists():
                self._open_local_file(viewer, p)
            else:
                self._open_remote_file(viewer, path)
        else:
            self._open_spa(viewer)

    # -----------------------------------------------------------------------
    # Private — view modes
    # -----------------------------------------------------------------------

    def _open_local_file(self, viewer, path: Path) -> None:
        """Read a local .md file and render it in a simple HTML viewer window."""
        from .md_to_html import convert
        try:
            md_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            self._host.log(f"[docs_viewer] Failed to read local file: {exc}")
            md_text = f"_Could not load `{path}`: {exc}_"
        title = path.stem.replace("_", " ").title()
        html = convert(md_text, title=title)
        viewer.show(title, html)

    def _open_remote_file(self, viewer, repo_path: str) -> None:
        """Fetch a single remote doc and render it in a simple HTML viewer window."""
        from .md_to_html import convert
        api = self._get_api()
        docs_svc = self._get_docs_svc()
        entry = docs_svc.get_entry_by_path(repo_path)
        if entry is None:
            # Try fetching tree first, then retry
            docs_svc.get_tree(force_refresh=True)
            entry = docs_svc.get_entry_by_path(repo_path)
        if entry is None:
            self._host.log(f"[docs_viewer] Entry not found: {repo_path}")
            return
        md_text = docs_svc.fetch_content(entry)
        title = entry.display_name
        html = convert(md_text, title=title)
        viewer.show(title, html)

    def _open_spa(self, viewer) -> None:
        """
        Build and open the SPA docs browser window.

        Embeds the full doc tree as JSON and the GitHub CSS into the template,
        then launches via html_viewer with inject_titlebar=False (the SPA has
        its own title bar) and a _DocsAPI as extra_api.
        """
        docs_svc = self._get_docs_svc()

        try:
            tree = docs_svc.get_tree()
        except Exception as exc:
            self._host.log(f"[docs_viewer] Failed to fetch doc tree: {exc}")
            tree = []

        # Serialize tree for JS embedding
        tree_json = json.dumps(
            [
                {
                    "display_name": e.display_name,
                    "path": e.path,
                    "download_url": e.download_url,
                    "section": e.section,
                }
                for e in tree
            ],
            ensure_ascii=False,
        )

        github_css = _load_github_css()
        template = _load_spa_template()
        spa_html = template.replace("{TREE_JSON}", tree_json).replace("{GITHUB_CSS}", github_css)

        docs_api = _DocsAPI(docs_svc, self._host)

        def _on_refresh():
            """Called when user clicks Refresh in the SPA."""
            docs_svc.invalidate()

        viewer.show(
            "Documentation",
            spa_html,
            width=1100,
            height=780,
            extra_api=docs_api,
            inject_titlebar=False,
        )

    # -----------------------------------------------------------------------
    # Private — lazy service accessors
    # -----------------------------------------------------------------------

    def _get_api(self):
        if self._api is None:
            from ...core.remote.github_api import GitHubAPI

            repo_owner = self._meta.get("repo_owner", "")
            repo_name = self._meta.get("repo_name", "")
            token_path = _HERE / ".github_token"

            self._api = GitHubAPI(
                repo_owner=repo_owner,
                repo_name=repo_name,
                token_file_path=token_path if token_path.exists() else None,
                on_status=self._on_api_status,
            )
        return self._api

    def _get_docs_svc(self):
        if self._docs_svc is None:
            from .github_docs import GitHubDocsService

            self._docs_svc = GitHubDocsService(
                api=self._get_api(),
                dev_mode=self._host.dev_mode,
            )
        return self._docs_svc

    def _html_viewer(self):
        if self._host.has_service("html_viewer"):
            return self._host.get_service("html_viewer")
        return None

    def _on_api_status(self, level: str, message: str) -> None:
        self._host.log(f"[docs_viewer] [{level.upper()}] {message}")
        # TODO: wire up MDSnackbar notification when Snackbar service is available


# ---------------------------------------------------------------------------
# JavaScript API exposed to the SPA
# ---------------------------------------------------------------------------

class _DocsAPI:
    """
    Methods exposed to JavaScript via pywebview js_api.

    html_viewer merges these with its own close() method.
    JavaScript calls: await pywebview.api.get_doc_html(path)
                      pywebview.api.open_url(url)
                      pywebview.api.refresh()
    """

    def __init__(self, docs_svc, host) -> None:
        self._svc = docs_svc
        self._host = host

    def get_doc_html(self, path: str) -> str:
        """
        Fetch a doc by its repo-relative path and return rendered HTML fragment.
        Called by the SPA when the user clicks a sidebar entry.
        """
        from .md_to_html import convert_body

        try:
            entry = self._svc.get_entry_by_path(path)
            if entry is None:
                return f'<div class="state-msg error">Document not found: <code>{path}</code></div>'

            md_text = self._svc.fetch_content(entry)
            if not md_text:
                return '<div class="state-msg error">Document is empty or unavailable.</div>'

            return convert_body(md_text)

        except Exception as exc:
            self._host.log(f"[docs_viewer] get_doc_html error: {exc}")
            return f'<div class="state-msg error">Failed to load document.<br><small>{exc}</small></div>'

    def open_url(self, url: str) -> None:
        """Open an external URL in the system's default browser."""
        try:
            if url.startswith("http://") or url.startswith("https://"):
                webbrowser.open(url)
        except Exception as exc:
            self._host.log(f"[docs_viewer] open_url error: {exc}")

    def refresh(self) -> None:
        """Invalidate the cache so the next tree/content fetch goes to GitHub."""
        try:
            self._svc.invalidate()
        except Exception as exc:
            self._host.log(f"[docs_viewer] refresh error: {exc}")
