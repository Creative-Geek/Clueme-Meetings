"""Transcriber module - real-time audio transcription."""

from src.transcriber.constants import WHISPER_RATE, RECORD_CHUNK_MS
from src.transcriber.devices.discovery import list_devices
from src.transcriber.live_transcriber import LiveTranscriber

__all__ = [
    "WHISPER_RATE",
    "RECORD_CHUNK_MS",
    "list_devices",
    "LiveTranscriber",
]
