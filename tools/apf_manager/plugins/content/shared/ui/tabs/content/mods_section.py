"""mods_section.py — ModsSectionMixin: mod/other row builders for ContentTab."""

from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox

from .....shared.ui.constants import COL_CPP, COL_BP, COL_DIM, COL_WARN
from .....shared.ui.hover_row import HoverRow


_BG_ROW_EVEN = (0.13, 0.13, 0.13, 1)
_BG_ROW_ODD  = (0.11, 0.11, 0.11, 1)


class ModsSectionMixin:
    """Mod and Other row builders for ContentTab."""

    def _package_header(self, pkg_id: str, pkg_mods: list, collapsed: bool) -> MDBoxLayout:
        key = f"pkg:{pkg_id}"
        bg = (0.10, 0.13, 0.17, 1)
        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg,
        )
        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            padding=[dp(8), dp(4)], spacing=dp(8),
        )
        def _mod_key(m):
            return f"mod:{getattr(m,'folder_name',getattr(m,'folder',getattr(m,'mod_id','')))}"
        all_checked = all(_mod_key(m) in self._checked for m in pkg_mods)
        cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                        pos_hint={"center_y": 0.5})
        cb.active = all_checked
        def _on_pkg_check(inst, val, mods=pkg_mods):
            for m in mods:
                k = _mod_key(m)
                if val:
                    self._checked.add(k)
                else:
                    self._checked.discard(k)
        cb.bind(active=_on_pkg_check)
        header.add_widget(cb)
        header.add_widget(MDIcon(
            icon="package-variant-closed", size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=(0.5, 0.6, 0.9, 1),
        ))
        pkg_label = pkg_id.split("/")[-1] if "/" in pkg_id else pkg_id
        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        info.add_widget(MDLabel(
            text=pkg_label, font_style="Body",
            size_hint_y=None, height=dp(24),
        ))
        info.add_widget(MDLabel(
            text=f"{len(pkg_mods)} components  ·  {pkg_id}",
            font_style="Label", role="small",
            size_hint_y=None, height=dp(18),
            theme_text_color="Custom", text_color=COL_DIM,
        ))
        info.bind(on_touch_down=lambda w, t: self._toggle_pkg_collapse(key)
                  if w.collide_point(*t.pos) else None)
        header.add_widget(info)
        chevron_icon = "chevron-up" if not collapsed else "chevron-down"
        header.add_widget(MDIconButton(
            icon=chevron_icon,
            size_hint=(None, None), size=(dp(32), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, k=key: self._toggle_pkg_collapse(k),
        ))
        container.add_widget(header)
        return container

    def _toggle_pkg_collapse(self, key: str) -> None:
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)

    def _mod_row(self, mod, index: int, indent: bool = False) -> MDBoxLayout:
        folder = getattr(mod, "folder_name", getattr(mod, "folder", getattr(mod, "mod_id", str(index))))
        key = f"mod:{folder}"
        _comp_raw = getattr(mod, "components", None)
        components = _comp_raw.types if hasattr(_comp_raw, "types") else (_comp_raw if isinstance(_comp_raw, list) else ["lua"])
        bg = _BG_ROW_EVEN if index % 2 == 0 else _BG_ROW_ODD
        expanded = key in self._expanded

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg,
        )

        left_pad = dp(24) if indent else dp(8)
        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52),
            padding=[left_pad, dp(4), dp(8), dp(4)], spacing=dp(8),
        )

        cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                        pos_hint={"center_y": 0.5})
        cb.active = key in self._checked
        cb.bind(active=lambda inst, val, k=key, m=mod: self._on_mod_check(k, val, m))
        header.add_widget(cb)

        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))

        name_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(4),
        )
        display = getattr(mod, "name", folder)
        name_row.add_widget(MDLabel(
            text=display, font_style="Body", size_hint=(1, 1),
            halign="left", valign="middle",
        ))
        if "cpp" in components:
            name_row.add_widget(MDIcon(
                icon="code-braces",
                size_hint=(None, None), size=(dp(20), dp(20)),
                pos_hint={"center_y": 0.5},
                theme_icon_color="Custom", icon_color=COL_CPP,
            ))
        if "blueprint" in components:
            name_row.add_widget(MDIcon(
                icon="blueprint",
                size_hint=(None, None), size=(dp(20), dp(20)),
                pos_hint={"center_y": 0.5},
                theme_icon_color="Custom", icon_color=COL_BP,
            ))
        info.add_widget(name_row)

        mod_id = getattr(mod, "mod_id", "")
        desc   = getattr(mod, "description", "")
        if mod_id:
            sub = mod_id
        elif desc:
            sub = desc
        else:
            sub = "Non-AP Mod"
        if sub:
            info.add_widget(MDLabel(
                text=sub, font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        info.bind(on_touch_down=lambda w, t: self._toggle_expand(key)
                  if w.collide_point(*t.pos) else None)
        header.add_widget(info)

        chevron_icon = "chevron-up" if expanded else "chevron-down"
        header.add_widget(MDIconButton(
            icon=chevron_icon,
            size_hint=(None, None), size=(dp(32), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, k=key: self._toggle_expand(k),
        ))
        container.add_widget(header)

        if expanded:
            container.add_widget(self._mod_detail(mod))
        return container

    def _mod_detail(self, mod) -> MDBoxLayout:
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(6), dp(8), dp(8)], spacing=dp(4),
        )
        mod_id = getattr(mod, "mod_id", "")
        desc   = getattr(mod, "description", "")
        owner  = getattr(mod, "owner", "")
        repo   = getattr(mod, "repo", "")

        if desc:
            panel.add_widget(MDLabel(
                text=desc, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Secondary",
            ))
        elif not mod_id:
            panel.add_widget(MDLabel(
                text="This is a regular UE4SS mod that does not directly contribute toward "
                     "Archipelago randomization on its own.",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(32),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        else:
            panel.add_widget(MDLabel(
                text="No description",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=COL_DIM,
            ))

        if mod_id:
            panel.add_widget(MDLabel(
                text=mod_id, font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.5, 0.7, 0.9, 1),
            ))

        known_ids = {getattr(m, "mod_id", "") for m in self._all_mods}
        depends = getattr(mod, "depends", []) or []
        if depends:
            dep_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(16),
                spacing=dp(4),
            )
            dep_row.add_widget(MDLabel(
                text="Deps:", font_style="Label", role="small",
                size_hint=(None, 1), width=dp(32),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            for dep in depends[:5]:
                dep_id = dep.split(" ")[0] if isinstance(dep, str) else str(dep)
                missing = dep_id not in known_ids
                dep_row.add_widget(MDLabel(
                    text=dep_id, font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(max(80, len(dep_id) * 7)),
                    theme_text_color="Custom",
                    text_color=(0.9, 0.3, 0.3, 1) if missing else COL_DIM,
                ))
            panel.add_widget(dep_row)

        incompatible = getattr(mod, "incompatible", []) or []
        if incompatible:
            panel.add_widget(MDLabel(
                text="Incompatible: " + ", ".join(str(i) for i in incompatible[:4]),
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.8, 0.5, 0.2, 1),
            ))

        includes = getattr(mod, "capabilities_includes", []) or []
        if includes:
            fw_dir = self._fw_dir
            for inc in includes[:4]:
                present = False
                if fw_dir:
                    from pathlib import Path
                    present = (Path(fw_dir) / inc).exists()
                inc_row = MDBoxLayout(
                    orientation="horizontal", size_hint_y=None, height=dp(16), spacing=dp(4),
                )
                inc_row.add_widget(MDIcon(
                    icon="circle-small", size_hint=(None, 1), width=dp(14),
                    theme_icon_color="Custom",
                    icon_color=(0.3, 0.8, 0.4, 1) if present else COL_WARN,
                ))
                inc_row.add_widget(MDLabel(
                    text=inc, font_style="Label", role="small",
                    size_hint=(1, 1), halign="left",
                    theme_text_color="Custom",
                    text_color=COL_DIM if present else COL_WARN,
                ))
                panel.add_widget(inc_row)

        if getattr(mod, "is_submodule_content", False):
            panel.add_widget(MDLabel(
                text=f"from submodule: {owner}/{repo}",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=(0.6, 0.7, 0.9, 1),
            ))

        if owner and repo:
            reg_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(8),
            )
            reg_row.add_widget(MDLabel(
                text=f"{owner}/{repo}", font_style="Label", role="small",
                size_hint=(1, 1), halign="left",
                theme_text_color="Custom", text_color=COL_DIM,
            ))
            panel.add_widget(reg_row)
        return panel

    def _open_other_docs(self, docs_path: str, owner: str, repo: str,
                          registry_owner: str = "", registry_repo: str = "") -> None:
        docs_svc = self._host.get_service("docs_viewer") if self._host.has_service("docs_viewer") else None
        if not docs_svc:
            return
        raw_owner = registry_owner or owner
        raw_repo  = registry_repo  or repo
        raw_url = f"https://raw.githubusercontent.com/{raw_owner}/{raw_repo}/HEAD/{docs_path}"
        title = docs_path.rsplit("/", 1)[-1].replace("_", " ").replace(".md", "").title()
        if hasattr(docs_svc, "open_url"):
            docs_svc.open_url(raw_url, title=title, show_sidebar=True, show_mode_toggle=False)

    def _other_row(self, item, index: int) -> MDBoxLayout:
        from .....shared.data.content_types import GithubReleaseBinary as _GRB
        if isinstance(item, _GRB):
            _src  = item.source
            opt_type = "github_release"
            tag      = _src.tag if _src else ""
            owner    = _src.repo.owner if _src else ""
            repo_    = _src.repo.repo if _src else ""
            _hash    = item.tags.content_hash if item.tags else ""
        else:
            opt_type = getattr(item, "type", "manual")
            tag      = getattr(item, "tag", "")
            owner    = getattr(item, "owner", "")
            repo_    = getattr(item, "repo", "")
            _hash    = getattr(item, "content_hash", "")
        if _hash:
            key = f"other:{_hash}"
        else:
            key = f"other:{owner}+{repo_}/{tag or getattr(item, 'name', str(index))}"
        bg       = _BG_ROW_EVEN if index % 2 == 0 else _BG_ROW_ODD
        expanded = key in self._expanded

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=bg,
        )

        if opt_type == "github_release":
            header = HoverRow(
                orientation="horizontal", size_hint_y=None, height=dp(52),
                padding=[dp(8), dp(4)], spacing=dp(8),
            )
        else:
            header = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(52),
                padding=[dp(8), dp(4)], spacing=dp(8),
            )

        if opt_type == "github_release":
            cb = MDCheckbox(size_hint=(None, None), size=(dp(24), dp(24)),
                            pos_hint={"center_y": 0.5})
            cb.active = key in self._checked
            cb.bind(active=lambda inst, val, k=key: self._on_check(k, val))
            header.add_widget(cb)
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(24)))

        header.add_widget(MDIcon(
            icon="package-variant", size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=(0.8, 0.55, 0.1, 1),
        ))

        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        name_lbl = getattr(item, "name", "Unknown")
        info.add_widget(MDLabel(
            text=name_lbl, font_style="Body",
            size_hint_y=None, height=dp(24),
        ))
        from .....shared.data.content_types import GithubReleaseBinary as _GRB
        if isinstance(item, _GRB):
            _src = item.source
            if item.install_type == "framework_binary":
                note = f"framework binaries  \u00b7  {_src.repo.full_name if _src else ''}"
            elif _src and _src.is_prerelease:
                note = f"experimental  \u00b7  {_src.repo.full_name}"
            else:
                note = f"stable  \u00b7  {_src.repo.full_name if _src else ''}"
            _assets = item.assets or []
        else:
            note = getattr(item, "note", "")
            _assets = getattr(item, "assets", []) or []
        _n_sel = sum(1 for a in _assets if getattr(a, "selected", False))
        if _assets and 0 < _n_sel < len(_assets):
            note = f"{note}   ({_n_sel}/{len(_assets)} assets)" if note else f"({_n_sel}/{len(_assets)} assets selected)"
        if note:
            info.add_widget(MDLabel(
                text=note, font_style="Label", role="small",
                size_hint_y=None, height=dp(18),
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        from .....shared.data.content_types import GithubReleaseBinary as _GRB
        _has_dup = (item.tags.has_duplicate_source if isinstance(item, _GRB) and item.tags
                    else getattr(item, "has_duplicate_source", False))
        if _has_dup:
            info.add_widget(MDLabel(
                text="duplicate source",
                font_style="Label", role="small",
                size_hint_y=None, height=dp(14),
                theme_text_color="Custom", text_color=(1.0, 0.75, 0.0, 1),
            ))
        if opt_type != "manual":
            info.bind(on_touch_down=lambda w, t: self._toggle_expand(key)
                      if w.collide_point(*t.pos) else None)
        header.add_widget(info)

        _docs_path = "" if isinstance(item, _GRB) else getattr(item, "docs", "")
        if _docs_path:
            _docs_owner = getattr(item, "owner", "")
            _docs_repo  = getattr(item, "repo",  "")
            _reg_owner  = getattr(item, "registry_owner", "")
            _reg_repo   = getattr(item, "registry_repo",  "")
            header.add_widget(MDIconButton(
                icon="file-document-outline",
                size_hint=(None, None), size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, dpath=_docs_path, do=_docs_owner, dr=_docs_repo, ro=_reg_owner, rr=_reg_repo: (
                    self._open_other_docs(dpath, do, dr, ro, rr)
                ),
            ))
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(32)))

        if opt_type == "external_url":
            import webbrowser
            url = getattr(item, "url", "")
            header.add_widget(MDButton(
                MDButtonText(text="Open"),
                style="outlined", size_hint=(None, None), size=(dp(72), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, u=url: webbrowser.open(u) if u else None,
            ))
        elif opt_type == "github_release":
            chevron_icon = "chevron-up" if expanded else "chevron-down"
            header.add_widget(MDIconButton(
                icon=chevron_icon,
                size_hint=(None, None), size=(dp(32), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, k=key: self._toggle_expand(k),
            ))
        else:
            header.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(40)))

        container.add_widget(header)

        if expanded:
            container.add_widget(self._other_detail(item, outer_key=key))
        return container

    def _other_detail(self, item, outer_key: str = "") -> MDBoxLayout:
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.09, 0.10, 0.12, 1),
            padding=[dp(16), dp(6), dp(8), dp(8)], spacing=dp(4),
        )

        from .....shared.data.content_types import GithubReleaseBinary as _GRB
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
                docs_svc = self._host.get_service("docs_viewer") if self._host.has_service("docs_viewer") else None
                if docs_svc and hasattr(docs_svc, "show_inline"):
                    docs_svc.show_inline(
                        content=_cl,
                        title=f"{_nm} — Release Notes",
                        sidebar_mode="verbose",
                        allow_mode_toggle=False,
                    )
                else:
                    from kivymd.uix.dialog import (
                        MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
                        MDDialogButtonContainer,
                    )
                    dlg_ref = [None]
                    def _close(*_):
                        if dlg_ref[0]:
                            dlg_ref[0].dismiss()
                    dlg = MDDialog(
                        MDDialogHeadlineText(text="Release Notes"),
                        MDDialogSupportingText(text=_cl[:500]),
                        MDDialogButtonContainer(
                            MDButton(MDButtonText(text="Close"), style="text", on_release=_close),
                        ),
                    )
                    dlg_ref[0] = dlg
                    dlg.open()

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
