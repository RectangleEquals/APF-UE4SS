"""
Documentation Viewer plugin — hub_action toolbar button + dialog contribution.

Other plugins can invoke it via:
    host.show_dialog("docs_viewer", path="docs/public/dev/mods.md")

Or as a service:
    host.get_service("docs_viewer").open(path="...")
"""

from ...core.models.plugin import PluginContribution
from .views.docs_panel import DocsPanel


def setup(host):
    _panel = DocsPanel(host)

    host.register_service("docs_viewer", _panel)

    host.register_contribution("apf.builtin.docs_viewer.action", PluginContribution(
        type="hub_action",
        plugin_id="apf.builtin.docs_viewer",
        label="Docs",
        icon="book-open-variant",
        handler=lambda: _panel.open(),
    ))

    host.register_contribution("apf.builtin.docs_viewer.dialog", PluginContribution(
        type="dialog",
        plugin_id="apf.builtin.docs_viewer",
        label="Documentation Viewer",
        icon="book-open-variant",
        dialog_id="docs_viewer",
        handler=lambda path=None: _panel.open(path=path),
    ))
