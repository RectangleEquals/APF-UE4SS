"""
installed_row_widget.py — InstalledRowWidget: typed row widget for the Installed tab.

Wraps ContentRowWidget for the generic row body and adds install-specific overlays:
  - Registry/managed/orphaned source badge
  - Update-available badge (checks local cache)
  - Live component health chips (filesystem-derived)
  - Uninstall as a composable action entry in ContentRowWidget
  - Expanded detail via ContentDetailPanel with install_record
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel
import logging

_log = logging.getLogger(__name__)

from ..chrome.badge_bar import BadgeBar
from ..chrome.badges import badge_icon, badge_text
from ..chrome.constants import COL_WARN

if TYPE_CHECKING:
    from ...models.state.pipeline import InstallRecord


_COL_MANAGED = (0.3, 0.8, 0.6, 1)
_COL_UPDATE  = (0.25, 0.65, 1.0, 1)


class InstalledRowWidget(MDBoxLayout):
    """
    Typed row widget for the Installed tab.

    Uses ContentRowWidget for the generic row body. Adds install-specific
    badges (managed/orphaned, update-available) and live component health.

    Parameters
    ----------
    install_record  : InstallRecord — primary data source
    detection       : DetectionResult or None — for filesystem health checks
    deploy_svc      : DeployService or None — reserved for future inline actions
    row_index       : int — alternating background
    expanded        : bool — initial expanded state
    on_expand       : Callable — called when the user clicks the expand area
    on_uninstall    : Callable — called when the Uninstall action is triggered
    is_orphaned     : bool — mod is on disk but not tracked in install state
    """

    def __init__(
        self,
        install_record: "InstallRecord",
        detection,
        deploy_svc,
        row_index: int = 0,
        expanded: bool = False,
        on_expand: Optional[Callable] = None,
        on_uninstall: Optional[Callable] = None,
        is_orphaned: bool = False,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            **kwargs,
        )
        self._record    = install_record
        self._detection = detection
        self._deploy_svc = deploy_svc
        self._row_index  = row_index
        self._expanded   = expanded
        self._on_expand  = on_expand
        self._on_uninstall = on_uninstall
        self._is_orphaned  = is_orphaned
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.clear_widgets()
        from .content_row import ContentRowWidget
        from ...models.descriptors.types import (
            APModDescriptor, FrameworkModDescriptor, ThirdPartyModDescriptor,
            ModComponents,
        )
        from ...models.descriptors.base import RegistrySource, GitHubRepo

        r = self._record

        # Determine the correct typed class from the install record
        if r.content_type == "framework_mod":
            content_cls = FrameworkModDescriptor
        elif r.content_type == "ap_mod":
            content_cls = APModDescriptor
        else:
            content_cls = ThirdPartyModDescriptor

        # Reconstruct source reference if available
        source = None
        if r.source_repo:
            source = RegistrySource(
                repo=GitHubRepo.from_full_name(r.source_repo),
                registry_url=r.source_registry_url,
                folder=r.source_folder,
            )

        components = ModComponents.from_lists(
            r.components or [], r.bp_pak_files_deployed or []
        )

        # Build typed descriptor — AP types get mod_id and capabilities_includes
        base_kwargs = dict(
            name=r.name,
            version=r.version,
            game_id=r.game_id,
            folder_name=r.folder_name,
            description=r.description,
            author=r.author,
            source=source,
            components=components,
        )
        if issubclass(content_cls, APModDescriptor):
            content = content_cls(
                **base_kwargs,
                mod_id=r.mod_id,
                capabilities_includes=list(r.capabilities_includes or []),
            )
        else:
            content = content_cls(**base_kwargs)

        # Uninstall as a composable action passed into ContentRowWidget
        actions = []
        if self._on_uninstall:
            def _trigger_uninstall(*_, fn=self._on_uninstall):
                fn()
            actions.append({
                "icon": "delete-outline",
                "tooltip": "Uninstall",
                "callback": _trigger_uninstall,
            })

        row_widget = ContentRowWidget(
            content=content,
            row_index=self._row_index,
            checked=None,   # Installed tab has no checkboxes
            expanded=self._expanded,
            on_expand=self._on_expand,
            actions=actions,
            install_record=self._record,
        )
        self.add_widget(row_widget)

        # ------------------------------------------------------------------
        # Overlay bar: source badge + update-available badge
        # ------------------------------------------------------------------
        bar = BadgeBar()

        if self._is_orphaned:
            bar.add_widget(badge_icon("folder-account", COL_WARN, "Manually installed"))
            bar.add_widget(MDLabel(
                text="Orphaned — not tracked by APF Manager",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=COL_WARN,
            ))
        elif r.source_repo:
            label = r.source_repo.split("/")[-1] if "/" in r.source_repo else r.source_repo
            bar.add_widget(badge_text(label, _COL_MANAGED))
            bar.add_widget(MDLabel(size_hint=(1, 1)))
        else:
            bar.add_widget(badge_text("Managed", _COL_MANAGED))
            bar.add_widget(MDLabel(size_hint=(1, 1)))

        update_ver = self._check_update()
        if update_ver:
            upd = MDBoxLayout(
                orientation="horizontal", size_hint=(None, 1), width=dp(180), spacing=dp(4),
            )
            upd.add_widget(MDIcon(
                icon="arrow-up-circle", size_hint=(None, 1), width=dp(16),
                theme_icon_color="Custom", icon_color=_COL_UPDATE,
            ))
            upd.add_widget(MDLabel(
                text=f"v{update_ver} available",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=_COL_UPDATE,
            ))
            bar.add_widget(upd)

        self.add_widget(bar)

        # ------------------------------------------------------------------
        # Expanded detail panel (component health chips rendered inside)
        # ------------------------------------------------------------------
        if self._expanded:
            from ..panels.content_detail_panel import ContentDetailPanel
            component_status = self._compute_component_status()
            self.add_widget(ContentDetailPanel(
                content=content,
                install_record=self._record,
                component_health=component_status or None,
            ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_update(self) -> str:
        """Return cached version string if newer than installed, else empty string."""
        r = self._record
        if not r.source_repo or not r.folder_name:
            return ""
        from ...models.state.pipeline import ContentSerializer
        cache_dir = Path.home() / ".apf_manager" / "cache"
        owner_repo = r.source_repo.replace("/", "+")
        mod_cache = cache_dir / owner_repo / r.folder_name
        result = ContentSerializer().load_cache(mod_cache, log_fn=_log.warning)
        if not result:
            return ""
        cached_content, _ = result
        cached_ver = cached_content.version
        if not cached_ver or cached_ver == r.version:
            return ""
        try:
            from .....core.models.semver import SemVer
            if SemVer(cached_ver) > SemVer(r.version or "0.0.0"):
                return cached_ver
        except Exception as exc:
            _log.warning("[installed_row] WARN: semver compare failed for %s: %s", r.folder_name, exc)
            if r.version and cached_ver != r.version:
                return cached_ver
        return ""

    def _compute_component_status(self) -> dict:
        """Return per-component filesystem presence status for the installed mod."""
        r = self._record
        detection = self._detection
        if not detection or not r.folder_name:
            return {}
        components = r.components or []
        if not components:
            return {}
        mods_dir      = detection.ue4ss.mods_dir      if detection.ue4ss else None
        logicmods_dir = detection.ue4ss.logicmods_dir if detection.ue4ss else None
        fn = r.folder_name
        status: dict = {}
        if "lua" in components:
            status["lua"] = bool(
                mods_dir and (mods_dir / fn / "scripts" / "main.lua").exists()
            )
        if "cpp" in components:
            status["cpp"] = bool(
                mods_dir and (mods_dir / fn / "dlls" / "main.dll").exists()
            )
        if "blueprint" in components:
            paks = r.bp_pak_files_deployed or []
            status["blueprint"] = bool(paks) and all(
                logicmods_dir and (logicmods_dir / p).exists()
                for p in paks
            )
        return status
