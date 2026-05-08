"""
Developer Tools plugin — version management, CI, and release tools.

Only loaded in dev mode when launched with --devtools.
"""

from ...core.models.plugin import PluginContribution
from .views.devtools_panel import DevToolsPanel


def setup(host):
    host.register_contribution("apf.builtin.devtools", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.devtools",
        label="Dev Tools",
        icon="wrench-cog",
        priority=99,
        panel_class=DevToolsPanel,
    ))
