"""App configuration — persisted to ~/.clueme/config.json."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".clueme"
CONFIG_FILE = CONFIG_DIR / "config.json"

_defaults = {
    "google_api_key": "",
    "assemblyai_api_key": "",
    "tavily_api_key": "",
    "model": "gemma-4-31b-it",
    "thinking_level": "HIGH",
    "speaker_device": "",  # "" = system default loopback
    "mic_device": "",      # "" = disabled
    "debug_logging": False,
    "auto_name": "first_stop",        # "every_stop" | "first_stop" | "never"
    "transcription_method": "local_whisper",  # "local_whisper" | "assemblyai"
    "whisper_model": "tiny",           # "tiny" | "base" | "small" | "turbo"
}


def load() -> dict:
    """Load config from disk, merging with defaults."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return {**_defaults, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_defaults)


def save(config: dict) -> None:
    """Save config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def apply_env(config: dict | None = None) -> None:
    """Set environment variables from config (if keys are non-empty).

    Call this early, before any google.genai imports read the env.
    """
    if config is None:
        config = load()
    if config.get("google_api_key"):
        os.environ["GOOGLE_API_KEY"] = config["google_api_key"]
    if config.get("assemblyai_api_key"):
        os.environ["ASSEMBLYAI_API_KEY"] = config["assemblyai_api_key"]
