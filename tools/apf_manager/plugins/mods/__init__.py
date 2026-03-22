"""
Mod Discovery plugin — registers the 'mods' service.

No UI contributions. All other plugins that need mod metadata call:
  host.get_service("mods")
"""

from .mod_service import ModService, ModInfo


def setup(host):
    service = ModService(host)
    host.register_service("mods", service)
