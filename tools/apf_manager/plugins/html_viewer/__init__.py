"""
HTML Viewer plugin — registers the "html_viewer" service.

Other plugins can use it via:
    svc = host.get_service("html_viewer")
    svc.show("My Doc Title", full_html_string)
"""

from .html_viewer_service import HTMLViewerService


def setup(host) -> None:
    host.register_service("html_viewer", HTMLViewerService())
