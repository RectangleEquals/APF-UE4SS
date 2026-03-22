"""
Manifesto Editor plugin (dev only) — stub panel.

Full implementation is deferred. See plan for scope.
"""

from ...core.plugin_host import PluginContribution
from .manifesto_panel import ManifestoPanel


def setup(host):
    host.register_contribution("apf.builtin.manifesto", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.manifesto",
        label="Manifesto",
        icon="pencil-ruler",
        priority=90,
        panel_class=ManifestoPanel,
    ))
