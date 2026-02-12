"""System-wide parametric EQ application."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("equaliser")
except PackageNotFoundError:
    __version__ = "0.2.0"  # fallback for dev
