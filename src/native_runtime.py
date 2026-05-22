"""Native runtime DLL discovery for optional GPU transcription."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES = []


def _app_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def add_nvidia_runtime_dll_directory() -> Path | None:
    """Register the app-private NVIDIA runtime directory on Windows."""
    if os.name != "nt":
        return None

    nvidia_dir = _app_root() / "runtime" / "nvidia" / "cuda12"
    if not nvidia_dir.exists():
        return None

    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(nvidia_dir)))

    path = os.environ.get("PATH", "")
    nvidia_path = str(nvidia_dir)
    path_parts = path.split(os.pathsep) if path else []
    if nvidia_path not in path_parts:
        os.environ["PATH"] = nvidia_path + (os.pathsep + path if path else "")

    return nvidia_dir
