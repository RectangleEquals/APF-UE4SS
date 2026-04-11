"""
Repository Viewer plugin — SPA dialog for reviewing multi-content repos.

Other plugins invoke it via:
    host.show_dialog("repo_viewer",
        repo_url=url,
        game_id=game_id,
        traversal_result=mods,        # list[DiscoveredMod]
        on_confirm=lambda selected: ...,
        on_cancel=lambda: ...,
    )
"""

from ...core.plugin_host import PluginContribution
from .repo_viewer_panel import RepoViewerPanel


def setup(host):
    _panel = RepoViewerPanel(host)

    host.register_service("repo_viewer", _panel)

    host.register_contribution("apf.builtin.repo_viewer.dialog", PluginContribution(
        type="dialog",
        plugin_id="apf.builtin.repo_viewer",
        label="Repository Viewer",
        icon="source-repository",
        dialog_id="repo_viewer",
        handler=lambda **kwargs: _panel.show(**kwargs),
    ))
