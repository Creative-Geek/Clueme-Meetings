"""Settings dialog — API keys, model, transcription, audio, debug.

This module re-exports the SettingsDialog class from the settings subpackage for backward compatibility.
"""

# Re-export everything from the settings subpackage
from src.ui.settings.settings_dialog import SettingsDialog

__all__ = [
    "SettingsDialog",
]
