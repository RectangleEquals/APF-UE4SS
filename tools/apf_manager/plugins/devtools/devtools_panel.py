"""
DevToolsPanel — comprehensive developer hub for repo contributors.

Seven permission-aware sections:

  All users (logged out)  Section 1 (Account) + Section 2 (Dev Setup)
  Read-only               Adds Section 3 (Pull Requests)
  Write tier              Adds Sections 4-7 (Versions, Workflows, Releases, Branches)

All GitHub API calls run on background threads; UI updates are dispatched
back to the main thread via Clock.schedule_once.
All errors are logged via self._host.log("[devtools] ...") and shown in
per-section status labels.
"""

from __future__ import annotations

import json
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer, MDDialogContentContainer,
)
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivymd.uix.textfield import MDTextField

from ...gui.widgets.plugin_panel import PluginPanel
from .github_auth import GitHubAuth
from .ci_manager import CIManager
from . import version_manager as vm

if TYPE_CHECKING:
    from ...core.config import GameProfile

_HERE = Path(__file__).parent

_COMPONENTS = ("framework", "manager", "apworld")
_COMPONENT_LABELS = {
    "framework": "Framework",
    "manager":   "Manager",
    "apworld":   "Apworld",
}
_BUMP_PARTS = ["patch", "minor", "major"]


