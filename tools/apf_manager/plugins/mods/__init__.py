"""
Mod Management plugin — registers the 'mods', 'registry', and 'deploy' services,
and contributes the Mods hub_panel (priority 10).
"""

from .mod_service import ModService, ModInfo
from .registry_service import RegistryService
from .deploy_service import DeployService
from .validation_service import ValidationService
from .mods_panel import ModsPanel
from ...core.plugin_host import PluginContribution


def setup(host):
    # Core mod service (scan, component detection)
    mod_service = ModService(host)
    host.register_service("mods", mod_service)

    # Registry service (GitHub-hosted mod discovery, staging, install)
    registry_service = RegistryService(host)
    host.register_service("registry", registry_service)

    # Deploy service (mods.txt management, deploy/undeploy)
    deploy_service = DeployService(host)
    host.register_service("deploy", deploy_service)

    # Validation service (install/staging/cache health checks)
    validation_service = ValidationService(host)
    host.register_service("validation", validation_service)

    # Hub panel
    host.register_contribution("apf.builtin.mods", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.mods",
        label="Mods",
        icon="package-variant",
        priority=10,
        panel_class=ModsPanel,
    ))
