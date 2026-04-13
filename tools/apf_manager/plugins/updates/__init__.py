"""
Updates plugin — registers the 'updates' service and contributes
a hub_action toolbar button for app/APWorld update notifications.
"""

from .updates_service import UpdatesService


def setup(host):
    svc = UpdatesService(host)
    host.register_service("updates", svc)
