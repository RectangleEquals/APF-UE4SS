"""
Release Packager plugin (dev only) — builds release ZIPs and .apworld files.
"""

from ...core.plugin_host import PluginContribution
from .packager_panel import PackagerPanel


def setup(host):
    host.register_contribution("apf.builtin.packager", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.packager",
        label="Package",
        icon="package-up",
        priority=80,
        panel_class=PackagerPanel,
    ))
