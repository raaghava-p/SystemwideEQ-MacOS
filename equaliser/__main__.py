#!/usr/bin/env python3
"""Entry point for `python -m equaliser`."""
from equaliser.runtime import ensure_native_arm64

ensure_native_arm64()

from equaliser.gui import run

# Re-export run for use as entry point (equaliser-app command)
__all__ = ["run"]

if __name__ == "__main__":
    run()
