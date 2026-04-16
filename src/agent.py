"""Gemini chat — direct google.genai client with decoupled logs.

Uses TranscriptLog + ChatLog assembled just-in-time into API messages.
No ADK dependency — calls google.genai streaming API directly.
"""

import os
import logging
import asyncio
from typing import AsyncGenerator

from dotenv import load_dotenv
import google.genai as genai
from google.genai import types

from src.logs import TranscriptLog, ChatLog, assemble_api_messages
from src.ui.chat_tab import StreamChunk
from src import debug_log

load_dotenv()

logging.getLogger("google.genai").setLevel(logging.ERROR)

MODEL_NAME = os.getenv("GOOGLE_MODEL_NAME", "gemini-3.1-flash-lite-preview")

# Model → allowed thinking levels
MODELS = {
    "gemini-3.1-flash-lite-preview": {
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


SYSTEM_INSTRUCTION = """\
You are a helpful meeting assistant. The user is attending a live meeting.

Throughout the conversation, you will see two kinds of context mixed in
with the user's messages:

1. [Meeting Update HH:MM] — confirmed transcript of what was said in the
   meeting, timestamped by wall-clock time. Use these to understand the
   discussion.

2. [Live Audio] — tentative, unconfirmed transcription of what is being
   said right now. Treat as potentially incomplete or inaccurate.

Help the user by answering questions about the meeting, summarizing
discussion, clarifying points, and providing insights. Be concise and
conversational. Use markdown when helpful. If no transcript is available,
answer based on prior context.
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def reconfigure_client(api_key: str = "") -> None:
    """Recreate the genai client (e.g. after API key change)."""
    global _client
    # Explicitly close the old client's transport to avoid RecursionError
    # when GC finalizes it while httpx connections are still open.
    old = _client
    _client = None
    if old is not None:
        try:
            # genai.Client wraps an httpx client; close it explicitly
            if hasattr(old, "_api_client") and hasattr(
                old._api_client, "_httpx_client"
            ):
                old._api_client._httpx_client.close()
        except Exception:
            pass
    if api_key:
        _client = genai.Client(api_key=api_key)
    else:
        _client = genai.Client()


_TITLE_INSTRUCTION = (
    "Generate a short meeting title (3-6 words) from the transcript excerpt below. "
    "Reply with ONLY the title, no quotes, no punctuation at the end."
)


async def generate_session_title(transcript_text: str) -> str:
    """Generate a short AI title from transcript content.

    Returns 'Untitled Session' on error or empty transcript.
    """
    excerpt = transcript_text.strip()[:500]
    if not excerpt:
        return "Untitled Session"
    try:
        response = await _get_client().aio.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=excerpt)],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=_TITLE_INSTRUCTION,
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            ),
        )
        title = response.text.strip().strip("\"'").strip()
        return title if title else "Untitled Session"
    except Exception:
        return "Untitled Session"


class MeetingChat:
    """Manages chat with decoupled transcript/chat logs."""

    def __init__(self, transcript_log: TranscriptLog, chat_log: ChatLog):
        self.transcript_log = transcript_log
        self.chat_log = chat_log
        self._cancel_event = asyncio.Event()

    def cancel(self):
        """Signal the current stream to stop."""
        self._cancel_event.set()

    async def send(
        self,
        user_message: str,
        minute: int,
        tentative_text: str = "",
    ) -> AsyncGenerator[StreamChunk, None]:
        """Send a message, yielding streamed response chunks.

        Args:
            user_message: The user's question or command.
            minute: Current minute offset from recording start.
            tentative_text: Unconfirmed transcript text (ephemeral).

        Yields:
            StreamChunk objects (thinking or response text).
        """
        # Record user message
        self.chat_log.append(role="user", text=user_message, minute=minute)

        # Build assembled contents
        contents = assemble_api_messages(
            self.transcript_log, self.chat_log, tentative_text
        )
        debug_log.log_ai_payload(contents, MODEL_NAME)

        # Stream response
        full_response = ""
        self._cancel_event.clear()
        stream = await _get_client().aio.models.generate_content_stream(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                thinking_config=types.ThinkingConfig(thinking_level=_thinking_level),
            ),
        )
        async for chunk in stream:
            if self._cancel_event.is_set():
                break
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                if not part.text:
                    continue
                if part.thought:
                    yield StreamChunk(text=part.text, is_thought=True)
                else:
                    full_response += part.text
                    yield StreamChunk(text=part.text, is_thought=False)

        # Record model response (even partial if cancelled)
        if full_response:
            self.chat_log.append(role="model", text=full_response, minute=minute)
            debug_log.log_ai_response(full_response, MODEL_NAME)

    def pop_last_model_response(self) -> str | None:
        """Remove the last model entry from ChatLog, return the user text before it.

        The user entry is kept in ChatLog (it will be re-used by resend).
        Returns None if the log doesn't end with a model entry.
        """
        entries = self.chat_log.entries
        if len(entries) >= 2 and entries[-1].role == "model":
            self.chat_log.truncate_from(len(entries) - 1)  # remove model only
            return entries[-2].text  # user text still in log
        return None

    async def resend(
        self,
        minute: int,
        tentative_text: str = "",
    ) -> AsyncGenerator[StreamChunk, None]:
        """Re-send the last user message (already in ChatLog) without appending it.

        Used by retry — the user entry is already in the log from the
        original send(). Only streams and appends the model response.
        """
        contents = assemble_api_messages(
            self.transcript_log, self.chat_log, tentative_text
        )
        debug_log.log_ai_payload(contents, MODEL_NAME)

        full_response = ""
        self._cancel_event.clear()
        stream = await _get_client().aio.models.generate_content_stream(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                thinking_config=types.ThinkingConfig(thinking_level=_thinking_level),
            ),
        )
        async for chunk in stream:
            if self._cancel_event.is_set():
                break
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                if not part.text:
                    continue
                if part.thought:
                    yield StreamChunk(text=part.text, is_thought=True)
                else:
                    full_response += part.text
                    yield StreamChunk(text=part.text, is_thought=False)

        if full_response:
            self.chat_log.append(role="model", text=full_response, minute=minute)
            debug_log.log_ai_response(full_response, MODEL_NAME)
