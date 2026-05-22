"""Stream chunk dataclass for AI responses."""

from dataclasses import dataclass


@dataclass
class StreamChunk:
    """A chunk yielded during streaming — either thinking or response text."""

    text: str
    is_thought: bool = False
