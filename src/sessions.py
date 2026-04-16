"""Session persistence — auto-saving meeting sessions to disk."""

import json
from datetime import datetime
from pathlib import Path

from src.logs import TranscriptLog, ChatLog

SESSIONS_DIR = Path.home() / ".clueme" / "sessions"


def create_session() -> Path:
    """Create a new empty session file. Returns the path."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SESSIONS_DIR / f"{ts}.json"
    data = {
        "name": "",
        "name_source": "",
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "transcript": [],
        "chat": [],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def update_session(path: Path, transcript_log: TranscriptLog, chat_log: ChatLog) -> None:
    """Overwrite session data in place (auto-save)."""
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        existing = {}
    existing["transcript"] = transcript_log.to_dicts()
    existing["chat"] = chat_log.to_dicts()
    existing["updated"] = datetime.now().isoformat()
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def rename_session(path: Path, name: str, source: str = "") -> None:
    """Update the name field in a session file.

    Args:
        source: "auto" or "manual" — stored as name_source.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    data["name"] = name
    if source:
        data["name_source"] = source
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_sessions() -> list[dict]:
    """Return session metadata sorted newest-first.

    Each dict has: path, name, created, updated, transcript_count, chat_count.
    """
    if not SESSIONS_DIR.exists():
        return []
    sessions = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sessions.append({
                "path": p,
                "name": data.get("name", ""),
                "name_source": data.get("name_source", ""),
                "created": data.get("created", ""),
                "updated": data.get("updated", ""),
                "transcript_count": len(data.get("transcript", [])),
                "chat_count": len(data.get("chat", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


def load_session(
    path: Path, transcript_log: TranscriptLog, chat_log: ChatLog
) -> dict:
    """Load a session file into existing log objects. Returns metadata."""
    data = json.loads(path.read_text(encoding="utf-8"))
    transcript_log.clear()
    chat_log.clear()
    transcript_log.load_dicts(data.get("transcript", []))
    chat_log.load_dicts(data.get("chat", []))
    return {"name": data.get("name", ""), "created": data.get("created", "")}


def delete_session(path: Path) -> None:
    """Delete a session file."""
    path.unlink(missing_ok=True)
