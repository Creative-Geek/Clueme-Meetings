"""Gemini chat — direct google.genai client with decoupled logs.

This module re-exports all components from the agent subpackage for backward compatibility.
"""

from dotenv import load_dotenv

load_dotenv()

# Re-export everything from the agent subpackage modules
from src.agent.client import _get_client, reconfigure_client
from src.agent.model_config import MODEL_NAME, MODELS, set_model_config, get_thinking_level
from src.agent.session_naming import generate_session_title
from src.agent.system_instruction import SYSTEM_INSTRUCTION
from src.agent.meeting_chat import MeetingChat

__all__ = [
    "_get_client",
    "reconfigure_client",
    "MODEL_NAME",
    "MODELS",
    "set_model_config",
    "get_thinking_level",
    "generate_session_title",
    "SYSTEM_INSTRUCTION",
    "MeetingChat",
]
