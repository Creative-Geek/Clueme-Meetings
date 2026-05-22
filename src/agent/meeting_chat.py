"""Meeting chat class with decoupled transcript/chat logs."""

import asyncio
from typing import AsyncGenerator

from google.genai import types

from src.logs import TranscriptLog, ChatLog, assemble_api_messages
from src.ui.chat_tab import StreamChunk
from src import debug_log
from src.agent.client import _get_client
from src.agent import model_config
from src.agent.system_instruction import SYSTEM_INSTRUCTION
from src.agent.tools import get_tools_for_model, execute_tool
from src.config import load as load_config

# Maximum tool-call iterations per response to prevent infinite loops
_MAX_TOOL_ITERATIONS = 3


class MeetingChat:
    """Manages chat with decoupled transcript/chat logs."""

    def __init__(self, transcript_log: TranscriptLog, chat_log: ChatLog):
        self.transcript_log = transcript_log
        self.chat_log = chat_log
        self._cancel_event = asyncio.Event()

    def cancel(self):
        """Signal the current stream to stop."""
        self._cancel_event.set()

    # ── Public API ───────────────────────────────────────────────────────────

    async def send(
        self,
        user_message: str,
        minute: int,
        tentative_text: str = "",
        images: list[str] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Send a message, yielding streamed response chunks.

        Args:
            user_message: The user's question or command.
            minute: Current minute offset from recording start.
            tentative_text: Unconfirmed transcript text (ephemeral).
            images: Base64-encoded image attachments.

        Yields:
            StreamChunk objects (thinking or response text).
        """
        self.chat_log.append(role="user", text=user_message, minute=minute, images=images)
        contents = list(assemble_api_messages(self.transcript_log, self.chat_log, tentative_text))
        debug_log.log_ai_payload(contents, model_config.MODEL_NAME)

        self._cancel_event.clear()
        full_response = ""
        async for chunk in self._generate(contents):
            full_response += chunk.text if not chunk.is_thought else ""
            yield chunk

        if full_response:
            self.chat_log.append(role="model", text=full_response, minute=minute)
            debug_log.log_ai_response(full_response, model_config.MODEL_NAME)

    async def resend(
        self,
        minute: int,
        tentative_text: str = "",
    ) -> AsyncGenerator[StreamChunk, None]:
        """Re-send the last user message (already in ChatLog) without appending it.

        Used by retry — the user entry is already in the log from the
        original send(). Only streams and appends the model response.
        """
        contents = list(assemble_api_messages(self.transcript_log, self.chat_log, tentative_text))
        debug_log.log_ai_payload(contents, model_config.MODEL_NAME)

        self._cancel_event.clear()
        full_response = ""
        async for chunk in self._generate(contents):
            full_response += chunk.text if not chunk.is_thought else ""
            yield chunk

        if full_response:
            self.chat_log.append(role="model", text=full_response, minute=minute)
            debug_log.log_ai_response(full_response, model_config.MODEL_NAME)

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

    # ── Internal: tool-call loop ─────────────────────────────────────────────

    async def _generate(self, contents: list) -> AsyncGenerator[StreamChunk, None]:
        """Stream a response, handling tool calls transparently.

        Yields StreamChunk objects for thinking and text parts.

        When the model returns function_call parts (Tavily/manual path):
          - Executes each tool call
          - Appends model turn + tool responses to contents
          - Loops to get the model's final text response

        For built-in google_search (Gemma/Gemini 2.x):
          - No function_call parts are ever returned — search is server-side
          - The loop exits after the first iteration
        """
        cfg = load_config()
        tavily_key = cfg.get("tavily_api_key", "")
        tools = get_tools_for_model(model_config.MODEL_NAME, tavily_key)

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            thinking_config=types.ThinkingConfig(thinking_level=model_config.get_thinking_level()),
            tools=tools or None,  # pyrefly: ignore
        )

        for _iteration in range(_MAX_TOOL_ITERATIONS):
            stream = await _get_client().aio.models.generate_content_stream(
                model=model_config.MODEL_NAME,
                contents=contents,  # pyrefly: ignore
                config=config,
            )

            function_calls: list[types.FunctionCall] = []
            model_parts: list[types.Part] = []

            async for chunk in stream:
                if self._cancel_event.is_set():
                    return

                if not chunk.candidates:
                    continue
                content = chunk.candidates[0].content
                if content is None:
                    continue

                for part in content.parts or []:
                    model_parts.append(part)
                    if part.function_call:
                        # Collect for execution after stream ends
                        function_calls.append(part.function_call)
                    elif part.text:
                        if part.thought:
                            yield StreamChunk(text=part.text, is_thought=True)
                        else:
                            yield StreamChunk(text=part.text, is_thought=False)

            # No function calls or cancelled — final response received
            if not function_calls or self._cancel_event.is_set():
                return

            # Append the model's function_call turn to contents
            contents.append(types.Content(role="model", parts=model_parts))  # pyrefly: ignore

            # Execute each tool and collect responses
            tool_parts: list[types.Part] = []
            for fc in function_calls:
                if not fc.name:
                    continue
                args = fc.args or {}
                debug_log.log_tool_call(fc.name, args)
                result = await execute_tool(fc.name, args, tavily_key)
                debug_log.log_tool_result(fc.name, result)
                tool_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result},
                    )
                )
            contents.append(types.Content(role="tool", parts=tool_parts))  # pyrefly: ignore

            # Loop: next iteration gets model's final text response
