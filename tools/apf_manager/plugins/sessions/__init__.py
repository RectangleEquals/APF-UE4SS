"""
Session Manager plugin — registers 'sessions' service and Sessions panel.
"""

from ...core.models.plugin import PluginContribution
from .session_manager import SessionManager
from .sessions_panel import SessionsPanel


def setup(host):
    svc = SessionManager()
    host.register_service("sessions", svc)

    host.register_contribution("apf.builtin.sessions", PluginContribution(
        type="hub_panel",
        plugin_id="apf.builtin.sessions",
        label="Sessions",
        icon="backup-restore",
        priority=30,
        panel_class=SessionsPanel,
    ))
