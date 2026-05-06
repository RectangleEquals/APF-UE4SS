"""controllers/download — re-exports DownloadService for clean plugin imports."""
from .service import DownloadService, download_github_folder, collect_files

__all__ = ["DownloadService", "download_github_folder", "collect_files"]
