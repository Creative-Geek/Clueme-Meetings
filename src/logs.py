"""Decoupled transcript + chat logs with time-based assembly.

Two independent logs (TranscriptLog, ChatLog) are merged just-in-time
into a Gemini-compatible message list before each API call.
"""

from dataclasses import dataclass
import time

from google.genai import types


def _format_minute(epoch_minute: int) -> str:
    """Convert epoch-minutes to local HH:MM string."""
    t = time.localtime(epoch_minute * 60)
    return f"{t.tm_hour:02d}:{t.tm_min:02d}"


@dataclass(frozen=True)
class TranscriptEntry:
    text: str
    minute: int  # system-time minute (epoch // 60)


@dataclass(frozen=True)
class ChatEntry:
    role: str   # "user" or "model"
    text: str
    minute: int


class TranscriptLog:
    """Append-only, immutable log of confirmed transcript chunks."""

    def __init__(self):
        self._entries: list[TranscriptEntry] = []

    def append(self, text: str, minute: int) -> None:
        self._entries.append(TranscriptEntry(text=text, minute=minute))

    @property
    def entries(self) -> list[TranscriptEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def to_dicts(self) -> list[dict]:
        return [{"text": e.text, "minute": e.minute} for e in self._entries]

    def load_dicts(self, data: list[dict]) -> None:
        self._entries = [TranscriptEntry(**d) for d in data]


class ChatLog:
    """Mutable log of user/model messages. Supports truncation for editing."""

    def __init__(self):
        self._entries: list[ChatEntry] = []

    def append(self, role: str, text: str, minute: int) -> None:
        self._entries.append(ChatEntry(role=role, text=text, minute=minute))

    @property
    def entries(self) -> list[ChatEntry]:
        return list(self._entries)

    def truncate_from(self, index: int) -> None:
        """Remove entry at index and all after it (for message editing)."""
        self._entries = self._entries[:index]

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def to_dicts(self) -> list[dict]:
        return [{"role": e.role, "text": e.text, "minute": e.minute} for e in self._entries]

    def load_dicts(self, data: list[dict]) -> None:
        self._entries = [ChatEntry(**d) for d in data]


def _collect_transcript_blocks(
    entries: list[TranscriptEntry],
    start_idx: int,
    up_to_minute: int,
) -> tuple[list[str], int]:
    """Group transcript entries by minute into [Meeting Update t=N] blocks.

    Returns (blocks, new_idx) where new_idx is the next unprocessed index.
    """
    blocks: list[str] = []
    current_minute: int | None = None
    current_texts: list[str] = []
    idx = start_idx

    while idx < len(entries) and entries[idx].minute <= up_to_minute:
        entry = entries[idx]
        if entry.minute != current_minute:
            if current_texts:
                blocks.append(
                    f"[Meeting Update {_format_minute(current_minute)}]\n{' '.join(current_texts)}"
                )
            current_minute = entry.minute
            current_texts = [entry.text]
        else:
            current_texts.append(entry.text)
        idx += 1

    if current_texts:
        blocks.append(
            f"[Meeting Update {_format_minute(current_minute)}]\n{' '.join(current_texts)}"
        )

    return blocks, idx


def assemble_api_messages(
    transcript_log: TranscriptLog,
    chat_log: ChatLog,
    tentative_text: str = "",
) -> list[types.Content]:
    """Merge transcript and chat logs into alternating user/model Content list.

    Transcript entries are prepended to the next user chat message as
    [Meeting Update t=N] blocks. Tentative text is injected into the
    last user message as an ephemeral [Live Audio] block.
    """
    chat_entries = chat_log.entries
    transcript_entries = transcript_log.entries
    has_transcript = bool(transcript_entries) or bool(tentative_text and tentative_text.strip())
    messages: list[types.Content] = []
    t_idx = 0

    for chat_entry in chat_entries:
        if chat_entry.role == "user":
            # Consume transcript entries up to this user message's minute
            blocks, t_idx = _collect_transcript_blocks(
                transcript_entries, t_idx, up_to_minute=chat_entry.minute
            )
            # If no transcript at all, tell the AI explicitly
            if not has_transcript and not blocks:
                blocks.append("[No transcript captured yet — the meeting recording has not started or no speech detected.]")
            blocks.append(chat_entry.text)
            messages.append(types.Content(
                role="user",
                parts=[types.Part(text="\n\n".join(blocks))],
            ))

        elif chat_entry.role == "model":
            messages.append(types.Content(
                role="model",
                parts=[types.Part(text=chat_entry.text)],
            ))

    # Remaining transcript entries (after the last chat message)
    # These exist if transcript continued after the last user question.
    # They'll be picked up on the next send() call.

    # Inject tentative text into the last user message
    if tentative_text.strip() and messages and messages[-1].role == "user":
        existing_text = messages[-1].parts[0].text
        messages[-1] = types.Content(
            role="user",
            parts=[types.Part(
                text=existing_text + f"\n\n[Live Audio]\n{tentative_text.strip()}"
            )],
        )

    return messages
