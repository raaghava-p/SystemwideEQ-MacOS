"""Entry point for `python -m equaliser`."""
from equaliser.runtime import ensure_native_arm64

ensure_native_arm64()

from equaliser.gui import run


if __name__ == "__main__":
    run()
