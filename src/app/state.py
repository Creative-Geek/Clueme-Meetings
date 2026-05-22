"""App state - initializes application state."""

from src.config import load as load_config
from src.agent import set_model_config
from src.session_context import SessionManager


def initialize_state():
    """Initialize application state and return components."""
    cfg = load_config()
    transcriber = None
    manager = SessionManager()

    # Apply saved model config
    set_model_config(
        cfg.get("model", "gemma-4-31b-it"), cfg.get("thinking_level", "HIGH")
    )

    return cfg, transcriber, manager
