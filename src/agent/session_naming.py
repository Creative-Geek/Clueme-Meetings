"""Session title generation using AI."""

import asyncio
from google.genai import types

from src import debug_log
from src.agent.client import _get_client

_TITLE_INSTRUCTION = (
    "Generate a short meeting title (3-6 words) from the transcript excerpt below. "
    "{sample_context}Reply with ONLY the title, no quotes, no punctuation at the end."
)

_SAMPLE_CONTEXT = "The excerpt is a SAMPLE from the beginning, middle, and end of a longer meeting (marked with '...' separators). "


def _get_representative_excerpt(text: str, max_chars: int = 2500) -> tuple[str, bool]:
    """Extract representative text from beginning, middle, and end of transcript.
    
    Returns (excerpt, was_sampled) tuple.
    This avoids biasing the title toward early audio debugging/setup conversations.
    Future enhancement: implement 5-minute interval fact extraction to generate
    a structured list of key points, then use those for more accurate titling.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text, False  # Not sampled
    
    chunk_size = max_chars // 3
    start = text[:chunk_size]
    mid_start = len(text) // 2 - chunk_size // 2
    middle = text[mid_start:mid_start + chunk_size]
    end = text[-chunk_size:]
    return f"{start}\n...\n{middle}\n...\n{end}", True  # Sampled


async def generate_session_title(transcript_text: str) -> str:
    """Generate a short AI title from transcript content.

    Returns 'Untitled Session' on error or empty transcript.
    Uses smart sampling from beginning, middle, and end to avoid bias from
    early setup/debugging conversations. Retries once on failure.
    """
    excerpt, was_sampled = _get_representative_excerpt(transcript_text.strip())
    if not excerpt:
        return "Untitled Session"
    
    # Use dynamic system prompt based on whether transcript was sampled
    sample_context = _SAMPLE_CONTEXT if was_sampled else ""
    instruction = _TITLE_INSTRUCTION.format(sample_context=sample_context)
    
    # Retry mechanism: attempt twice before giving up
    for attempt in range(2):
        try:
            response = await _get_client().aio.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=[  # pyrefly: ignore
                    types.Content(
                        role="user",
                        parts=[types.Part(text=excerpt)],
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
                ),
            )
            title = (response.text or "").strip().strip("\"'").strip()
            return title if title else "Untitled Session"
        except Exception as e:
            if attempt == 0:
                # Retry once on first failure
                continue
            # Log error and return fallback on second failure
            debug_log.log_event("AUTO_NAME", f"ERROR: {e}")
    
    return "Untitled Session"
