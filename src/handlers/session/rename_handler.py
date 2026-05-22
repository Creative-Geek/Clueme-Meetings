"""Session rename handler - renames a session."""

from src.sessions import rename_session, list_sessions
from src import debug_log as _debug_log


class RenameHandler:
    """Handles renaming a session."""

    def __init__(self, manager, session_list_view, session_title_text, page):
        self.manager = manager
        self.session_list_view = session_list_view
        self.session_title_text = session_title_text
        self.page = page

    def confirm_rename(self, path, new_name):
        """Commit a rename and refresh the UI."""
        _debug_log.log_event("RENAME", f"manual rename: {new_name!r} (source=manual)")
        rename_session(path, new_name, source="manual")
        if self.manager.viewed_path == path:
            self.session_title_text.value = new_name
        self.session_list_view.refresh(list_sessions())
        self.page.update()

    async def ai_suggest_name(self, path):
        """Generate an AI title from a session's transcript."""
        from src.agent import generate_session_title

        ctx = self.manager.get_or_load(path)
        transcript_text = " ".join(entry.text for entry in ctx.transcript_log.entries)
        _debug_log.log_event(
            "RENAME", f"AI suggest — transcript_len={len(transcript_text)}"
        )
        title = await generate_session_title(transcript_text)
        _debug_log.log_event("RENAME", f"AI returned: {title!r}")
        return title
