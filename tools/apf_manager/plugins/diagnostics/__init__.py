"""
Diagnostics plugin — validation + log packaging.
"""

from ...core.plugin_host import PluginContribution
from .diagnostics_panel import DiagnosticsPanel


def setup(host):
    host.register_contribution("apf.builtin.diagnostics", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.diagnostics",
        label="Diagnostics",
        icon="stethoscope",
        priority=40,
        panel_class=DiagnosticsPanel,
    ))
