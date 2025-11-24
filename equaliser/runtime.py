"""Runtime helpers for launching the GUI application."""
from __future__ import annotations

import os
import platform
import shutil
import sys
from typing import List

import ctypes
import subprocess


def _running_under_rosetta() -> bool:
    """Detect Rosetta translation via sysctl.proc_translated."""

    if sys.platform != "darwin":
        return False
    libc = ctypes.CDLL("libc.dylib", use_errno=True)
    value = ctypes.c_int(0)
    size = ctypes.c_size_t(ctypes.sizeof(value))
    name = b"sysctl.proc_translated"
    result = libc.sysctlbyname(name, ctypes.byref(value), ctypes.byref(size), None, 0)
    if result == 0:
        return bool(value.value)
    try:
        output = subprocess.check_output(
            ["/usr/sbin/sysctl", "-in", "sysctl.proc_translated"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return output == "1"
    except Exception:
        return False


def ensure_native_arm64() -> None:
    """Re-exec the process using the arm64 slice when needed."""

    if sys.platform != "darwin":
        return
    if platform.machine() == "arm64" and not _running_under_rosetta():
        return
    if os.environ.get("EQUALISER_ARM64_REEXEC") == "1":
        return
    arch_tool = shutil.which("arch")
    if not arch_tool:
        return
    env = os.environ.copy()
    env["EQUALISER_ARM64_REEXEC"] = "1"
    args: List[str] = [arch_tool, "-arm64", sys.executable, "-m", "equaliser"]
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])
    os.execve(arch_tool, args, env)
