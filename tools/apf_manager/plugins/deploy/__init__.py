"""
Deployment Manager plugin — registers the 'deploy' service.

Requires: apf.builtin.mods

Registered services:
    "deploy"  → DeployService  (get_load_order, set_enabled, reorder, remove_entry)

The hub_panel contribution (Load Order + Install tabs) is provided by apf.builtin.mods.
"""

from .deploy_service import DeployService


def setup(host):
    svc = DeployService(host)
    host.register_service("deploy", svc)