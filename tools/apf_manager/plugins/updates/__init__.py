"""
Updates plugin — registers the 'updates' service and triggers a background
update check shortly after app startup.

No UI contribution (no hub_action) — update notifications surface via:
  - Red dot badge on the Settings gear icon in the Library screen
  - An Updates section in the Settings screen
"""

from kivy.clock import Clock
from .updates_service import UpdatesService


def setup(host):
    svc = UpdatesService(host)
    host.register_service("updates", svc)

    # Trigger the background update check ~2 seconds after startup so that the
    # UI is fully loaded before any status callbacks fire.  The service's own
    # 1-hour TTL prevents redundant checks within an active session.
    Clock.schedule_once(lambda dt: svc.check_all(), 2)
