"""mods_section.py — ModsSectionMixin: mod/other row builders for ContentTab."""

from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

from ..chrome.constants import COL_DIM
from ..rows.package_header_row import PackageHeaderWidget


_BG_ROW_EVEN = (0.13, 0.13, 0.13, 1)
_BG_ROW_ODD  = (0.11, 0.11, 0.11, 1)


class ModsSectionMixin:
    """Mod and Other row builders for ContentTab."""

    def _package_header(self, pkg_id: str, pkg_mods: list, collapsed: bool) -> PackageHeaderWidget:
        def _mod_key(m):
            return f"mod:{getattr(m,'folder_name',getattr(m,'folder',getattr(m,'mod_id','')))}"

        any_checked = any(_mod_key(m) in self._checked for m in pkg_mods)

        def _on_pkg_check(val: bool) -> None:
            # Always cascade to ALL children — no early return for partial-check state.
            for m in pkg_mods:
                k = _mod_key(m)
                self._checked.add(k) if val else self._checked.discard(k)
            if hasattr(self, "_sync_queue_btn"):
                self._sync_queue_btn()
            Clock.schedule_once(lambda dt: self._do_refresh(), 0)

        return PackageHeaderWidget(
            pkg_id=pkg_id,
            pkg_label=pkg_id.split("/")[-1] if "/" in pkg_id else pkg_id,
            mod_count=len(pkg_mods),
            any_checked=any_checked,
            on_toggle=lambda: self._toggle_pkg_collapse(f"pkg:{pkg_id}"),
            on_check=_on_pkg_check,
            collapsed=collapsed,
            md_bg_color=(0.10, 0.13, 0.17, 1),
        )

    def _toggle_pkg_collapse(self, key: str) -> None:
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    def _mod_row(self, mod, index: int, indent: bool = False) -> MDBoxLayout:
        from ..rows.content_row import ContentRowWidget
        folder = getattr(mod, "folder_name", getattr(mod, "folder", getattr(mod, "mod_id", str(index))))
        key = f"mod:{folder}"
        expanded = key in self._expanded

        # known_ids: registry-available + installed (so installed deps don't falsely show red)
        known_ids = {getattr(m, "mod_id", "") for m in self._all_mods if getattr(m, "mod_id", "")}
        try:
            from ...models.state.install import InstallStateManager
            for d in InstallStateManager(self._game_id).get_all():
                mid = d.get("mod_id", "")
                if mid:
                    known_ids.add(mid)
        except Exception as exc:
            self._host.log(f"[mods_section] WARN: failed to load install state for known_ids: {exc}")

        # install_record for update-available detection in the detail panel
        install_record = None
        try:
            from ...models.state.install import InstallStateManager
            from ...models.state.pipeline import InstallRecord
            mod_folder = getattr(mod, "folder_name", "")
            if mod_folder:
                for d in InstallStateManager(self._game_id).get_all():
                    if d.get("folder_name") == mod_folder:
                        install_record = InstallRecord.from_dict(d)
                        break
        except Exception as exc:
            self._host.log(f"[mods_section] WARN: failed to load install record for {getattr(mod, 'folder_name', '?')}: {exc}")

        # docs action button on the unexpanded row
        # K-3: readme_url is always a full https://raw.githubusercontent.com/… URL from the
        # resolver — use it directly, no re-wrapping.
        actions = []
        _docs = getattr(mod, "docs", None)
        if _docs and getattr(_docs, "readme_url", ""):
            _title = getattr(mod, "name", folder)

            def _open_readme(*_, url=_docs.readme_url, title=_title):
                self._ctrl.open_docs_url(url, title=title)

            actions.append({"icon": "file-document-outline", "tooltip": "View Readme",
                            "callback": _open_readme})

        # Detect associated BP subfolders bundled with this mod (Gap B).
        _comps = getattr(mod, "components", None)
        bp_subfolders = list(getattr(_comps, "bp_subfolders", None) or []) if _comps else []
        valid_bp_sfs = [sf for sf in bp_subfolders if sf.get("is_valid")]

        # Combined detail widget: ContentDetailPanel + BP subfolders section when expanded
        detail_widget = None
        if expanded and valid_bp_sfs:
            detail_widget = self._build_mod_bp_detail(
                mod, key, valid_bp_sfs, install_record, known_ids
            )

        outer = MDBoxLayout(orientation="vertical", size_hint_y=None, adaptive_height=True)
        row_widget = ContentRowWidget(
            content=mod, row_index=index,
            checked=key in self._checked, expanded=expanded,
            on_check=lambda val, k=key: self._on_check(k, val),
            on_expand=lambda *_: self._toggle_expand(key),
            actions=actions,
            known_mod_ids=known_ids,
            install_record=install_record,
            detail_widget=detail_widget,
        )
        if indent:
            inner = MDBoxLayout(orientation="horizontal", size_hint_y=None, adaptive_height=True)
            inner.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(16),
                                         md_bg_color=row_widget.md_bg_color))
            inner.add_widget(row_widget)
            outer.add_widget(inner)
        else:
            outer.add_widget(row_widget)
        return outer

    def _build_mod_bp_detail(self, mod, key: str, valid_bp_sfs: list,
                              install_record, known_ids) -> MDBoxLayout:
        """Combined detail widget: ContentDetailPanel + associated BP subfolders section."""
        from ..panels.content_detail_panel import ContentDetailPanel
        from ..chrome.constants import COL_DIM

        combined = MDBoxLayout(orientation="vertical", size_hint_y=None, adaptive_height=True)

        # Standard mod detail panel
        detail_panel = ContentDetailPanel(
            content=mod, install_record=install_record, known_mod_ids=known_ids
        )
        combined.add_widget(detail_panel)

        # Associated BP subfolders section
        bp_section = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(4), dp(8), dp(8)], spacing=dp(4),
        )
        sep = MDBoxLayout(size_hint_y=None, height=dp(1), md_bg_color=(0.2, 0.2, 0.25, 1))
        bp_section.add_widget(sep)
        bp_section.add_widget(MDLabel(
            text="Associated Blueprint Mods",
            font_style="Label", role="small",
            size_hint_y=None, height=dp(18),
            theme_text_color="Custom", text_color=COL_DIM,
        ))

        parent_checked = key in self._checked
        for sf in valid_bp_sfs:
            sf_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(28),
                padding=[dp(8), 0, 0, 0], spacing=dp(8),
            )
            chk = MDCheckbox(
                size_hint=(None, None), size=(dp(20), dp(20)),
                pos_hint={"center_y": 0.5},
                disabled=True,
            )
            chk.active = parent_checked
            sf_row.add_widget(chk)
            sf_row.add_widget(MDLabel(
                text=sf.get("name", ""),
                font_style="Label", role="small",
                size_hint=(1, 1),
            ))
            bp_type_str = _bp_type_str(sf.get("files", []))
            if bp_type_str:
                sf_row.add_widget(MDLabel(
                    text=bp_type_str,
                    font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(88),
                    halign="right",
                    theme_text_color="Custom", text_color=COL_DIM,
                ))
            bp_section.add_widget(sf_row)

        combined.add_widget(bp_section)
        return combined

    def _open_other_docs(self, docs_path: str, owner: str, repo: str,
                          registry_owner: str = "", registry_repo: str = "") -> None:
        raw_owner = registry_owner or owner
        raw_repo  = registry_repo  or repo
        raw_url = f"https://raw.githubusercontent.com/{raw_owner}/{raw_repo}/HEAD/{docs_path}"
        title = docs_path.rsplit("/", 1)[-1].replace("_", " ").replace(".md", "").title()
        self._ctrl.open_docs_url(raw_url, title=title)

    def _other_row(self, item, index: int) -> MDBoxLayout:
        from ..rows.content_row import ContentRowWidget
        from ...models.descriptors.types import GithubReleaseBinary as _GRB
        is_grb = isinstance(item, _GRB)
        if is_grb:
            _hash = item.tags.content_hash if item.tags else ""
            _src = item.source
            key = (f"other:{_hash}" if _hash else
                   f"other:{_src.repo.owner if _src else ''}+{_src.repo.repo if _src else ''}/{_src.tag if _src else item.name}")
        else:
            key = f"other:{getattr(item, 'name', str(index))}"
        expanded = key in self._expanded

        # K-5 Fix B: GRB parent checkbox cascades down to all assets (downward cascade).
        # Upward cascade (assets → parent) is handled in _other_detail/_on_asset_check.
        if is_grb:
            _assets = item.assets or []
            def _grb_on_check(val, k=key, assets=_assets):
                self._on_check(k, val)
                for a in assets:
                    a.selected = val
                if hasattr(self, "_sync_queue_btn"):
                    self._sync_queue_btn()
                Clock.schedule_once(lambda dt: self._do_refresh(), 0)
            on_check_cb = lambda val, k=key: _grb_on_check(val)
        else:
            on_check_cb = lambda val, k=key: self._on_check(k, val)

        # K-11 Fix B: docs action button when item.docs is present (same pattern as _mod_row).
        actions = []
        _docs = getattr(item, "docs", None)
        if _docs and getattr(_docs, "readme_url", ""):
            _title = getattr(item, "name", "Docs")

            def _open_docs(*_, url=_docs.readme_url, title=_title):
                self._ctrl.open_docs_url(url, title=title)

            actions.append({"icon": "file-document-outline", "tooltip": "View Docs",
                            "callback": _open_docs})

        outer_detail = self._other_detail(item, outer_key=key) if expanded else None
        outer = MDBoxLayout(orientation="vertical", size_hint_y=None, adaptive_height=True)
        outer.add_widget(ContentRowWidget(
            content=item, row_index=index,
            checked=key in self._checked,
            expanded=expanded,
            on_check=on_check_cb,
            on_expand=lambda *_: self._toggle_expand(key),
            actions=actions,
            detail_widget=outer_detail,
        ))
        return outer

    def _other_detail(self, item, outer_key: str = "") -> MDBoxLayout:
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(6), dp(8), dp(8)], spacing=dp(4),
        )

        from ...models.descriptors.types import GithubReleaseBinary as _GRB
        if isinstance(item, _GRB):
            _src     = item.source
            install_type = item.install_type
            opt_type     = "github_release"
            owner        = _src.repo.owner if _src else ""
            repo_        = _src.repo.repo if _src else ""
            tag          = _src.tag if _src else ""
            published_at = _src.published_at if _src else ""
            changelog    = _src.changelog if _src else ""
            prerelease   = _src.is_prerelease if _src else False
            assets       = item.assets or []
            asset_name   = assets[0].name if assets else ""
        else:
            install_type = getattr(item, "install_type", "ue4ss")
            opt_type     = getattr(item, "type", "manual")
            owner        = getattr(item, "owner", "")
            repo_        = getattr(item, "repo", "")
            tag          = getattr(item, "tag", "")
            published_at = getattr(item, "published_at", "")
            asset_name   = getattr(item, "asset_name", "")
            changelog    = getattr(item, "changelog", "")
            prerelease   = getattr(item, "prerelease", False)
            assets       = getattr(item, "assets", []) or []

        if install_type == "framework_binary":
            type_label = "Framework Binaries"
        elif opt_type == "manual":
            type_label = "Manual Installation"
        else:
            type_label = "UE4SS experimental" if prerelease else "UE4SS stable"

        def _detail_row(key_text: str, val_text: str) -> MDBoxLayout:
            r = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(8))
            r.add_widget(MDLabel(
                text=key_text, font_style="Label", role="small",
                size_hint=(None, 1), width=dp(96),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            r.add_widget(MDLabel(
                text=val_text, font_style="Label", role="small",
                size_hint=(1, 1),
            ))
            return r

        panel.add_widget(_detail_row("Type", type_label))
        if owner and repo_:
            panel.add_widget(_detail_row("Source", f"{owner}/{repo_}"))
        if tag:
            panel.add_widget(_detail_row("Tag", tag))
        if published_at:
            panel.add_widget(_detail_row("Published", published_at[:10]))
        if asset_name and not assets:
            panel.add_widget(_detail_row("Asset", asset_name))

        if opt_type == "manual":
            panel.add_widget(MDLabel(
                text="This option requires manual installation. Refer to the UE4SS documentation for this game.",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(36),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

        if assets:
            sep = MDBoxLayout(size_hint_y=None, height=dp(1), md_bg_color=(0.2, 0.2, 0.25, 1))
            panel.add_widget(sep)
            panel.add_widget(MDLabel(
                text="Assets", font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

            def _on_asset_check(asset, val, ok=outer_key):
                asset.selected = val
                any_selected = any(a.selected for a in assets)
                if not any_selected and ok in self._checked:
                    self._checked.discard(ok)
                    self._sync_queue_btn()
                elif any_selected and ok not in self._checked:
                    self._checked.add(ok)
                    self._sync_queue_btn()
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self._do_refresh(), 0)

            for asset in assets:
                asset_row = MDBoxLayout(
                    orientation="horizontal", size_hint_y=None, height=dp(28),
                    padding=[dp(8), 0, 0, 0], spacing=dp(8),
                )
                chk = MDCheckbox(
                    size_hint=(None, None), size=(dp(20), dp(20)),
                    pos_hint={"center_y": 0.5},
                )
                chk.active = asset.selected
                chk.bind(active=lambda inst, val, a=asset: _on_asset_check(a, val))
                asset_row.add_widget(chk)
                asset_row.add_widget(MDLabel(
                    text=asset.name, font_style="Label", role="small",
                    size_hint=(1, 1),
                ))
                sz = getattr(asset, "size_bytes", None) or getattr(asset, "size", 0) or 0
                if sz:
                    asset_row.add_widget(MDLabel(
                        text=_fmt_bytes(sz), font_style="Label", role="small",
                        size_hint=(None, 1), width=dp(72),
                        halign="right", theme_text_color="Custom", text_color=COL_DIM,
                    ))
                panel.add_widget(asset_row)

        if changelog:
            _name = getattr(item, "name", "Release Notes")

            def _show_changelog(*_, _cl=changelog, _nm=_name):
                self._ctrl.show_inline_docs(
                    content=_cl,
                    title=f"{_nm} — Release Notes",
                    sidebar_mode="verbose",
                    allow_mode_toggle=False,
                )

            panel.add_widget(MDButton(
                MDButtonText(text="Release Notes"),
                style="text",
                size_hint_y=None, height=dp(36),
                on_release=_show_changelog,
            ))

        return panel


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


def _bp_type_str(files: list) -> str:
    """Return a short BP file-type label (PAK, UCAS/UTOC, PAK+UCAS/UTOC) from a file list."""
    exts = {f.rsplit(".", 1)[-1].lower() for f in files if "." in f}
    if "pak" in exts and ("ucas" in exts or "utoc" in exts):
        return "PAK+UCAS/UTOC"
    if "ucas" in exts or "utoc" in exts:
        return "UCAS/UTOC"
    if "pak" in exts:
        return "PAK"
    return ""
