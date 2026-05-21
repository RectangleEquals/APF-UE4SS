"""
DocsController — builds doc SPA HTML and dispatches to html_viewer service.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from ....core.controllers.plugin_host import PluginHost

_PLUGIN_DIR = Path(__file__).parent.parent   # plugins/docs_viewer/
_REPO_ROOT  = _PLUGIN_DIR.parent.parent.parent.parent  # ipc_2/


def _get_framework_version() -> str:
    cmake_path = _REPO_ROOT / "CMakeLists.txt"
    try:
        m = re.search(
            r'project\s*\(\s*APFramework\s+VERSION\s+([\d.]+)',
            cmake_path.read_text(encoding="utf-8"),
        )
        if m:
            return m.group(1)
    except Exception as exc:
        logger.debug("[docs] Framework version not readable from CMakeLists.txt: %s", exc)
    try:
        from ...__version__ import __framework_version__
        if __framework_version__ and __framework_version__ != "?":
            return __framework_version__
    except Exception as exc:
        logger.debug("[docs] __framework_version__ not available: %s", exc)
    return "?"


def _load_plugin_meta() -> dict:
    meta_path = _PLUGIN_DIR / "plugin.json"
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[docs] Failed to load plugin.json: %s", exc)
        return {}


def _load_spa_template() -> str:
    return (_PLUGIN_DIR / "assets" / "docs_spa.html").read_text(encoding="utf-8")


def _load_github_css() -> str:
    css_path = _PLUGIN_DIR / "assets" / "github-markdown-dark.css"
    if css_path.exists():
        try:
            return css_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.debug("[docs] Failed to load github-markdown-dark.css: %s", exc)
    return ""


class DocsController:
    def __init__(self, host: "PluginHost") -> None:
        self._host = host
        self._api = None
        self._docs_svc = None
        self._meta = _load_plugin_meta()

    # -----------------------------------------------------------------------
    # Public operations
    # -----------------------------------------------------------------------

    def open(
        self,
        path: str | None = None,
        initial_path: str | None = None,
        force_dev_docs: bool = False,
        sidebar_mode: str = "default",
        show_mode_toggle: bool = True,
    ) -> None:
        viewer = self._html_viewer()
        if viewer is None:
            logger.warning("html_viewer service not available")
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

    def open_local_spa(
        self,
        path: str,
        title: str = "",
        sidebar_mode: str = "default",
        show_mode_toggle: bool = True,
        show_sidebar: bool = True,
    ) -> None:
        viewer = self._html_viewer()
        if viewer is None:
            logger.warning("html_viewer service not available")
            return

        from ..models.html_builder import convert_body

        p = Path(path)
        display_title = title or p.stem.replace("_", " ").title()
        try:
            md_text = p.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to read {path}: {exc}")
            md_text = f"_Could not load `{path}`: {exc}_"

        doc_key = str(p)
        body_html = convert_body(md_text)

        tree_json = json.dumps(
            [{"display_name": display_title, "path": doc_key,
              "download_url": "", "section": "", "commit": "", "commit_url": ""}],
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

        viewer.show(display_title, spa_html, width=1100, height=780, inject_titlebar=False)

    def open_url(
        self,
        url: str,
        title: str = "",
        show_sidebar: bool = False,
        show_mode_toggle: bool = False,
        sidebar_mode: str = "verbose",
    ) -> None:
        from ..models.html_builder import convert_body

        viewer = self._html_viewer()
        if viewer is None:
            logger.warning("html_viewer service not available")
            return

        try:
            parts = url.replace("https://raw.githubusercontent.com/", "").split("/", 2)
            r_owner, r_repo = parts[0], parts[1]
        except (IndexError, ValueError):
            r_owner, r_repo = "unknown", "unknown"

        is_cached = [False]

        def _silent_status(level: str, msg: str) -> None:
            if level == "rate_limit_exceeded":
                return
            if level == "warn" and "cached version" in msg:
                is_cached[0] = True
                return
            self._on_api_status(level, msg)

        from ....core.controllers.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
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
            [{"display_name": display_title, "path": doc_key,
              "download_url": url, "section": "", "commit": "", "commit_url": ""}],
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
            titlebar_text=display_title,
        )

        viewer.show(display_title, spa_html, width=1000, height=750, inject_titlebar=False)

    def show_inline(
        self,
        content: str,
        title: str = "Release Notes",
        sidebar_mode: str = "verbose",
        allow_mode_toggle: bool = False,
    ) -> None:
        viewer = self._html_viewer()
        if viewer is None:
            logger.warning("html_viewer service not available")
            return
        from ..models.html_builder import convert_body
        body_html = convert_body(content or "_No content available._")
        doc_key = "inline"
        tree_json = json.dumps(
            [{"display_name": title, "path": doc_key,
              "download_url": "", "section": "", "commit": "", "commit_url": ""}],
            ensure_ascii=False,
        ).replace("</", "<\\/")
        docs_html_json = json.dumps({doc_key: body_html}, ensure_ascii=False).replace("</", "<\\/")
        spa_html = self._build_spa_html(
            tree_json=tree_json,
            docs_html_json=docs_html_json,
            fw_version=_get_framework_version(),
            sidebar_mode=sidebar_mode,
            show_mode_toggle=allow_mode_toggle,
            initial_path=doc_key,
            show_sidebar=True,
            titlebar_text=title,
        )
        viewer.show(title, spa_html, width=1000, height=750, inject_titlebar=False)

    # -----------------------------------------------------------------------
    # Private — view modes
    # -----------------------------------------------------------------------

    def _open_local_file(self, viewer, path: Path) -> None:
        from ..models.html_builder import convert
        try:
            md_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to read local file {path}: {exc}")
            md_text = f"_Could not load `{path}`: {exc}_"
        title = path.stem.replace("_", " ").title()
        html = convert(md_text, title=title)
        viewer.show(title, html)

    def _open_remote_file(self, viewer, repo_path: str) -> None:
        from ..models.html_builder import convert
        docs_svc = self._get_docs_svc()
        entry = docs_svc.get_entry_by_path(repo_path)
        if entry is None:
            docs_svc.get_tree(force_refresh=True)
            entry = docs_svc.get_entry_by_path(repo_path)
        if entry is None:
            logger.warning(f"Entry not found: {repo_path}")
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
        from ..models.html_builder import convert_body
        from .service import DocsService

        if force_dev_docs and not self._host.dev_mode:
            docs_svc = DocsService(api=self._get_api(), dev_mode=True)
        else:
            docs_svc = self._get_docs_svc()

        try:
            tree = docs_svc.get_tree()
        except Exception as exc:
            logger.error(f"Failed to fetch doc tree: {exc}")
            tree = []

        docs_html: dict[str, str] = {}
        for entry in tree:
            try:
                md_text = docs_svc.fetch_content(entry)
                docs_html[entry.path] = convert_body(md_text) if md_text else ""
            except Exception as exc:
                logger.error(f"Failed to render {entry.path}: {exc}")
                docs_html[entry.path] = (
                    '<div class="state-msg error">Failed to load this document.</div>'
                )

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
                except Exception as exc:
                    logger.debug("[docs] Failed to get git log for %s: %s", entry.path, exc)

        fw_version = _get_framework_version()

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

        viewer.show("Documentation", spa_html, width=1100, height=780, inject_titlebar=False)

    # -----------------------------------------------------------------------
    # Private — lazy accessors + helpers
    # -----------------------------------------------------------------------

    def _get_api(self):
        if self._api is None:
            from ....core.controllers.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
            repo_owner = self._meta.get("repo_owner", "")
            repo_name  = self._meta.get("repo_name", "")
            self._api = GitHubAPI(
                repo_owner=repo_owner,
                repo_name=repo_name,
                token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
                on_status=self._on_api_status,
            )
        return self._api

    def _get_docs_svc(self):
        if self._docs_svc is None:
            from .service import DocsService
            self._docs_svc = DocsService(
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
        if level in ("debug",):
            logger.debug(message)
        elif level in ("error", "rate_limit_exceeded", "rate_limit_exceeded_search"):
            logger.warning(f"[{level.upper()}] {message}")
        else:
            logger.info(f"[{level.upper()}] {message}")
