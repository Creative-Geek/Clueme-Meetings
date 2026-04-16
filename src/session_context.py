"""Session context manager — per-session state with multi-session support.

Tracks two independent pointers:
  - recording_path: which session the transcriber writes to (max one)
  - viewed_path: which session is shown in the meeting view (freely switchable)
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.agent import MeetingChat
from src.logs import TranscriptLog, ChatLog
from src.sessions import (
    create_session,
    load_session,
    update_session,
)


@dataclass
class SessionContext:
    """Bundle of per-session state."""

    path: Path
    transcript_log: TranscriptLog = field(default_factory=TranscriptLog)
    chat_log: ChatLog = field(default_factory=ChatLog)
    chat: MeetingChat = field(init=False)

    def __post_init__(self):
        self.chat = MeetingChat(
            transcript_log=self.transcript_log,
            chat_log=self.chat_log,
        )

    def save(self) -> None:
        """Persist logs to disk."""
        update_session(self.path, self.transcript_log, self.chat_log)


class SessionManager:
    """Manages multiple loaded SessionContexts."""

    def __init__(self):
        self._contexts: dict[Path, SessionContext] = {}
        self._recording_path: Path | None = None
        self._viewed_path: Path | None = None

    # ── Context access ────────────────────────────────────────────

    def get_or_load(self, path: Path) -> SessionContext:
        """Return cached context or load from disk."""
        if path not in self._contexts:
            ctx = SessionContext(path=path)
            load_session(path, ctx.transcript_log, ctx.chat_log)
            self._contexts[path] = ctx
        return self._contexts[path]

    def create_new(self) -> SessionContext:
        """Create a fresh session and cache its context."""
        path = create_session()
        ctx = SessionContext(path=path)
        self._contexts[path] = ctx
        return ctx

    def save(self, path: Path) -> None:
        """Save a specific session."""
        if path in self._contexts:
            self._contexts[path].save()

    def save_viewed(self) -> None:
        """Save the currently viewed session."""
        if self._viewed_path:
            self.save(self._viewed_path)

    def evict(self, path: Path) -> None:
        """Remove a context from cache (e.g. after navigating away)."""
        # Don't evict the recording session
        if path != self._recording_path:
            self._contexts.pop(path, None)

    # ── Recording session ─────────────────────────────────────────

    @property
    def recording_path(self) -> Path | None:
        return self._recording_path

    @property
    def recording_context(self) -> SessionContext | None:
        if self._recording_path:
            return self._contexts.get(self._recording_path)
        return None

    def start_recording(self, path: Path) -> None:
        """Mark a session as the active recording target."""
        self._recording_path = path

    def stop_recording(self) -> None:
        """Clear the recording target."""
        self._recording_path = None

    @property
    def is_recording(self) -> bool:
        return self._recording_path is not None

    def is_recording_session(self, path: Path) -> bool:
        return self._recording_path == path

    # ── Viewed session ────────────────────────────────────────────

    @property
    def viewed_path(self) -> Path | None:
        return self._viewed_path

    @property
    def viewed_context(self) -> SessionContext | None:
        if self._viewed_path:
            return self._contexts.get(self._viewed_path)
        return None

    def set_viewed(self, path: Path) -> None:
        """Switch the viewed session."""
        self._viewed_path = path

    def clear_viewed(self) -> None:
        """Clear viewed (navigating to session list)."""
        self._viewed_path = None

    @property
    def viewing_recording(self) -> bool:
        """True when the user is looking at the session that is recording."""
        return (
            self._recording_path is not None
            and self._viewed_path == self._recording_path
        )
