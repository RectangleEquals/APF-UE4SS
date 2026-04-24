"""
Content pipeline plugin — registers the 'mods', 'registry', 'deploy', and 'validation'
services, and contributes the Content hub_panel (priority 10).
"""

from .services.mod_service import ModService, ModInfo
from .services.registry_service import RegistryService
from .services.deploy_service import DeployService
from .services.validation_service import ValidationService
from .panel import ContentPipelinePanel
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
    host.register_contribution("apf.builtin.content", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.content",
        label="Content",
        icon="package-variant",
        priority=10,
        panel_class=ContentPipelinePanel,
    ))
