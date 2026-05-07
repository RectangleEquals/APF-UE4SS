"""
Content pipeline plugin — registers the 'mods', 'registry', 'deploy', and 'validation'
services, and contributes the Content hub_panel (priority 10).
"""

from .controllers.mods.service import ModService, ModInfo
from .controllers.registry.service import RegistryService
from .controllers.deploy.service import DeployService
from .controllers.validation.service import ValidationService
from .views.pipeline_panel import ContentPipelinePanel
from ...core.models.plugin import PluginContribution


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
