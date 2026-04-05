"""
Mod Discovery plugin — registers the 'mods' and 'registry' services,
and contributes the 6-tab Mods hub_panel (priority 10).
"""

from .mod_service import ModService, ModInfo
from .registry_service import RegistryService
from .mods_panel import ModsPanel
from ...core.plugin_host import PluginContribution


def setup(host):
    # Core mod discovery service (used by deploy, load order, etc.)
    mod_service = ModService(host)
    host.register_service("mods", mod_service)

    # Registry service (GitHub-hosted mod discovery, staging, install)
    registry_service = RegistryService(host)
    host.register_service("registry", registry_service)

    # Hub panel — replaces apf.builtin.deploy's former panel contribution
    host.register_contribution("apf.builtin.mods", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.mods",
        label="Mods",
        icon="package-variant",
        priority=10,
        panel_class=ModsPanel,
    ))
