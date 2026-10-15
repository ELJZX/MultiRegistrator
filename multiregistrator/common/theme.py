"""Application-wide light (white) theme.

Qt 6.5+ follows the operating system color scheme on Windows, which turns the
interface dark when Windows runs in dark mode.  :func:`apply_light_theme` forces
a light color scheme so both the server and the client always stay white
regardless of the OS setting.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _build_light_palette() -> QPalette:
    """Return a light palette that keeps every widget on a white background."""

    palette = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    palette.setColor(role.Window, QColor(0xF0, 0xF0, 0xF0))
    palette.setColor(role.WindowText, QColor(0x00, 0x00, 0x00))
    palette.setColor(role.Base, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(role.AlternateBase, QColor(0xF7, 0xF7, 0xF7))
    palette.setColor(role.ToolTipBase, QColor(0xFF, 0xFF, 0xDC))
    palette.setColor(role.ToolTipText, QColor(0x00, 0x00, 0x00))
    palette.setColor(role.Text, QColor(0x00, 0x00, 0x00))
    palette.setColor(role.Button, QColor(0xF0, 0xF0, 0xF0))
    palette.setColor(role.ButtonText, QColor(0x00, 0x00, 0x00))
    palette.setColor(role.BrightText, QColor(0xFF, 0x00, 0x00))
    palette.setColor(role.Link, QColor(0x00, 0x5A, 0xC8))
    palette.setColor(role.Highlight, QColor(0x30, 0x8C, 0xC6))
    palette.setColor(role.HighlightedText, QColor(0xFF, 0xFF, 0xFF))

    if hasattr(role, "PlaceholderText"):
        palette.setColor(role.PlaceholderText, QColor(0x80, 0x80, 0x80))

    grey = QColor(0x78, 0x78, 0x78)
    for disabled_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(group.Disabled, disabled_role, grey)
    palette.setColor(group.Disabled, role.Base, QColor(0xF0, 0xF0, 0xF0))

    return palette


def _force_light_color_scheme(app: QApplication) -> None:
    """Ask Qt to ignore the OS dark mode (Qt 6.5+ exposes the color scheme)."""

    try:
        from PySide6.QtCore import Qt

        hints = app.styleHints()
        setter = getattr(hints, "setColorScheme", None)
        if setter is not None:
            setter(Qt.ColorScheme.Light)
    except (ImportError, AttributeError, TypeError):
        pass


def apply_light_theme(app: QApplication) -> None:
    """Force the whole application into the light (white) theme."""

    _force_light_color_scheme(app)
    app.setPalette(_build_light_palette())
