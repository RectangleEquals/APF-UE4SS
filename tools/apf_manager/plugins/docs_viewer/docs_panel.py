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
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent.parent.parent  # tools/apf_manager/plugins/docs_viewer → ipc_2/


def _get_framework_version() -> str:
    """Read framework version from CMakeLists.txt, fall back to __version__ in frozen builds."""
    cmake_path = _REPO_ROOT / "CMakeLists.txt"
    try:
        m = re.search(
            r'project\s*\(\s*APFramework\s+VERSION\s+([\d.]+)',
            cmake_path.read_text(encoding="utf-8"),
        )
        if m:
            return m.group(1)
    except Exception:
        pass
    # Frozen fallback: setup.py bakes __framework_version__ into __version__.py
    try:
        from ...__version__ import __framework_version__
        if __framework_version__ and __framework_version__ != "?":
            return __framework_version__
    except Exception:
        pass
    return "?"


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

    def open_local_spa(
        self,
        path: str,
        title: str = "",
        sidebar_mode: str = "default",
        show_mode_toggle: bool = True,
        show_sidebar: bool = True,
    ) -> None:
        """
        Open a local .md file in the full SPA viewer (sidebar, search, back/forward).

        Reads the file from disk, converts it, and builds a minimal single-item
        TREE so the SPA loads with navigation chrome — no GitHub fetch needed.

        sidebar_mode: "default" (titles only) | "verbose" (flat heading anchors) |
                      "tree" (collapsible H1→H2→H3 hierarchy). Default: "default".
        show_mode_toggle: whether to show the Default/Verbose/Tree chips in the
                          sidebar footer so the user can switch modes. Default: True.
        show_sidebar: whether to show the left sidebar. Default: True.
        """
        viewer = self._html_viewer()
        if viewer is None:
            self._host.log("[docs_viewer] html_viewer service not available")
            return

        from .md_to_html import convert_body

        p = Path(path)
        display_title = title or p.stem.replace("_", " ").title()
        try:
            md_text = p.read_text(encoding="utf-8")
        except Exception as exc:
            self._host.log(f"[docs_viewer] Failed to read {path}: {exc}")
            md_text = f"_Could not load `{path}`: {exc}_"

        doc_key = str(p)
        body_html = convert_body(md_text)

        tree_json = json.dumps(
            [
                {
                    "display_name": display_title,
                    "path": doc_key,
                    "download_url": "",
                    "section": "",
                    "commit": "",
                    "commit_url": "",
                }
            ],
            ensure_ascii=False,
        ).replace("</", "<\\/")

        docs_html_json = json.dumps(
            {doc_key: body_html}, ensure_ascii=False
        ).replace("</", "<\\/")

        spa_html = self._build_spa_html(
            tree_json=tree_json,
            docs_html_json=docs_html_json,
            fw_version=_get_framework_version(),
            sidebar_mode=sidebar_mode,
            show_mode_toggle=show_mode_toggle,
            initial_path=doc_key,
            show_sidebar=show_sidebar,
        )

        viewer.show(
            display_title,
            spa_html,
            width=1100,
            height=780,
            inject_titlebar=False,
        )

    def open_url(
        self,
        url: str,
        title: str = "",
        show_sidebar: bool = False,
        show_mode_toggle: bool = False,
    ) -> None:
        """
        Fetch a remote markdown document by raw URL and open it in the SPA viewer.

        Defaults to no sidebar and no mode toggle — appropriate for single-doc views
        like mod documentation. Falls back to opening in the system browser on fetch
        failure.

        url: raw URL to a .md file (e.g. raw.githubusercontent.com/…/README.md)
        title: window + title bar label; derived from URL filename if empty
        show_sidebar: whether to show the left nav sidebar. Default: False.
        show_mode_toggle: whether to show the sidebar mode chips. Default: False.
        """
        from .md_to_html import convert_body

        viewer = self._html_viewer()
        if viewer is None:
            self._host.log("[docs_viewer] html_viewer service not available")
            return

        # Parse owner/repo from raw.githubusercontent.com URL for cache namespacing.
        # e.g. https://raw.githubusercontent.com/owner/repo/branch/path/README.md
        try:
            parts = url.replace("https://raw.githubusercontent.com/", "").split("/", 2)
            r_owner, r_repo = parts[0], parts[1]
        except (IndexError, ValueError):
            r_owner, r_repo = "unknown", "unknown"

        is_cached = [False]

        def _silent_status(level: str, msg: str) -> None:
            if level == "rate_limit_exceeded":
                return  # doc fetch failure is silent — fall back to cache
            if level == "warn" and "cached version" in msg:
                is_cached[0] = True
                return  # "(cached)" will appear in title bar instead
            self._on_api_status(level, msg)

        from ...core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
        _api = GitHubAPI(
            repo_owner=r_owner,
            repo_name=r_repo,
            token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
            on_status=_silent_status,
        )
        md_text = _api.fetch_text(url, force_refresh=True)
        if not md_text:
            import webbrowser
            webbrowser.open(url)
            return

        display_title = (
            title or url.split("/")[-1].replace(".md", "").replace("-", " ").replace("_", " ").title()
        )
        if is_cached[0]:
            display_title = f"{display_title} (cached)"
        body_html = convert_body(md_text)
        doc_key = url.split("/")[-1] or "readme.md"

        tree_json = json.dumps(
            [
                {
                    "display_name": display_title,
                    "path": doc_key,
                    "download_url": url,
                    "section": "",
                    "commit": "",
                    "commit_url": "",
                }
            ],
            ensure_ascii=False,
        ).replace("</", "<\\/")

        docs_html_json = json.dumps(
            {doc_key: body_html}, ensure_ascii=False
        ).replace("</", "<\\/")

        spa_html = self._build_spa_html(
            tree_json=tree_json,
            docs_html_json=docs_html_json,
            fw_version=_get_framework_version(),
            sidebar_mode="default",
            show_mode_toggle=show_mode_toggle,
            initial_path=doc_key,
            show_sidebar=show_sidebar,
            titlebar_text=display_title,
        )

        viewer.show(
            display_title,
            spa_html,
            width=1000,
            height=750,
            inject_titlebar=False,
        )

    def open(
        self,
        path: str | None = None,
        initial_path: str | None = None,
        force_dev_docs: bool = False,
        sidebar_mode: str = "default",
        show_mode_toggle: bool = True,
    ) -> None:
        """
        Open documentation.

        path=None          → remote SPA browser (fetches tree from GitHub)
        path="docs/..."    → remote single-file view (repo-relative path)
        path="C:\\..."     → local file view (absolute filesystem path)

        initial_path: when opening the SPA, pre-navigate to this repo-relative path.
        force_dev_docs: when True, include dev docs in the SPA tree even in player mode.
        sidebar_mode: "default" | "verbose" | "tree"
        show_mode_toggle: whether the mode chips appear in the sidebar footer
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
            self._open_spa(
                viewer,
                initial_path=initial_path,
                force_dev_docs=force_dev_docs,
                sidebar_mode=sidebar_mode,
                show_mode_toggle=show_mode_toggle,
                show_sidebar=True,
            )

    # -----------------------------------------------------------------------
    # Private — view modes
    # -----------------------------------------------------------------------

    def show_inline(
        self,
        content: str,
        title: str = "Release Notes",
        sidebar_mode: str = "verbose",
        allow_mode_toggle: bool = False,
    ) -> None:
        """Render an inline markdown string in the viewer (no file or network I/O)."""
        viewer = self._html_viewer()
        if viewer is None:
            self._host.log("[docs_viewer] html_viewer service not available")
            return
        from .md_to_html import convert
        html = convert(content or "_No content available._", title=title)
        viewer.show(title, html)

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

    def _open_spa(
        self,
        viewer,
        sidebar_mode: str = "default",
        show_mode_toggle: bool = True,
        initial_path: str | None = None,
        force_dev_docs: bool = False,
        show_sidebar: bool = True,
    ) -> None:
        """
        Build and open the SPA docs browser window.

        Pre-renders ALL docs to HTML bodies before opening the window. This is
        required because the viewer runs in a subprocess and cannot call back into
        the parent Python process. All content is embedded into the SPA HTML at
        launch time — no API calls from JS are needed for content loading.

        sidebar_mode: "default" | "verbose" | "tree"
        show_mode_toggle: whether the mode chips appear in the sidebar footer
        initial_path: repo-relative doc path to navigate to on open (None = first entry)
        force_dev_docs: include dev docs even if host.dev_mode is False
        """
        from .md_to_html import convert_body

        if force_dev_docs and not self._host.dev_mode:
            from .github_docs import GitHubDocsService
            docs_svc = GitHubDocsService(api=self._get_api(), dev_mode=True)
        else:
            docs_svc = self._get_docs_svc()

        try:
            tree = docs_svc.get_tree()
        except Exception as exc:
            self._host.log(f"[docs_viewer] Failed to fetch doc tree: {exc}")
            tree = []

        # Pre-render all docs to HTML bodies
        docs_html: dict[str, str] = {}
        for entry in tree:
            try:
                md_text = docs_svc.fetch_content(entry)
                docs_html[entry.path] = convert_body(md_text) if md_text else ""
            except Exception as exc:
                self._host.log(f"[docs_viewer] Failed to render {entry.path}: {exc}")
                docs_html[entry.path] = (
                    '<div class="state-msg error">Failed to load this document.</div>'
                )

        # In dev mode, populate per-doc commit hashes via git log
        is_frozen = getattr(sys, "frozen", False)
        _owner = self._meta.get("repo_owner", "")
        _name  = self._meta.get("repo_name", "")
        repo_url = f"https://github.com/{_owner}/{_name}" if _owner and _name else ""
        if not is_frozen and (_REPO_ROOT / ".git").exists():
            for entry in tree:
                try:
                    h = subprocess.run(
                        ["git", "log", "-1", "--format=%H", "--", entry.path],
                        capture_output=True,
                        text=True,
                        cwd=str(_REPO_ROOT),
                    ).stdout.strip()
                    if h:
                        entry.commit = h[:7]
                        entry.commit_url = f"{repo_url}/commit/{h}" if repo_url else ""
                except Exception:
                    pass

        # Read framework version for title display
        fw_version = _get_framework_version()

        # Serialize for JS embedding; escape </ to prevent premature </script> closure
        tree_json = json.dumps(
            [
                {
                    "display_name": e.display_name,
                    "path": e.path,
                    "download_url": e.download_url,
                    "section": e.section,
                    "commit": e.commit,
                    "commit_url": e.commit_url,
                }
                for e in tree
            ],
            ensure_ascii=False,
        ).replace("</", "<\\/")

        docs_html_json = json.dumps(docs_html, ensure_ascii=False).replace("</", "<\\/")

        spa_html = self._build_spa_html(
            tree_json=tree_json,
            docs_html_json=docs_html_json,
            fw_version=fw_version,
            sidebar_mode=sidebar_mode,
            show_mode_toggle=show_mode_toggle,
            initial_path=initial_path or "",
            show_sidebar=show_sidebar,
        )

        viewer.show(
            "Documentation",
            spa_html,
            width=1100,
            height=780,
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
            from ...core.remote.github_api import _BUNDLED_TOKEN_PATH
            self._api = GitHubAPI(
                repo_owner=repo_owner,
                repo_name=repo_name,
                token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
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

    def _build_spa_html(
        self,
        tree_json: str,
        docs_html_json: str,
        fw_version: str,
        sidebar_mode: str = "default",
        show_mode_toggle: bool = True,
        initial_path: str = "",
        show_sidebar: bool = True,
        titlebar_text: str = "",
    ) -> str:
        """Build the full SPA HTML string by substituting all template placeholders."""
        github_css = _load_github_css()
        template = _load_spa_template()
        return (
            template
            .replace("{TREE_JSON}", tree_json)
            .replace("{DOCS_HTML_JSON}", docs_html_json)
            .replace("{GITHUB_CSS}", github_css)
            .replace("{FRAMEWORK_VERSION}", fw_version)
            .replace("{SIDEBAR_MODE}", sidebar_mode)
            .replace("{SHOW_MODE_TOGGLE}", "true" if show_mode_toggle else "false")
            .replace("{SHOW_SIDEBAR}", "true" if show_sidebar else "false")
            .replace("{INITIAL_PATH}", initial_path)
            .replace("{TITLEBAR_TEXT}", titlebar_text)
        )

    def _on_api_status(self, level: str, message: str) -> None:
        self._host.log(f"[docs_viewer] [{level.upper()}] {message}")
        # TODO: wire up MDSnackbar notification when Snackbar service is available

