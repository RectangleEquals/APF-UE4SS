"""
Deployment Manager plugin — registers the 'deploy' service.

Requires: apf.builtin.mods

Registered services:
    "deploy"  → DeployService  (get_load_order, set_enabled, reorder, deploy_all)

The hub_panel contribution (Load Order + Deploy tabs) is now provided by apf.builtin.mods.
"""

from .deploy_service import DeployService


def setup(host):
    svc = DeployService(host)
    host.register_service("deploy", svc)