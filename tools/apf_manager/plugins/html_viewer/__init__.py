"""
HTML Viewer plugin — registers the "html_viewer" service.

Other plugins can use it via:
    svc = host.get_service("html_viewer")
    svc.show("My Doc Title", full_html_string)
"""

from .controllers.service import HTMLViewerService
from .views.viewer_overlay import ViewerOverlay


def setup(host) -> None:
    svc = HTMLViewerService()
    overlay = ViewerOverlay()
    svc.register_overlay(overlay)
    host.register_service("html_viewer", svc)
