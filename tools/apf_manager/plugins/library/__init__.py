"""
Game Library plugin — provides the home_screen contribution.
"""

from ...core.models.plugin import PluginContribution
from .views.library_screen import LibraryScreen


def setup(host):
    host.register_contribution("apf.builtin.library", PluginContribution(
        type="home_screen",
        plugin_id="apf.builtin.library",
        label="Library",
        icon="view-grid",
        priority=0,
        panel_class=LibraryScreen,
    ))
