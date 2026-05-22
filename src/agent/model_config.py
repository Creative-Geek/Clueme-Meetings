"""Model configuration for AI chat."""

import os

MODEL_NAME = os.getenv("GOOGLE_MODEL_NAME", "gemini-3.1-flash-lite")

# Model → allowed thinking levels
MODELS = {
    "gemini-3.1-flash-lite": {
        "display": "Gemini 3.1 Flash Lite",
        "levels": ["MINIMAL", "LOW", "MEDIUM", "HIGH"],
    },
    "gemma-4-31b-it": {
        "display": "Gemma 4 31B IT",
        "levels": ["MINIMAL", "HIGH"],
    },
}

_thinking_level: str = "HIGH"


def set_model_config(model: str, thinking_level: str) -> None:
    """Update the active model and thinking level at runtime."""
    global MODEL_NAME, _thinking_level
    MODEL_NAME = model
    _thinking_level = thinking_level


def get_thinking_level() -> str:
    """Get the current thinking level."""
    return _thinking_level
