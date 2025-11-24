"""GUI launcher for the EQ application."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from PyQt6 import QtCore
import pkgutil
import ctypes


def _ensure_qt_plugins() -> None:
    """Point Qt at the bundled plugin directory if the env lacks it."""

    plugin_path: Path | None = None
    dist_plugins = (
        Path(__file__).resolve().parents[2]
        / "dist"
        / "Equaliser.app"
        / "Contents"
        / "Resources"
        / f"lib/python{sys.version_info.major}.{sys.version_info.minor}"
        / "PyQt6"
        / "Qt6"
        / "plugins"
    )
    if dist_plugins.is_dir():
        plugin_path = dist_plugins
    if plugin_path is None:
        user_override = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH")
        if user_override and Path(user_override).is_dir():
            plugin_path = Path(user_override)
    if plugin_path is None:
        spec = pkgutil.get_loader("PyQt6")
        if spec and spec.origin:
            rel = Path(spec.origin).parent / "Qt6/plugins"
            if rel.is_dir():
                plugin_path = rel
    if plugin_path is None:
        qt_path = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.PluginsPath)
        if qt_path:
            candidate = Path(qt_path)
            if candidate.is_dir():
                plugin_path = candidate
    if plugin_path is None:
        return
    if not plugin_path.is_dir():
        return
    platform_dir = plugin_path / "platforms"
    if not (platform_dir / "libqcocoa.dylib").exists():
        dist_plugins = Path(__file__).resolve().parents[2] / "dist" / "Equaliser.app" / "Contents" / "Resources" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "PyQt6" / "Qt6" / "plugins"
        if (dist_plugins / "platforms" / "libqcocoa.dylib").exists():
            plugin_path = dist_plugins
            platform_dir = plugin_path / "platforms"
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platform_dir))
    # Try eager load to surface architecture issues early.
    try:
        ctypes.CDLL(str(platform_dir / "libqcocoa.dylib"))
    except OSError:
        pass
    QtCore.QCoreApplication.setLibraryPaths([str(plugin_path)])


_ensure_qt_plugins()

from .main_window import run, EqualiserWindow

__all__ = ["run", "EqualiserWindow"]
