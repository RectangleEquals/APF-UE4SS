"""
AP Configuration plugin — registers the 'ap_config' service and Configure panel.
"""

from ...core.plugin_host import PluginContribution
from .config_service import APConfigService
from .config_panel import APConfigPanel


def setup(host):
    svc = APConfigService()
    host.register_service("ap_config", svc)

    host.register_contribution("apf.builtin.ap_config", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.ap_config",
        label="Configure",
        icon="tune",
        priority=20,
        panel_class=APConfigPanel,
    ))
