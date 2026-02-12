"""GUI launcher for the EQ application."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import pkgutil


def _ensure_qt_plugins() -> None:
    """Point Qt at the bundled plugin directory BEFORE importing PyQt6.

    CRITICAL: This must be called before any PyQt6 imports because Qt's
    plugin paths are resolved at first import time.
    """
    plugin_path: Path | None = None

    # Try to find PyQt6 installation via pkgutil (doesn't trigger Qt init)
    loader = pkgutil.get_loader("PyQt6")
    if loader and hasattr(loader, "get_filename"):
        origin = loader.get_filename()
        if origin:
            rel = Path(origin).parent / "Qt6" / "plugins"
            if rel.is_dir():
                plugin_path = rel

    # Fallback: Check standard venv location
    if plugin_path is None:
        venv_plugins = (
            Path(sys.prefix) / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages" / "PyQt6" / "Qt6" / "plugins"
        )
        if venv_plugins.is_dir():
            plugin_path = venv_plugins

    # Fallback: Check for bundled app
    if plugin_path is None:
        dist_plugins = (
            Path(__file__).resolve().parents[2]
            / "dist" / "Equaliser.app" / "Contents" / "Resources"
            / f"lib/python{sys.version_info.major}.{sys.version_info.minor}"
            / "PyQt6" / "Qt6" / "plugins"
        )
        if dist_plugins.is_dir():
            plugin_path = dist_plugins

    # User override takes precedence
    user_override = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH")
    if user_override and Path(user_override).is_dir():
        # User already set a valid path, respect it
        return

    if plugin_path is None or not plugin_path.is_dir():
        return

    platform_dir = plugin_path / "platforms"
    if not platform_dir.is_dir():
        return

    # Set environment variables BEFORE any Qt import
    os.environ["QT_PLUGIN_PATH"] = str(plugin_path)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platform_dir)


# CRITICAL: Set plugin paths BEFORE importing PyQt6
_ensure_qt_plugins()

# Now safe to import PyQt6
from PyQt6 import QtCore

from .main_window import run, EqualiserWindow

__all__ = ["run", "EqualiserWindow"]
