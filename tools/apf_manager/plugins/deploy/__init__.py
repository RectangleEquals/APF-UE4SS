"""
Deployment Manager plugin — registers the 'deploy' service and hub_panel contribution.

Requires: apf.builtin.mods

Registered services:
    "deploy"  → DeployService  (get_load_order, set_enabled, reorder, deploy_all)
"""

from ...core.plugin_host import PluginContribution
from .deploy_service import DeployService
from .deploy_panel import DeployPanel


def setup(host):
    svc = DeployService(host)
    host.register_service("deploy", svc)

    host.register_contribution("apf.builtin.deploy", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.deploy",
        label="Mods",
        icon="package-variant",
        priority=10,
        panel_class=DeployPanel,
    ))