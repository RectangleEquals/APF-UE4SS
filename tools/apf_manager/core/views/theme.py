"""
Shared UI theme constants for APF Manager.
"""

# Status icon name and RGBA color tuples used across the app.
# Keys: "ok", "warn", "error", "unknown"
STATUS_ICONS: dict[str, tuple[str, tuple[float, float, float, float]]] = {
    "ok":      ("check-circle",  (0.3,  0.8,  0.4,  1.0)),
    "warn":    ("alert",         (0.95, 0.75, 0.1,  1.0)),
    "error":   ("close-circle",  (0.85, 0.25, 0.25, 1.0)),
    "unknown": ("help-circle",   (0.5,  0.5,  0.5,  1.0)),
}
