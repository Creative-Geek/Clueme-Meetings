"""AI chat module with decoupled transcript/chat logs."""

from src.agent.client import _get_client, reconfigure_client
from src.agent.model_config import MODEL_NAME, MODELS, set_model_config, get_thinking_level
from src.agent.session_naming import generate_session_title
from src.agent.system_instruction import SYSTEM_INSTRUCTION
from src.agent.meeting_chat import MeetingChat
from src.agent.tools import get_tools_for_model, execute_tool

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
    "get_tools_for_model",
    "execute_tool",
]
