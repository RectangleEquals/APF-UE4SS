"""
DevToolsPanel — comprehensive developer hub for repo contributors.

Five tabs:
  Account        — sign in/out, identity + write-tier tokens, permission level
  Dev Setup      — dev environment setup guide, repo root path
  Source Control — pull requests + branch management (write-tier)
  Versions       — version management table (write-tier)
  CI             — workflow runs + releases (write-tier)

All GitHub API calls run on background threads; UI updates are dispatched
back to the main thread via Clock.schedule_once.
All errors are logged via self.host.log("[devtools] ...") and shown in
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
from kivy.core.clipboard import Clipboard
from kivy.uix.image import Image as KivyImage
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer, MDDialogContentContainer,
)
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivymd.uix.tab import MDTabsPrimary, MDTabsItem, MDTabsItemIcon, MDTabsItemText, MDTabsCarousel
from kivymd.uix.textfield import MDTextField

from ...gui.widgets.plugin_panel import PluginPanel
from ...gui.widgets.tip_icon_button import ImageTextButton
from .github_auth import GitHubAuth
from .ci_manager import CIManager
from . import version_manager as vm

if TYPE_CHECKING:
    from ...core.config import GameProfile

_HERE = Path(__file__).parent
_DISCORD_ICON = _HERE.parent.parent / "data" / "Discord_Symbol_White.png"
_DEVTOOLS_CONFIG = Path.home() / ".apf_manager" / "devtools.json"

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


def _load_devtools_config() -> dict:
    try:
        return json.loads(_DEVTOOLS_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_devtools_config(data: dict) -> None:
    try:
        _DEVTOOLS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        _DEVTOOLS_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


class DevToolsPanel(PluginPanel):

    def __init__(self, host, **kwargs):
        super().__init__(host=host, **kwargs)
        meta = _load_meta()
        self._repo_owner: str = meta.get("repo_owner", "")
        self._repo_name:  str = meta.get("repo_name", "")

        self._auth = GitHubAuth()
        self._ci   = CIManager(self._repo_owner, self._repo_name)

        # Load persisted repo root (set before _build_ui so the slide initialises correctly)
        saved_root = _load_devtools_config().get("repo_root", "")
        if saved_root:
            candidate = Path(saved_root)
            if (candidate / ".git").is_dir():
                vm.set_repo_root(candidate)

        # Per-component version state
        self._local_versions:  dict[str, Optional[str]] = {}
        self._remote_versions: dict[str, Optional[str]] = {}
        self._bump_parts:      dict[str, str]            = {c: "patch" for c in _COMPONENTS}

        # Slide content box refs (populated in _build_ui; cleared/rebuilt in _refresh_auth_ui)
        self._box_account:        Optional[MDBoxLayout] = None
        self._box_source_control: Optional[MDBoxLayout] = None
        self._box_versions:       Optional[MDBoxLayout] = None
        self._box_ci:             Optional[MDBoxLayout] = None

        # Widget refs populated when content is built
        self._repo_state_icon: Optional[MDIconButton] = None
        self._repo_root_lbl:   Optional[MDLabel]      = None
        self._pr_branch_lbl:   Optional[MDLabel]      = None
        self._pr_title:       Optional[MDTextField] = None
        self._pr_body:        Optional[MDTextField] = None

        self._version_rows:   dict[str, dict] = {}
        self._workflows_list: Optional[MDBoxLayout] = None
        self._releases_list:  Optional[MDBoxLayout] = None
        self._branches_list:  Optional[MDBoxLayout] = None

        self._status_labels:  dict[str, MDLabel]        = {}
        self._bump_menus:     dict[str, MDDropdownMenu] = {}

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
        # Tab bar — MDTabsPrimary naturally collapses to its tab-bar height (kv:
        # size_hint_y=None, height=minimum_height). That is correct here because
        # we add MDTabsCarousel as a SIBLING in PluginPanel, not a child of tabs.
        tabs = MDTabsPrimary()

        for label, icon in [
            ("Account",        "account"),
            ("Dev Setup",      "book-open-variant"),
            ("Source Control", "source-branch"),
            ("Versions",       "tag-multiple"),
            ("CI",             "cog-play"),
        ]:
            tabs.add_widget(MDTabsItem(
                MDTabsItemIcon(icon=icon),
                MDTabsItemText(text=label),
            ))

        # Content carousel — sibling to tabs in PluginPanel so it gets full
        # remaining height via size_hint=(1, 1) in the parent BoxLayout.
        carousel = MDTabsCarousel(size_hint=(1, 1))

        # Wire carousel ↔ tabs manually (mirrors what MDTabsPrimary.add_widget
        # does internally when a MDTabsCarousel is passed to it, minus the
        # super().add_widget() that would place it inside MDTabsPrimary).
        tabs._tabs_carousel = carousel
        carousel._tabs = tabs
        carousel.bind(_offset=tabs.android_animation, index=tabs.on_carousel_index)

        # Tab 0: Account — dynamic, rebuilt each _refresh_auth_ui
        self._box_account = MDBoxLayout(
            orientation="vertical", adaptive_height=True,
            padding=dp(16), spacing=dp(8),
        )
        sv0 = ScrollView(size_hint=(1, 1))
        sv0.add_widget(self._box_account)
        carousel.add_widget(sv0)

        # Tab 1: Dev Setup — static
        carousel.add_widget(self._build_devsetup_slide())

        # Tab 2: Source Control — dynamic
        self._box_source_control = MDBoxLayout(
            orientation="vertical", adaptive_height=True,
            padding=dp(16), spacing=dp(8),
        )
        sv2 = ScrollView(size_hint=(1, 1))
        sv2.add_widget(self._box_source_control)
        carousel.add_widget(sv2)

        # Tab 3: Versions — dynamic
        self._box_versions = MDBoxLayout(
            orientation="vertical", adaptive_height=True,
            padding=dp(16), spacing=dp(8),
        )
        sv3 = ScrollView(size_hint=(1, 1))
        sv3.add_widget(self._box_versions)
        carousel.add_widget(sv3)

        # Tab 4: CI — dynamic
        self._box_ci = MDBoxLayout(
            orientation="vertical", adaptive_height=True,
            padding=dp(16), spacing=dp(8),
        )
        sv4 = ScrollView(size_hint=(1, 1))
        sv4.add_widget(self._box_ci)
        carousel.add_widget(sv4)

        # Add as siblings: tab bar (natural height) → divider → carousel (fills rest)
        self.add_widget(tabs)
        self.add_widget(MDDivider())
        self.add_widget(carousel)

        self._refresh_auth_ui()

    def _build_devsetup_slide(self) -> ScrollView:
        box = MDBoxLayout(
            orientation="vertical", adaptive_height=True,
            size_hint_x=1, padding=dp(16), spacing=dp(8),
        )

        # Repo root row: [state icon] [label — fills remaining width] [browse button]
        # Using concrete size=(dp(40), dp(40)) on both buttons so the horizontal
        # BoxLayout gets explicit widths for everything except the label.
        root_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=1, size_hint_y=None, height=dp(48),
            spacing=dp(4),
        )
        self._repo_state_icon = MDIconButton(
            icon="alert-circle-outline",
            theme_icon_color="Custom",
            icon_color=(1, 0.8, 0, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            # Non-interactive — decorative state indicator only, no on_release bound
        )
        root_row.add_widget(self._repo_state_icon)
        self._repo_root_lbl = MDLabel(
            text="Repo source folder not set — please choose a folder",
            theme_text_color="Custom",
            text_color=(1, 0.8, 0, 1),
            adaptive_height=True,
            adaptive_width=True,
            size_hint_x=None,
            shorten=True,
            shorten_from="left",
        )
        root_row.add_widget(self._repo_root_lbl)
        browse_btn = MDIconButton(
            icon="folder-open-outline",
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        browse_btn.bind(on_release=lambda *_: self._pick_repo_root())
        root_row.add_widget(browse_btn)
        box.add_widget(root_row)

        clone_btn = MDButton(
            MDButtonIcon(icon="source-repository"),
            MDButtonText(text="Clone Repo"),
        )
        clone_btn.bind(on_release=lambda *_: self._show_clone_dialog())
        box.add_widget(clone_btn)

        setup_btn = MDButton(
            MDButtonIcon(icon="book-open-variant"),
            MDButtonText(text="View Dev Environment Setup"),
        )
        setup_btn.bind(on_release=lambda *_: self._open_setup_guide())
        box.add_widget(setup_btn)

        sv = ScrollView(size_hint=(1, 1))
        sv.add_widget(box)
        self._update_repo_root_display()
        return sv

    def _update_repo_root_display(self) -> None:
        """Update the state icon and label in the Dev Setup slide to reflect current repo validity."""
        if self._repo_state_icon is None or self._repo_root_lbl is None:
            return
        if vm.is_repo_valid():
            self._repo_state_icon.icon = "source-repository"
            self._repo_state_icon.theme_icon_color = "Secondary"
            self._repo_root_lbl.text = str(vm._REPO_ROOT)
            self._repo_root_lbl.theme_text_color = "Secondary"
        else:
            self._repo_state_icon.icon = "alert-circle-outline"
            self._repo_state_icon.theme_icon_color = "Custom"
            self._repo_state_icon.icon_color = (1, 0.8, 0, 1)
            self._repo_root_lbl.text = "Repo source folder not set — please choose a folder"
            self._repo_root_lbl.theme_text_color = "Custom"
            self._repo_root_lbl.text_color = (1, 0.8, 0, 1)

    def _pick_repo_root(self) -> None:
        """Open a native folder picker. Validates that the chosen folder is a git repo."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            tk_root = tk.Tk()
            tk_root.withdraw()
            path = filedialog.askdirectory(title="Select Repository Root")
            tk_root.destroy()
        except Exception as exc:
            self.host.log(f"[devtools] Folder picker failed: {exc}")
            return
        if not path:
            return
        candidate = Path(path)
        if not (candidate / ".git").is_dir():
            self.host.log(f"[devtools] Selected folder is not a git repository: {candidate}")
            return
        vm.set_repo_root(candidate)
        cfg = _load_devtools_config()
        cfg["repo_root"] = str(candidate)
        _save_devtools_config(cfg)
        self._update_repo_root_display()
        self._refresh_auth_ui()

    def _show_clone_dialog(self) -> None:
        """Dialog to clone the repo to a local directory, streaming output to the log."""
        dialog_ref: list = [None]

        def _dismiss(*_):
            if dialog_ref[0] is not None:
                d = dialog_ref[0]
                dialog_ref[0] = None
                d.dismiss()

        url_field = MDTextField(
            hint_text="Repository URL",
            text="https://github.com/RectangleEquals/APF-UE4SS.git",
        )
        dir_field = MDTextField(hint_text="Target directory (will be created)")

        def _run_clone(*_):
            url = url_field.text.strip()
            target = dir_field.text.strip()
            if not url or not target:
                return
            _dismiss()
            self.host.log(f"[devtools] Cloning {url} into {target} ...")

            def _clone():
                try:
                    proc = subprocess.Popen(
                        ["git", "clone", url, target],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    )
                    for line in proc.stdout:
                        Clock.schedule_once(
                            lambda dt, l=line.rstrip(): self.host.log(f"[git] {l}")
                        )
                    proc.wait()
                    if proc.returncode == 0:
                        new_root = Path(target)
                        vm.set_repo_root(new_root)
                        cfg = _load_devtools_config()
                        cfg["repo_root"] = str(new_root)
                        _save_devtools_config(cfg)
                        Clock.schedule_once(lambda dt: (
                            self.host.log(f"[devtools] Clone complete. Repo: {new_root}"),
                            self._update_repo_root_display(),
                            self._refresh_auth_ui(),
                        ))
                    else:
                        Clock.schedule_once(lambda dt: self.host.log(
                            f"[devtools] git clone exited with code {proc.returncode}"
                        ))
                except Exception as exc:
                    Clock.schedule_once(lambda dt, e=exc: self.host.log(
                        f"[devtools] Clone failed: {e}"
                    ))

            threading.Thread(target=_clone, daemon=True).start()

        clone_btn = MDButton(
            MDButtonIcon(icon="source-repository"),
            MDButtonText(text="Clone"),
        )
        clone_btn.bind(on_release=_run_clone)

        dialog = MDDialog(
            MDDialogHeadlineText(text="Clone Repository"),
            MDDialogContentContainer(
                url_field,
                dir_field,
            ),
            MDDialogButtonContainer(
                Widget(),
                clone_btn,
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_dismiss),
            ),
        )
        dialog_ref[0] = dialog
        dialog.open()

    # -----------------------------------------------------------------------
    # Write-tier placeholder
    # -----------------------------------------------------------------------

    def _write_tier_placeholder(self) -> MDBoxLayout:
        """Centered message shown in write-tier tabs when not authenticated."""
        outer = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(16))
        outer.add_widget(Widget(size_hint_y=None, height=dp(60)))
        outer.add_widget(MDLabel(
            text="Sign in with write access to use this section.",
            adaptive_height=True,
            halign="center",
            theme_text_color="Secondary",
        ))
        return outer

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def _refresh(self) -> None:
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
        if ok and self._auth.is_logged_in:
            self._refresh_pr_branch()
        if ok and self._auth.is_write_tier:
            self._refresh_versions()
            self._refresh_workflows()
            self._refresh_releases()
            self._refresh_branches()

    def _refresh_pr_branch(self) -> None:
        branch = vm.get_current_branch()
        if branch and self._pr_branch_lbl:
            self._pr_branch_lbl.text = f"Branch: {branch} -> master"

    def _refresh_auth_ui(self) -> None:
        logged_in  = self._auth.is_logged_in
        write_tier = self._auth.is_write_tier

        # --- Tab 0: Account ---
        box = self._box_account
        box.clear_widgets()

        if not logged_in:
            box.add_widget(MDLabel(
                text="Sign in to GitHub to enable contribution tools and developer features.",
                adaptive_height=True,
                theme_text_color="Secondary",
            ))
            login_btn = MDButton(
                MDButtonIcon(icon="github"),
                MDButtonText(text="Sign In with GitHub"),
            )
            login_btn.bind(on_release=lambda *_: self._start_login())
            box.add_widget(login_btn)
        else:
            perm = self._auth.permission           # "admin" | "write" | "read" | "none" | None
            perm_display = (perm or "?").upper()
            row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
            row.add_widget(MDLabel(
                text=f"@{self._auth.username}",
                adaptive_height=True,
                size_hint_x=0.5,
            ))
            row.add_widget(MDLabel(
                text=f"[{perm_display}]",
                adaptive_height=True,
                size_hint_x=0.2,
                theme_text_color="Custom",
                text_color=(0.2, 0.8, 0.3, 1) if write_tier else (0.6, 0.6, 0.6, 1),
            ))
            logout_btn = MDButton(
                MDButtonIcon(icon="logout"),
                MDButtonText(text="Sign Out"),
                size_hint_x=None,
            )
            logout_btn.bind(on_release=lambda *_: self._logout())
            row.add_widget(logout_btn)
            box.add_widget(row)

            box.add_widget(MDDivider())
            if not write_tier:
                box.add_widget(MDLabel(
                    text="Write access lets you create PRs, manage branches, trigger CI, and push version tags.",
                    adaptive_height=True,
                    theme_text_color="Secondary",
                    font_style="Body",
                ))
                req_btn = MDButton(
                    MDButtonIcon(icon="account-plus"),
                    MDButtonText(text="Request Write Access"),
                )
                req_btn.bind(on_release=lambda *_: self._show_request_write_dialog())
                box.add_widget(req_btn)

            # --- GitHub API Rate Limit ---
            box.add_widget(MDDivider())
            box.add_widget(MDLabel(
                text="GitHub API",
                font_style="Label",
                role="medium",
                adaptive_height=True,
                theme_text_color="Secondary",
            ))
            self._build_rate_limit_section(box)


        # --- Tab 2: Source Control ---
        sc = self._box_source_control
        sc.clear_widgets()
        if logged_in:
            # PR form visible to all logged-in users; branches section gated to write-tier
            self._build_source_control_content(sc, write_tier=write_tier)
        else:
            sc.add_widget(self._write_tier_placeholder())

        # --- Tab 3: Versions ---
        ver = self._box_versions
        ver.clear_widgets()
        self._version_rows.clear()
        self._status_labels.pop("versions", None)
        if write_tier:
            self._build_versions_content(ver)
        else:
            ver.add_widget(self._write_tier_placeholder())

        # --- Tab 4: CI ---
        ci = self._box_ci
        ci.clear_widgets()
        self._status_labels.pop("workflows", None)
        self._status_labels.pop("releases", None)
        self._workflows_list = None
        self._releases_list  = None
        if write_tier:
            self._build_ci_content(ci)
        else:
            ci.add_widget(self._write_tier_placeholder())

        # Branches list ref cleared when not shown
        if not write_tier:
            self._branches_list = None
            self._status_labels.pop("branches", None)

    # -----------------------------------------------------------------------
    # Rate limit helpers
    # -----------------------------------------------------------------------

    def _build_rate_limit_section(self, box: MDBoxLayout) -> None:
        from ...core.remote.github_api import (
            GitHubAPI, _format_reset_time,
        )

        def _rl_row(label: str, info) -> MDBoxLayout:
            row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
            if info:
                remaining, limit, reset_ts = info
                color = (0.9, 0.3, 0.3, 1) if remaining < 10 else (0.3, 0.8, 0.4, 1)
                row.add_widget(MDLabel(
                    text=f"{label}: {remaining} / {limit}",
                    adaptive_height=True,
                    size_hint_x=0.6,
                    theme_text_color="Custom",
                    text_color=color,
                ))
                reset_text = f"Resets at: {_format_reset_time(reset_ts)}" if reset_ts else ""
                row.add_widget(MDLabel(
                    text=reset_text,
                    adaptive_height=True,
                    size_hint_x=0.4,
                    theme_text_color="Secondary",
                ))
            else:
                row.add_widget(MDLabel(
                    text=f"{label}: unknown",
                    adaptive_height=True,
                    theme_text_color="Secondary",
                ))
            return row

        rest_info   = GitHubAPI.get_global_rate_limit_info()
        search_info = GitHubAPI.get_global_search_rate_limit_info()

        if not rest_info and not search_info:
            box.add_widget(MDLabel(
                text="Rate limit: unknown (no API calls made yet)",
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            ))
            return

        box.add_widget(_rl_row("REST (5000/hr)",  rest_info))
        box.add_widget(_rl_row("Search (30/min)", search_info))

    # -----------------------------------------------------------------------
    # Tab content builders
    # -----------------------------------------------------------------------

    def _build_source_control_content(self, box: MDBoxLayout, write_tier: bool = True) -> None:
        # --- Pull Requests (visible to all logged-in users) ---
        box.add_widget(MDLabel(text="Pull Requests", font_style="Title", adaptive_height=True))

        self._pr_branch_lbl = MDLabel(
            text="Branch: — -> master",
            adaptive_height=True,
            theme_text_color="Secondary",
        )
        box.add_widget(self._pr_branch_lbl)
        self._refresh_pr_branch()

        if not write_tier:
            box.add_widget(MDLabel(
                text="Fill in the title and description, then click the button to open your PR on GitHub.",
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            ))

        pr_title_label = MDLabel(
            text="PR Title",
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
        )
        self._pr_title = MDTextField(hint_text="PR title")
        pr_body_label = MDLabel(
            text="PR Description (optional)",
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
        )
        self._pr_body = MDTextField(
            hint_text="PR description (optional)",
            multiline=True,
            size_hint_y=None,
            height=dp(120),
        )
        pr_btn = MDButton(
            MDButtonIcon(icon="source-pull"),
            MDButtonText(text="Open PR on GitHub"),
        )
        pr_btn.bind(on_release=lambda *_: self._on_open_pr())

        for w in (pr_title_label, self._pr_title, pr_body_label, self._pr_body, pr_btn):
            box.add_widget(w)

        box.add_widget(MDDivider())

        # --- Branches (write-tier only) ---
        if write_tier:
            br_hdr = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
            br_hdr.add_widget(MDLabel(
                text="Branches", font_style="Title", adaptive_height=True, size_hint_x=1,
            ))
            refresh_br = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
            refresh_br.bind(on_release=lambda *_: self._refresh_branches())
            br_hdr.add_widget(refresh_br)
            new_br_btn = MDButton(
                MDButtonIcon(icon="source-branch-plus"),
                MDButtonText(text="New Branch"),
                size_hint_x=None,
            )
            new_br_btn.bind(on_release=lambda *_: self._show_new_branch_dialog())
            br_hdr.add_widget(new_br_btn)
            box.add_widget(br_hdr)

            box.add_widget(MDLabel(
                text="Manages remote branches on GitHub. Deletions cannot be undone.",
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            ))

            self._branches_list = MDBoxLayout(
                orientation="vertical", adaptive_height=True, spacing=dp(4)
            )
            box.add_widget(self._branches_list)
            self._status_labels["branches"] = self._make_status_lbl()
            box.add_widget(self._status_labels["branches"])
        else:
            box.add_widget(MDLabel(
                text="Branches",
                font_style="Title",
                adaptive_height=True,
            ))
            box.add_widget(MDLabel(
                text="Branch management requires collaborator access.",
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            ))

    def _build_versions_content(self, box: MDBoxLayout) -> None:
        box.add_widget(MDLabel(text="Version Management", font_style="Title", adaptive_height=True))

        if not vm.is_repo_valid():
            box.add_widget(MDLabel(
                text="Repo source folder not configured — see Dev Setup tab.",
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(1, 0.8, 0, 1),
            ))
            return

        box.add_widget(MDLabel(
            text=(
                "Shows local vs. remote version for each component. "
                "Use Bump to increment the version, then Commit & Tag to push a git tag."
            ),
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
        ))
        box.add_widget(MDDivider())

        # Column headers — sizes must match _make_version_row column sizes
        hdr_row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        for txt, sx in [("Component", 0.15), ("Local", 0.18), ("Remote", 0.18),
                        ("Status", 0.15), ("Bump", 0.18), ("Action", 0.16)]:
            hdr_row.add_widget(MDLabel(
                text=txt, size_hint_x=sx, adaptive_height=True,
                theme_text_color="Secondary", font_style="Body",
            ))
        box.add_widget(hdr_row)

        for component in _COMPONENTS:
            box.add_widget(self._make_version_row(component))

        self._status_labels["versions"] = self._make_status_lbl()
        box.add_widget(self._status_labels["versions"])

    def _build_ci_content(self, box: MDBoxLayout) -> None:
        # --- CI / Workflows ---
        wf_hdr = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        wf_hdr.add_widget(MDLabel(
            text="CI / Workflows", font_style="Title", adaptive_height=True, size_hint_x=1,
        ))
        refresh_wf = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_wf.bind(on_release=lambda *_: self._refresh_workflows())
        wf_hdr.add_widget(refresh_wf)
        box.add_widget(wf_hdr)

        self._workflows_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(4)
        )
        box.add_widget(self._workflows_list)
        self._status_labels["workflows"] = self._make_status_lbl()
        box.add_widget(self._status_labels["workflows"])

        box.add_widget(MDDivider())

        # --- Releases ---
        rel_hdr = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        rel_hdr.add_widget(MDLabel(
            text="Releases", font_style="Title", adaptive_height=True, size_hint_x=1,
        ))
        refresh_rel = MDIconButton(icon="refresh", size_hint_x=None, width=dp(36))
        refresh_rel.bind(on_release=lambda *_: self._refresh_releases())
        rel_hdr.add_widget(refresh_rel)
        create_rel = MDButton(
            MDButtonIcon(icon="tag-plus"),
            MDButtonText(text="Create Release"),
            size_hint_x=None,
        )
        create_rel.bind(on_release=lambda *_: self._show_create_release_dialog())
        rel_hdr.add_widget(create_rel)
        box.add_widget(rel_hdr)

        self._releases_list = MDBoxLayout(
            orientation="vertical", adaptive_height=True, spacing=dp(4)
        )
        box.add_widget(self._releases_list)
        self._status_labels["releases"] = self._make_status_lbl()
        box.add_widget(self._status_labels["releases"])

    # -----------------------------------------------------------------------
    # Widget factories
    # -----------------------------------------------------------------------

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
        bump_btn   = MDButton(
            MDButtonIcon(icon="chevron-up"),
            MDButtonText(text="patch"),
            size_hint_x=0.18,
        )
        bump_btn.bind(on_release=lambda btn, c=component: self._open_bump_menu(btn, c))
        commit_btn = MDButton(
            MDButtonIcon(icon="tag-check"),
            MDButtonText(text="Commit & Tag"),
            size_hint_x=0.16,
        )
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
    # Login / logout
    # -----------------------------------------------------------------------

    def _start_login(self) -> None:
        code_lbl = MDLabel(text="", adaptive_height=True)
        url_lbl  = MDLabel(text="Connecting to GitHub...", adaptive_height=True, font_style="Body")
        dialog_ref: list = [None]

        def _copy_code(*_):
            text = getattr(code_lbl, "_raw_code", "")
            if text:
                Clipboard.copy(text)

        def _copy_url(*_):
            text = getattr(url_lbl, "_raw_url", "")
            if text:
                Clipboard.copy(text)

        code_row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(4))
        code_row.add_widget(MDLabel(
            text="Device Code:", adaptive_height=True, size_hint_x=None,
            width=dp(120), theme_text_color="Secondary",
        ))
        code_row.add_widget(code_lbl)
        copy_code_btn = MDIconButton(icon="content-copy", size_hint_x=None, width=dp(36))
        copy_code_btn.bind(on_release=_copy_code)
        code_row.add_widget(copy_code_btn)

        url_row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(4))
        url_row.add_widget(MDLabel(
            text="Verification URL:", adaptive_height=True, size_hint_x=None,
            width=dp(120), theme_text_color="Secondary",
        ))
        url_row.add_widget(url_lbl)
        copy_url_btn = MDIconButton(icon="content-copy", size_hint_x=None, width=dp(36))
        copy_url_btn.bind(on_release=_copy_url)
        url_row.add_widget(copy_url_btn)

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="Sign In with GitHub"),
            MDDialogSupportingText(
                text=(
                    f"Verifies your identity and access level for "
                    f"{self._repo_owner}/{self._repo_name}. "
                    "No access to any of your personal repositories is requested."
                ),
            ),
            MDDialogContentContainer(
                code_row, url_row,
                orientation="vertical", spacing=dp(8),
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss(),
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

        def _on_code(user_code: str, verification_uri: str) -> None:
            def _update(dt):
                code_lbl._raw_code = user_code
                url_lbl._raw_url   = verification_uri
                code_lbl.text = f"[b]{user_code}[/b]"
                code_lbl.markup = True
                url_lbl.text  = verification_uri
            Clock.schedule_once(_update)

        def _on_complete(success: bool, username_or_error: str) -> None:
            def _update(dt):
                if dialog_ref[0]:
                    dialog_ref[0].dismiss()
                self._refresh_auth_ui()   # Always — reflects current permission state
                if success:
                    perm = self._auth.permission or "?"
                    self.host.log(
                        f"[devtools] Signed in as @{username_or_error} [{perm.upper()}]"
                    )
                    self._propagate_token()
                    if self._auth.is_write_tier:
                        self._refresh_versions()
                        self._refresh_workflows()
                        self._refresh_releases()
                        self._refresh_branches()
                else:
                    self.host.log(f"[devtools] Sign-in failed: {username_or_error}")
            Clock.schedule_once(_update)

        self._auth.login_async(
            self._repo_owner, self._repo_name,
            on_code=_on_code,
            on_complete=_on_complete,
            log_fn=self.host.log,
        )

    # -----------------------------------------------------------------------
    # Logout
    # -----------------------------------------------------------------------

    def _logout(self) -> None:
        self._auth.logout()
        self._propagate_token_clear()
        self._refresh_auth_ui()
        self.host.log("[devtools] Signed out.")

    def _show_request_write_dialog(self) -> None:
        """Show collaborator requirements + Discord link for non-collaborators."""
        discord_url = "https://discord.gg/xhcVRhnjK"
        dialog_ref: list = [None]

        def _dismiss(*_):
            if dialog_ref[0] is not None:
                d = dialog_ref[0]
                dialog_ref[0] = None
                d.dismiss()

        discord_btn = ImageTextButton(
            source=str(_DISCORD_ICON) if _DISCORD_ICON.exists() else "",
            text="Join Discord",
        )
        discord_btn.bind(on_release=lambda *_: (_dismiss(), webbrowser.open(discord_url)))

        dialog = MDDialog(
            MDDialogHeadlineText(text="Request Write Access"),
            MDDialogSupportingText(
                text=(
                    "To become a collaborator you must:\n"
                    "\u2022 Have contributed to the project (merged PR or existing collaborator status)\n"
                    "\u2022 Contact the team via Discord\n\n"
                    "Join the Discord server to get in touch."
                ),
            ),
            MDDialogButtonContainer(
                Widget(),
                discord_btn,
                MDButton(
                    MDButtonText(text="Close"),
                    style="text",
                    on_release=_dismiss,
                ),
            ),
        )
        dialog_ref[0] = dialog
        dialog.open()

    def _propagate_token(self) -> None:
        try:
            docs_api = self.host.get_service("docs_viewer")
            if docs_api and hasattr(docs_api, "_api") and docs_api._api:
                docs_api._api.refresh_auth()
        except Exception as exc:
            self.host.log(f"[devtools] Could not propagate token to docs_viewer: {exc}")

    def _propagate_token_clear(self) -> None:
        try:
            docs_api = self.host.get_service("docs_viewer")
            if docs_api and hasattr(docs_api, "_api") and docs_api._api:
                docs_api._api.clear_user_token()
        except Exception as exc:
            self.host.log(f"[devtools] Could not clear token from docs_viewer: {exc}")

    # -----------------------------------------------------------------------
    # Dev Setup tab
    # -----------------------------------------------------------------------

    def _open_setup_guide(self) -> None:
        # Use the docs_viewer service — it already has repo_owner/repo_name from its own plugin.json.
        # Passing a repo-relative path opens the remote file without any local file dependency.
        if not self.host:
            return
        try:
            svc = self.host.get_service("docs_viewer")
            if svc is None:
                self.host.log("[devtools] docs_viewer service not available.")
                return
            svc.open(
                initial_path="docs/public/dev/dev_setup.md",
                force_dev_docs=True,
                sidebar_mode="tree",
                show_mode_toggle=False,
            )
        except Exception as exc:
            self.host.log(f"[devtools] Could not open setup guide: {exc}")

    # -----------------------------------------------------------------------
    # Source Control — Pull Requests
    # -----------------------------------------------------------------------

    def _on_open_pr(self) -> None:
        branch = vm.get_current_branch()
        title  = self._pr_title.text.strip() if self._pr_title else ""
        if not branch:
            self.host.log("[devtools] Cannot determine current branch for PR.")
            return
        url = (
            f"https://github.com/{self._repo_owner}/{self._repo_name}"
            f"/compare/{branch}?expand=1"
        )
        if title:
            url += f"&title={title.replace(' ', '+')}"
        try:
            webbrowser.open(url)
            self.host.log(f"[devtools] Opened PR page for branch '{branch}'.")
        except Exception as exc:
            self.host.log(f"[devtools] Could not open browser ({exc}). URL: {url}")

    # -----------------------------------------------------------------------
    # Versions tab
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
                self.host.log(f"[devtools] Failed to fetch remote tags: {exc}")
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
                if isinstance(child, MDButtonText):
                    child.text = part
                    break
        menu = self._bump_menus.get(component)
        if menu:
            menu.dismiss()

    def _on_commit_tag(self, component: str) -> None:
        current = self._local_versions.get(component)
        if not current:
            self.host.log(f"[devtools] Cannot read current {component} version.")
            self._set_status("versions", f"Cannot read {component} version.", ok=False)
            return
        part    = self._bump_parts.get(component, "patch")
        new_ver = vm.bump_version(current, part)

        if not vm.set_version(component, new_ver):
            self.host.log(f"[devtools] Failed to write {component} version to source file.")
            self._set_status("versions", f"Failed to write {component} version.", ok=False)
            return

        self.host.log(f"[devtools] {component}: {current} → {new_ver} — committing...")
        self._set_status("versions", f"Committing {component} v{new_ver}...")

        def _run():
            try:
                ok, err = vm.commit_and_tag(component, new_ver)
                def _update(dt):
                    if ok:
                        self.host.log(f"[devtools] {component} v{new_ver} committed and tagged.")
                        self._set_status("versions", f"{component} v{new_ver} tagged.", ok=True)
                        self._refresh_versions()
                        Clock.schedule_once(lambda dt: self._refresh_workflows(), 8)
                    else:
                        self.host.log(f"[devtools] Commit/tag failed: {err}")
                        self._set_status("versions", f"Failed: {err}", ok=False)
                Clock.schedule_once(_update)
            except Exception as exc:
                self.host.log(f"[devtools] Unexpected error during commit/tag: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("versions", str(e), ok=False)
                )

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # CI tab — Workflows
    # -----------------------------------------------------------------------

    def _refresh_workflows(self) -> None:
        token = self._auth.token
        if not token or not self._workflows_list:
            return
        self.host.log("[devtools] Fetching workflows...")
        self._set_status("workflows", "Loading...")

        def _fetch():
            try:
                workflows = self._ci.list_workflows(token)
                self.host.log(f"[devtools] list_workflows returned {len(workflows)} item(s).")

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
                Clock.schedule_once(_update)
            except Exception as exc:
                self.host.log(f"[devtools] Failed to fetch workflows: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("workflows", f"Error: {e}", ok=False)
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

        name_lbl   = MDLabel(text=wf_name, adaptive_height=True, size_hint_x=0.4)
        status_lbl = MDLabel(text="", adaptive_height=True, size_hint_x=0.3,
                             theme_text_color="Secondary")
        run_btn  = MDButton(
            MDButtonIcon(icon="play"),
            MDButtonText(text="Run"),
            size_hint_x=None,
        )
        view_btn = MDIconButton(icon="open-in-new", size_hint_x=None, width=dp(36))

        def _on_run(*args, _id=wf_id, _name=wf_name, _lbl=status_lbl):
            token = self._auth.token
            if not token:
                return
            branch = vm.get_current_branch() or "master"
            _lbl.text = "Dispatching..."
            self.host.log(f"[devtools] Dispatching workflow '{_name}' on {branch}...")

            def _on_status(s: str, lbl=_lbl, name=_name):
                def _upd(dt):
                    lbl.text = s
                    self.host.log(f"[devtools] Workflow '{name}': {s}")
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
    # CI tab — Releases
    # -----------------------------------------------------------------------

    def _refresh_releases(self) -> None:
        token = self._auth.token
        if not token or not self._releases_list:
            return
        self.host.log("[devtools] Fetching releases...")
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
                self.host.log(f"[devtools] Failed to fetch releases: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("releases", str(e), ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _show_create_release_dialog(self) -> None:
        token = self._auth.token
        if not token:
            return
        self.host.log("[devtools] Fetching tags for release dialog...")

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
                self.host.log(f"[devtools] Failed to fetch tags: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("releases", str(e), ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _open_create_release_dialog(self, unreleased_tags: list, token: str) -> None:
        if not unreleased_tags:
            self.host.log("[devtools] No unreleased tags found. Push a version tag first.")
            self._set_status("releases", "No unreleased tags available.", ok=False)
            return

        tag_field   = MDTextField(hint_text="Tag name")
        name_field  = MDTextField(hint_text="Release name (optional)")
        notes_field = MDTextField(
            hint_text="Release notes (leave empty to auto-generate)",
            multiline=True,
            size_hint_y=None,
            height=dp(120),
        )
        tag_field.text = unreleased_tags[0]
        dialog_ref: list = [None]

        def _publish(*_):
            tag   = tag_field.text.strip()
            name  = name_field.text.strip() or tag
            notes = notes_field.text.strip()
            if not tag:
                self.host.log("[devtools] Tag is required to create a release.")
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
                orientation="vertical", spacing=dp(8),
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(
                    MDButtonIcon(icon="publish"),
                    MDButtonText(text="Publish"),
                    style="filled",
                    on_release=_publish,
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _do_create_release(self, tag: str, name: str, notes: str, token: str) -> None:
        self.host.log(f"[devtools] Creating release for tag '{tag}'...")
        self._set_status("releases", f"Creating release for {tag}...")

        def _run():
            try:
                rel = self._ci.create_release(tag, name, notes, token)
                url = rel.get("html_url", "")
                def _update(dt):
                    self.host.log(f"[devtools] Release '{tag}' created. {url}")
                    self._set_status("releases", f"Release {tag} created.", ok=True)
                    self._refresh_releases()
                Clock.schedule_once(_update)
            except Exception as exc:
                self.host.log(f"[devtools] Failed to create release '{tag}': {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("releases", str(e), ok=False)
                )

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # Source Control — Branches
    # -----------------------------------------------------------------------

    def _refresh_branches(self) -> None:
        token = self._auth.token
        if not token or not self._branches_list:
            return
        self.host.log("[devtools] Fetching branches...")
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
                            del_btn = MDButton(
                                MDButtonIcon(icon="delete-outline"),
                                MDButtonText(text="Delete"),
                                style="text",
                                size_hint_x=None,
                            )
                            del_btn.bind(
                                on_release=lambda *_, n=bname: self._confirm_delete_branch(n)
                            )
                            row.add_widget(del_btn)
                        self._branches_list.add_widget(row)
                    self._set_status("branches", f"{len(branches)} branch(es).", ok=True)
                Clock.schedule_once(_update)
            except Exception as exc:
                self.host.log(f"[devtools] Failed to fetch branches: {exc}")
                Clock.schedule_once(
                    lambda dt, e=exc: self._set_status("branches", str(e), ok=False)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _show_new_branch_dialog(self) -> None:
        name_field = MDTextField(hint_text="New branch name")
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
                orientation="vertical",
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text",
                         on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss()),
                MDButton(
                    MDButtonIcon(icon="plus"),
                    MDButtonText(text="Create"),
                    style="filled",
                    on_release=_create,
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _do_create_branch(self, name: str) -> None:
        token = self._auth.token
        if not token:
            return
        self.host.log(f"[devtools] Creating branch '{name}' from HEAD...")
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
                        self.host.log(f"[devtools] Branch '{name}' created.")
                        self._set_status("branches", f"Branch '{name}' created.", ok=True)
                        self._refresh_branches()
                    else:
                        self.host.log(f"[devtools] Failed to create branch '{name}'.")
                        self._set_status("branches", f"Failed to create '{name}'.", ok=False)
                Clock.schedule_once(_update)
            except Exception as exc:
                self.host.log(f"[devtools] Error creating branch '{name}': {exc}")
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
                MDButton(
                    MDButtonIcon(icon="delete-outline"),
                    MDButtonText(text="Delete"),
                    style="filled",
                    on_release=_delete,
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

    def _do_delete_branch(self, name: str) -> None:
        token = self._auth.token
        if not token:
            return
        self.host.log(f"[devtools] Deleting branch '{name}'...")
        self._set_status("branches", f"Deleting '{name}'...")

        def _run():
            try:
                ok = self._ci.delete_branch(name, token)
                def _update(dt):
                    if ok:
                        self.host.log(f"[devtools] Branch '{name}' deleted.")
                        self._set_status("branches", f"Branch '{name}' deleted.", ok=True)
                        MDSnackbar(
                            MDSnackbarText(text=f"Branch '{name}' deleted."),
                            pos_hint={"center_x": 0.5, "y": 0.05},
                            size_hint_x=0.6, duration=3,
                        ).open()
                        self._refresh_branches()
                    else:
                        self.host.log(f"[devtools] Failed to delete branch '{name}'.")
                        self._set_status("branches", f"Failed to delete '{name}'.", ok=False)
                Clock.schedule_once(_update)
            except Exception as exc:
                self.host.log(f"[devtools] Error deleting branch '{name}': {exc}")
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
            self.host.log(f"[devtools] Could not open URL ({exc}): {url}")