def _load_meta() -> dict:
    try:
        return json.loads((_HERE / "plugin.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


class DevToolsPanel(PluginPanel):

    def __init__(self, host, **kwargs):
        super().__init__(host=host, **kwargs)
        meta = _load_meta()
        self._repo_owner: str = meta.get("repo_owner", "")
        self._repo_name:  str = meta.get("repo_name", "")

        self._auth = GitHubAuth()
        self._ci   = CIManager(self._repo_owner, self._repo_name)

        # Per-component version state
        self._local_versions:  dict[str, Optional[str]] = {}
        self._remote_versions: dict[str, Optional[str]] = {}
        self._bump_parts:      dict[str, str]            = {c: "patch" for c in _COMPONENTS}

        # Widget refs (populated in _build_ui)
        self._account_card:   Optional[MDBoxLayout] = None
        self._pr_card:        Optional[MDBoxLayout] = None
        self._pr_branch_lbl:  Optional[MDLabel]     = None
        self._pr_title:       Optional[MDTextField] = None
        self._pr_body:        Optional[MDTextField] = None
        self._write_sections: list[MDBoxLayout]     = []

        self._version_rows:   dict[str, dict] = {}
        self._workflows_list: Optional[MDBoxLayout] = None
        self._releases_list:  Optional[MDBoxLayout] = None
        self._branches_list:  Optional[MDBoxLayout] = None

        self._status_labels:  dict[str, MDLabel]       = {}
        self._bump_menus:     dict[str, MDDropdownMenu] = {}

        self._login_dialog:   Optional[MDDialog] = None
        self._login_code_lbl: Optional[MDLabel]  = None

        self._build_ui()

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._refresh()

    def on_deactivate(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        sv = ScrollView(size_hint=(1, 1))
        root = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=dp(16),
            spacing=dp(12),
        )

        # --- Section 1: Account (always visible) ---
        self._account_card = self._make_card()
        root.add_widget(self._account_card)

        # --- Section 2: Dev Setup (always visible) ---
        setup_card = self._make_card()
        setup_card.add_widget(self._section_title("Dev Setup"))
        setup_btn = MDButton(MDButtonText(text="View Dev Environment Setup"))
        setup_btn.bind(on_release=lambda *_: self._open_setup_guide())
        setup_card.add_widget(setup_btn)
        root.add_widget(setup_card)

        # --- Section 3: Pull Requests (logged-in users, any tier) ---
        self._pr_card = self._make_card()
        self._pr_card.add_widget(self._section_title("Pull Requests"))
        self._pr_branch_lbl = MDLabel(
            text="Current branch: —",
            adaptive_height=True,
            theme_text_color="Secondary",
        )
        self._pr_title = MDTextField(hint_text="PR title", adaptive_height=True)
        self._pr_body  = MDTextField(
            hint_text="PR description (optional)",
            adaptive_height=True,
            multiline=True,
        )
        pr_btn = MDButton(MDButtonText(text="Open PR on GitHub"))
        pr_btn.bind(on_release=lambda *_: self._on_open_pr())
        self._pr_card.add_widget(self._pr_branch_lbl)
        self._pr_card.add_widget(self._pr_title)
        self._pr_card.add_widget(self._pr_body)
        self._pr_card.add_widget(pr_btn)
        root.add_widget(self._pr_card)

        # --- Section 4: Version Management (write only) ---
        ver_card = self._make_card()
        ver_card.add_widget(self._section_title("Version Management"))
        ver_card.add_widget(MDLabel(
            text=f"Repo: {vm._REPO_ROOT}",
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
        ))
        ver_card.add_widget(MDDivider())
        # Column headers
        hdr_row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        for txt, sx in [("Component", 0.15), ("Local", 0.18), ("Remote", 0.18),
                        ("Status", 0.15), ("Bump", 0.18), ("", None)]:
            lbl = MDLabel(text=txt, size_hint_x=sx, adaptive_height=True,
                          theme_text_color="Secondary", font_style="Body")
            if sx is None:
                lbl.size_hint_x = 0.16
            hdr_row.add_widget(lbl)
        ver_card.add_widget(hdr_row)
        for component in _COMPONENTS:
            ver_card.add_widget(self._make_version_row(component))
        self._status_labels["versions"] = self._make_status_lbl()
        ver_card.add_widget(self._status_labels["versions"])
        self._write_sections.append(ver_card)
        root.add_widget(ver_card)

        # --- Section 5: CI / Workflows (write only) ---
        wf_card = self._make_card()
        wf_hdr = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        wf_hdr.add_widget(self._section_title("CI / Workflows", inline=True))
        refresh_wf = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_wf.bind(on_release=lambda *_: self._refresh_workflows())
        wf_hdr.add_widget(refresh_wf)
        wf_card.add_widget(wf_hdr)
        self._workflows_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(4)
        )
        wf_card.add_widget(self._workflows_list)
        self._status_labels["workflows"] = self._make_status_lbl()
        wf_card.add_widget(self._status_labels["workflows"])
        self._write_sections.append(wf_card)
        root.add_widget(wf_card)

        # --- Section 6: Releases (write only) ---
        rel_card = self._make_card()
        rel_hdr = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        rel_hdr.add_widget(self._section_title("Releases", inline=True))
        refresh_rel = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_rel.bind(on_release=lambda *_: self._refresh_releases())
        rel_hdr.add_widget(refresh_rel)
        create_rel = MDButton(MDButtonText(text="Create Release"), size_hint_x=None)
        create_rel.bind(on_release=lambda *_: self._show_create_release_dialog())
        rel_hdr.add_widget(create_rel)
        rel_card.add_widget(rel_hdr)
        self._releases_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(4)
        )
        rel_card.add_widget(self._releases_list)
        self._status_labels["releases"] = self._make_status_lbl()
        rel_card.add_widget(self._status_labels["releases"])
        self._write_sections.append(rel_card)
        root.add_widget(rel_card)

        # --- Section 7: Branches (write only) ---
        br_card = self._make_card()
        br_hdr = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        br_hdr.add_widget(self._section_title("Branches", inline=True))
        refresh_br = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_br.bind(on_release=lambda *_: self._refresh_branches())
        br_hdr.add_widget(refresh_br)
        new_br = MDIconButton(icon="plus", size_hint_x=None, width=dp(36))
        new_br.bind(on_release=lambda *_: self._show_new_branch_dialog())
        br_hdr.add_widget(new_br)
        br_card.add_widget(br_hdr)
        self._branches_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(4)
        )
        br_card.add_widget(self._branches_list)
        self._status_labels["branches"] = self._make_status_lbl()
        br_card.add_widget(self._status_labels["branches"])
        self._write_sections.append(br_card)
        root.add_widget(br_card)

        sv.add_widget(root)
        self.add_widget(sv)

        self._refresh_auth_ui()

    # -----------------------------------------------------------------------
    # Widget factories
    # -----------------------------------------------------------------------

    def _make_card(self) -> MDBoxLayout:
        return MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=dp(12),
            spacing=dp(8),
        )

    def _section_title(self, text: str, inline: bool = False) -> MDLabel:
        lbl = MDLabel(
            text=text,
            font_style="Title",
            adaptive_height=True,
        )
        if inline:
            lbl.size_hint_x = 1
        return lbl

    def _make_status_lbl(self) -> MDLabel:
        return MDLabel(
            text="",
            adaptive_height=True,
            font_style="Body",
            theme_text_color="Secondary",
        )

    def _make_version_row(self, component: str) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal",
            adaptive_height=True,
            spacing=dp(8),
            padding=(0, dp(2), 0, dp(2)),
        )
        label      = MDLabel(text=_COMPONENT_LABELS[component], size_hint_x=0.15, adaptive_height=True)
        local_lbl  = MDLabel(text="—", size_hint_x=0.18, adaptive_height=True, theme_text_color="Secondary")
        remote_lbl = MDLabel(text="—", size_hint_x=0.18, adaptive_height=True, theme_text_color="Secondary")
        status_lbl = MDLabel(text="", size_hint_x=0.15, adaptive_height=True)
        bump_btn   = MDButton(MDButtonText(text="patch ▾"), size_hint_x=0.18)
        bump_btn.bind(on_release=lambda btn, c=component: self._open_bump_menu(btn, c))
        commit_btn = MDButton(MDButtonText(text="Commit & Tag"), size_hint_x=None)
        commit_btn.bind(on_release=lambda *_, c=component: self._on_commit_tag(c))

        self._version_rows[component] = {
            "local_lbl":  local_lbl,
            "remote_lbl": remote_lbl,
            "status_lbl": status_lbl,
            "bump_btn":   bump_btn,
            "commit_btn": commit_btn,
        }
        for w in (label, local_lbl, remote_lbl, status_lbl, bump_btn, commit_btn):
            row.add_widget(w)
        return row

    # -----------------------------------------------------------------------
    # Status helper (main-thread only)
    # -----------------------------------------------------------------------

    def _set_status(self, section: str, msg: str, ok: bool = True) -> None:
        lbl = self._status_labels.get(section)
        if not lbl:
            return
        lbl.text = msg
        lbl.theme_text_color = "Custom"
        lbl.text_color = (0.2, 0.8, 0.2, 1) if ok else (0.9, 0.3, 0.3, 1)

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def _refresh(self) -> None:
        branch = vm.get_current_branch()
        if branch and self._pr_branch_lbl:
            self._pr_branch_lbl.text = f"Current branch: {branch}"

        if self._auth.is_logged_in:
            self._auth.refresh_async(
                self._repo_owner, self._repo_name,
                on_complete=lambda ok: Clock.schedule_once(
                    lambda dt: self._on_auth_refresh(ok)
                ),
            )
        else:
            self._refresh_auth_ui()

    def _on_auth_refresh(self, ok: bool) -> None:
        self._refresh_auth_ui()
        if ok and self._auth.is_write_tier:
            self._refresh_versions()
            self._refresh_workflows()
            self._refresh_releases()
            self._refresh_branches()

    def _refresh_auth_ui(self) -> None:
        card = self._account_card
        card.clear_widgets()

        logged_in  = self._auth.is_logged_in
        write_tier = self._auth.is_write_tier

        if not logged_in:
            card.add_widget(MDLabel(
                text="Sign in to GitHub to enable contribution tools and developer features.",
                adaptive_height=True,
                theme_text_color="Secondary",
            ))
            login_btn = MDButton(MDButtonText(text="Sign In with GitHub"))
            login_btn.bind(on_release=lambda *_: self._start_login())
            card.add_widget(login_btn)
        else:
            perm = self._auth.permission or "?"
            row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
            row.add_widget(MDLabel(
                text=f"@{self._auth.username}",
                adaptive_height=True,
                size_hint_x=0.5,
            ))
            row.add_widget(MDLabel(
                text=f"[{perm.upper()}]",
                adaptive_height=True,
                size_hint_x=0.2,
                theme_text_color="Custom",
                text_color=(0.2, 0.8, 0.3, 1) if write_tier else (0.6, 0.6, 0.6, 1),
            ))
            logout_btn = MDButton(MDButtonText(text="Sign Out"), size_hint_x=None)
            logout_btn.bind(on_release=lambda *_: self._logout())
            row.add_widget(logout_btn)
            card.add_widget(row)

        # PR section: show when logged in
        self._pr_card.opacity  = 1 if logged_in else 0
        self._pr_card.disabled = not logged_in

        # Write-only sections
        for section in self._write_sections:
            section.opacity  = 1 if write_tier else 0
            section.disabled = not write_tier

    # -----------------------------------------------------------------------
    # Login / logout
    # -----------------------------------------------------------------------

    def _start_login(self) -> None:
        if not self._login_dialog:
            self._login_code_lbl = MDLabel(
                text="Connecting to GitHub...",
                adaptive_height=True,
                halign="center",
            )
            self._login_dialog = MDDialog(
                MDDialogHeadlineText(text="Sign In with GitHub"),
                MDDialogSupportingText(
                    text="Visit the URL below and enter the code shown.",
                    adaptive_height=True,
                ),
                self._login_code_lbl,
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(
                        MDButtonText(text="Cancel"),
                        on_release=lambda *_: self._login_dialog.dismiss(),
                    ),
                    adaptive_height=True,
                ),
            )

        self._login_dialog.open()

        def _on_code(user_code: str, verification_uri: str) -> None:
            def _update(dt):
                if self._login_code_lbl:
                    self._login_code_lbl.text = (
                        f"Code: [b]{user_code}[/b]\n{verification_uri}"
                    )
                    self._login_code_lbl.markup = True
            Clock.schedule_once(_update)

        def _on_complete(success: bool, username_or_error: str) -> None:
            def _update(dt):
                if self._login_dialog:
                    self._login_dialog.dismiss()
                if success:
                    self._host.log(f"[devtools] Signed in as @{username_or_error}")
                    self._propagate_token()
                    self._refresh()
                else:
                    self._host.log(f"[devtools] Sign-in failed: {username_or_error}")
            Clock.schedule_once(_update)

        self._auth.login_async(
            self._repo_owner, self._repo_name,
            on_code=_on_code,
            on_complete=_on_complete,
            log_fn=self._host.log,
        )

    def _logout(self) -> None:
        self._auth.logout()
        self._propagate_token_clear()
        self._refresh_auth_ui()
        self._host.log("[devtools] Signed out.")

    def _propagate_token(self) -> None:
        try:
            docs_api = self._host.get_service("docs_viewer")
            if docs_api and hasattr(docs_api, "_api") and docs_api._api:
                docs_api._api.refresh_auth()
        except Exception as exc:
            self._host.log(f"[devtools] Could not propagate token to docs_viewer: {exc}")

    def _propagate_token_clear(self) -> None:
        try:
            docs_api = self._host.get_service("docs_viewer")
            if docs_api and hasattr(docs_api, "_api") and docs_api._api:
                docs_api._api.clear_user_token()
        except Exception as exc:
            self._host.log(f"[devtools] Could not clear token from docs_viewer: {exc}")

    # -----------------------------------------------------------------------
    # Section 2 — Dev Setup
    # -----------------------------------------------------------------------

    def _open_setup_guide(self) -> None:
        setup_md = _HERE / "SETUP.md"
        if not setup_md.exists():
            self._host.log("[devtools] SETUP.md not found.")
            return
        try:
            svc = self._host.get_service("docs_viewer")
            if svc:
                svc.open(path=str(setup_md))
            else:
                self._host.log("[devtools] docs_viewer service not available.")
        except Exception as exc:
            self._host.log(f"[devtools] Could not open setup guide: {exc}")

    # -----------------------------------------------------------------------
    # Section 3 — Pull Requests
    # -----------------------------------------------------------------------

    def _on_open_pr(self) -> None:
        branch = vm.get_current_branch()
        title  = self._pr_title.text.strip() if self._pr_title else ""
        if not branch:
            self._host.log("[devtools] Cannot determine current branch for PR.")
            return
        url = (
            f"https://github.com/{self._repo_owner}/{self._repo_name}"
            f"/compare/{branch}?expand=1"
        )
        if title:
            url += f"&title={title.replace(' ', '+')}"
        try:
            webbrowser.open(url)
            self._host.log(f"[devtools] Opened PR page for branch '{branch}'.")
        except Exception as exc:
            self._host.log(
                f"[devtools] Could not open browser ({exc}). URL: {url}"
            )

    # -----------------------------------------------------------------------
    # Section 4 — Version Management
    # -----------------------------------------------------------------------

    def _refresh_versions(self) -> None:
        versions = vm.get_all_versions()
        self._local_versions = versions
        for component, ver in versions.items():
            row = self._version_rows.get(component)
            if row:
                row["local_lbl"].text = ver or "?"
                row["status_lbl"].text = ""

        token = self._auth.token
        if not token:
            return

        def _fetch():
            try:
                tags = self._ci.list_tags(token)
                remote: dict[str, Optional[str]] = {}
                for component in _COMPONENTS:
                    prefix = f"{component}/v"
                    comp_tags = sorted(t for t in tags if t.startswith(prefix))
                    remote[component] = comp_tags[-1].removeprefix(prefix) if comp_tags else None
                self._remote_versions = remote

                def _update(dt):
                    for component, rem_ver in remote.items():
                        row = self._version_rows.get(component)
                        if not row:
                            continue
                        loc_ver = self._local_versions.get(component)
                        row["remote_lbl"].text = rem_ver or "—"
                        slbl = row["status_lbl"]
                        if loc_ver and rem_ver:
                            if loc_ver == rem_ver:
                                slbl.text = "✓ Current"
                                slbl.theme_text_color = "Custom"
                                slbl.text_color = (0.2, 0.8, 0.2, 1)
                            elif loc_ver > rem_ver:
                                slbl.text = "Ahead"
                                slbl.theme_text_color = "Custom"
                                slbl.text_color = (0.3, 0.6, 1.0, 1)
                            else:
                                slbl.text = "Behind"
                                slbl.theme_text_color = "Custom"
                                slbl.text_color = (1.0, 0.6, 0.2, 1)
                        else:
                            slbl.text = "No tag" if loc_ver else "?"
                            slbl.theme_text_color = "Secondary"
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Failed to fetch remote tags: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("versions", f"Tag fetch failed: {e}", ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _open_bump_menu(self, caller, component: str) -> None:
        items = [
            {
                "text": part,
                "on_release": lambda x, c=component, p=part: self._set_bump(c, p),
            }
            for part in _BUMP_PARTS
        ]
        menu = MDDropdownMenu(caller=caller, items=items)
        self._bump_menus[component] = menu
        menu.open()

    def _set_bump(self, component: str, part: str) -> None:
        self._bump_parts[component] = part
        row = self._version_rows.get(component)
        if row:
            for child in row["bump_btn"].walk(restrict=True):
                if hasattr(child, "text") and child is not row["bump_btn"]:
                    child.text = f"{part} ▾"
                    break
        menu = self._bump_menus.get(component)
        if menu:
            menu.dismiss()

    def _on_commit_tag(self, component: str) -> None:
        current = self._local_versions.get(component)
        if not current:
            self._host.log(f"[devtools] Cannot read current {component} version.")
            self._set_status("versions", f"Cannot read {component} version.", ok=False)
            return
        part    = self._bump_parts.get(component, "patch")
        new_ver = vm.bump_version(current, part)

        if not vm.set_version(component, new_ver):
            self._host.log(f"[devtools] Failed to write {component} version to source file.")
            self._set_status("versions", f"Failed to write {component} version.", ok=False)
            return

        self._host.log(f"[devtools] {component}: {current} → {new_ver} — committing...")
        self._set_status("versions", f"Committing {component} v{new_ver}...")

        def _run():
            try:
                ok, err = vm.commit_and_tag(component, new_ver)
                def _update(dt):
                    if ok:
                        self._host.log(f"[devtools] {component} v{new_ver} committed and tagged.")
                        self._set_status("versions", f"{component} v{new_ver} tagged.", ok=True)
                        self._refresh_versions()
                        # Tag push may trigger a release workflow — refresh after a short delay
                        Clock.schedule_once(lambda dt: self._refresh_workflows(), 8)
                    else:
                        self._host.log(f"[devtools] Commit/tag failed: {err}")
                        self._set_status("versions", f"Failed: {err}", ok=False)
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Unexpected error during commit/tag: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("versions", str(e), ok=False)
                )

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # Section 5 — CI / Workflows
    # -----------------------------------------------------------------------

    def _refresh_workflows(self) -> None:
        token = self._auth.token
        if not token or not self._workflows_list:
            return
        self._host.log("[devtools] Fetching workflows...")
        self._set_status("workflows", "Loading...")

        def _fetch():
            try:
                workflows = self._ci.list_workflows(token)
                def _update(dt):
                    self._workflows_list.clear_widgets()
                    if not workflows:
                        self._workflows_list.add_widget(MDLabel(
                            text="No workflows found in .github/workflows/",
                            adaptive_height=True,
                            theme_text_color="Secondary",
                        ))
                        self._set_status("workflows", "")
                        return
                    for wf in workflows:
                        self._workflows_list.add_widget(self._make_workflow_row(wf))
                    self._set_status("workflows", f"{len(workflows)} workflow(s) loaded.", ok=True)
                    self._host.log(f"[devtools] {len(workflows)} workflow(s) loaded.")
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Failed to fetch workflows: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("workflows", str(e), ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _make_workflow_row(self, wf: dict) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal",
            adaptive_height=True,
            spacing=dp(8),
            padding=(0, dp(4), 0, dp(4)),
        )
        wf_id    = wf.get("id")
        wf_name  = wf.get("name", "Unknown")
        html_url = wf.get("html_url", "")

        name_lbl = MDLabel(text=wf_name, adaptive_height=True, size_hint_x=0.4)
        status_lbl = MDLabel(text="", adaptive_height=True, size_hint_x=0.3,
                             theme_text_color="Secondary")
        run_btn  = MDButton(MDButtonText(text="Run"), size_hint_x=None)
        view_btn = MDIconButton(icon="open-in-new", size_hint_x=None, width=dp(36))

        def _on_run(*args, _id=wf_id, _name=wf_name, _lbl=status_lbl):
            token = self._auth.token
            if not token:
                return
            branch = vm.get_current_branch() or "master"
            _lbl.text = "Dispatching..."
            self._host.log(f"[devtools] Dispatching workflow '{_name}' on {branch}...")

            def _on_status(s: str, lbl=_lbl, name=_name):
                def _upd(dt):
                    lbl.text = s
                    self._host.log(f"[devtools] Workflow '{name}': {s}")
                Clock.schedule_once(_upd)

            self._ci.dispatch_workflow(str(_id), branch, token, _on_status)

        run_btn.bind(on_release=_on_run)

        if html_url:
            view_btn.bind(on_release=lambda *_, u=html_url: self._open_url(u))
        else:
            view_btn.disabled = True

        for w in (name_lbl, run_btn, status_lbl, view_btn):
            row.add_widget(w)
        return row

    # -----------------------------------------------------------------------
    # Section 6 — Releases
    # -----------------------------------------------------------------------

    def _refresh_releases(self) -> None:
        token = self._auth.token
        if not token or not self._releases_list:
            return
        self._host.log("[devtools] Fetching releases...")
        self._set_status("releases", "Loading...")

        def _fetch():
            try:
                releases = self._ci.list_releases(token)
                def _update(dt):
                    self._releases_list.clear_widgets()
                    if not releases:
                        self._releases_list.add_widget(MDLabel(
                            text="No releases yet.",
                            adaptive_height=True,
                            theme_text_color="Secondary",
                        ))
                        self._set_status("releases", "")
                        return
                    for rel in releases[:5]:
                        row = MDBoxLayout(orientation="horizontal", adaptive_height=True,
                                          spacing=dp(8), padding=(0, dp(2), 0, dp(2)))
                        row.add_widget(MDLabel(
                            text=rel.get("tag_name", "?"), adaptive_height=True, size_hint_x=0.3
                        ))
                        row.add_widget(MDLabel(
                            text=rel.get("name", ""), adaptive_height=True, size_hint_x=0.5,
                            theme_text_color="Secondary",
                        ))
                        view_btn = MDIconButton(icon="open-in-new", size_hint_x=None, width=dp(36))
                        url = rel.get("html_url", "")
                        if url:
                            view_btn.bind(on_release=lambda *_, u=url: self._open_url(u))
                        row.add_widget(view_btn)
                        self._releases_list.add_widget(row)
                    self._set_status("releases", f"{len(releases)} release(s).", ok=True)
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Failed to fetch releases: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("releases", str(e), ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _show_create_release_dialog(self) -> None:
        token = self._auth.token
        if not token:
            return
        self._host.log("[devtools] Fetching tags for release dialog...")

        def _fetch():
            try:
                tags     = self._ci.list_tags(token)
                releases = self._ci.list_releases(token)
                released = {r["tag_name"] for r in releases}
                unreleased = [t for t in tags if t not in released]
                Clock.schedule_once(
                    lambda dt, u=unreleased: self._open_create_release_dialog(u, token)
                )
            except Exception as exc:
                self._host.log(f"[devtools] Failed to fetch tags: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("releases", str(e), ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _open_create_release_dialog(self, unreleased_tags: list, token: str) -> None:
        if not unreleased_tags:
            self._host.log("[devtools] No unreleased tags found. Push a version tag first.")
            self._set_status("releases", "No unreleased tags available.", ok=False)
            return

        tag_field   = MDTextField(hint_text="Tag name", adaptive_height=True)
        name_field  = MDTextField(hint_text="Release name (optional)", adaptive_height=True)
        notes_field = MDTextField(
            hint_text="Release notes (leave empty to auto-generate)",
            adaptive_height=True, multiline=True,
        )
        tag_field.text = unreleased_tags[0]

        dialog_ref: list = [None]

        def _publish(*_):
            tag   = tag_field.text.strip()
            name  = name_field.text.strip() or tag
            notes = notes_field.text.strip()
            if not tag:
                self._host.log("[devtools] Tag is required to create a release.")
                return
            if dialog_ref[0]:
                dialog_ref[0].dismiss()
            self._do_create_release(tag, name, notes, token)

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="Create Release"),
            MDDialogContentContainer(
                tag_field, name_field, notes_field,
                orientation="vertical", adaptive_height=True, spacing=dp(8),
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(MDButtonText(text="Publish"), style="filled",
                         on_release=_publish),
                adaptive_height=True,
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _do_create_release(self, tag: str, name: str, notes: str, token: str) -> None:
        self._host.log(f"[devtools] Creating release for tag '{tag}'...")
        self._set_status("releases", f"Creating release for {tag}...")

        def _run():
            try:
                rel = self._ci.create_release(tag, name, notes, token)
                url = rel.get("html_url", "")
                def _update(dt):
                    self._host.log(f"[devtools] Release '{tag}' created. {url}")
                    self._set_status("releases", f"Release {tag} created.", ok=True)
                    self._refresh_releases()
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Failed to create release '{tag}': {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("releases", str(e), ok=False)
                )

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # Section 7 — Branches
    # -----------------------------------------------------------------------

    def _refresh_branches(self) -> None:
        token = self._auth.token
        if not token or not self._branches_list:
            return
        self._host.log("[devtools] Fetching branches...")
        self._set_status("branches", "Loading...")

        def _fetch():
            try:
                branches = self._ci.list_branches(token)
                def _update(dt):
                    self._branches_list.clear_widgets()
                    for br in branches:
                        bname     = br.get("name", "?")
                        protected = br.get("protected", False)
                        row = MDBoxLayout(orientation="horizontal", adaptive_height=True,
                                          spacing=dp(8), padding=(0, dp(2), 0, dp(2)))
                        row.add_widget(MDLabel(
                            text=bname, adaptive_height=True, size_hint_x=0.6
                        ))
                        if protected or bname in ("master", "main"):
                            row.add_widget(MDLabel(
                                text="protected" if protected else "default",
                                adaptive_height=True, size_hint_x=0.3,
                                theme_text_color="Secondary",
                            ))
                        else:
                            del_btn = MDIconButton(
                                icon="delete-outline", size_hint_x=None, width=dp(36)
                            )
                            del_btn.bind(
                                on_release=lambda *_, n=bname: self._confirm_delete_branch(n)
                            )
                            row.add_widget(del_btn)
                        self._branches_list.add_widget(row)
                    self._set_status("branches", f"{len(branches)} branch(es).", ok=True)
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Failed to fetch branches: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("branches", str(e), ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _show_new_branch_dialog(self) -> None:
        name_field = MDTextField(hint_text="New branch name", adaptive_height=True)
        dialog_ref: list = [None]

        def _create(*_):
            name = name_field.text.strip()
            if not name:
                return
            if dialog_ref[0]:
                dialog_ref[0].dismiss()
            self._do_create_branch(name)

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="New Branch"),
            MDDialogSupportingText(text="Branch will be created from current local HEAD."),
            MDDialogContentContainer(
                name_field,
                orientation="vertical", adaptive_height=True,
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(MDButtonText(text="Create"), style="filled",
                         on_release=_create),
                adaptive_height=True,
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _do_create_branch(self, name: str) -> None:
        token = self._auth.token
        if not token:
            return
        self._host.log(f"[devtools] Creating branch '{name}' from HEAD...")
        self._set_status("branches", f"Creating branch '{name}'...")

        def _run():
            try:
                sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(vm._REPO_ROOT), text=True, stderr=subprocess.STDOUT,
                ).strip()
                ok = self._ci.create_branch(name, sha, token)
                def _update(dt):
                    if ok:
                        self._host.log(f"[devtools] Branch '{name}' created.")
                        self._set_status("branches", f"Branch '{name}' created.", ok=True)
                        self._refresh_branches()
                    else:
                        self._host.log(f"[devtools] Failed to create branch '{name}'.")
                        self._set_status("branches", f"Failed to create '{name}'.", ok=False)
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Error creating branch '{name}': {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("branches", str(e), ok=False)
                )

        threading.Thread(target=_run, daemon=True).start()

    def _confirm_delete_branch(self, name: str) -> None:
        dialog_ref: list = [None]

        def _delete(*_):
            if dialog_ref[0]:
                dialog_ref[0].dismiss()
            self._do_delete_branch(name)

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="Delete Branch"),
            MDDialogSupportingText(text=f"Delete '{name}'? This cannot be undone."),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(MDButtonText(text="Delete"), style="filled",
                         on_release=_delete),
                adaptive_height=True,
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _do_delete_branch(self, name: str) -> None:
        token = self._auth.token
        if not token:
            return
        self._host.log(f"[devtools] Deleting branch '{name}'...")
        self._set_status("branches", f"Deleting '{name}'...")

        def _run():
            try:
                ok = self._ci.delete_branch(name, token)
                def _update(dt):
                    if ok:
                        self._host.log(f"[devtools] Branch '{name}' deleted.")
                        self._set_status("branches", f"Branch '{name}' deleted.", ok=True)
                        MDSnackbar(
                            MDSnackbarText(text=f"Branch '{name}' deleted."),
                            y=dp(24), pos_hint={"center_x": 0.5},
                            size_hint_x=0.6, duration=3,
                        ).open()
                        self._refresh_branches()
                    else:
                        self._host.log(f"[devtools] Failed to delete branch '{name}'.")
                        self._set_status("branches", f"Failed to delete '{name}'.", ok=False)
                Clock.schedule_once(_update)
            except Exception as exc:
                self._host.log(f"[devtools] Error deleting branch '{name}': {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("branches", str(e), ok=False)
                )

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as exc:
            self._host.log(f"[devtools] Could not open URL ({exc}): {url}")
