"""LiveTranscriber — real-time audio transcription engine.

This module re-exports all components from the transcriber subpackage for backward compatibility.
"""

from src.native_runtime import add_nvidia_runtime_dll_directory

add_nvidia_runtime_dll_directory()

# Re-export everything from the transcriber subpackage modules
from src.transcriber.constants import WHISPER_RATE, RECORD_CHUNK_MS
from src.transcriber.devices.discovery import list_devices
from src.transcriber.live_transcriber import LiveTranscriber

__all__ = [
    "WHISPER_RATE",
    "RECORD_CHUNK_MS",
    "list_devices",
    "LiveTranscriber",
]
