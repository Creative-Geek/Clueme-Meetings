"""Chat tab — message history with AI responses.

This module re-exports all components from the chat subpackage for backward compatibility.
"""

# Re-export everything from the chat subpackage modules
from src.ui.chat.stream_chunk import StreamChunk
from src.ui.chat.user_bubble import UserBubble
from src.ui.chat.assistant_bubble import AssistantBubble
from src.ui.chat.chat_tab import ChatTab

__all__ = [
    "StreamChunk",
    "UserBubble",
    "AssistantBubble",
    "ChatTab",
]
