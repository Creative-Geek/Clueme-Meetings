"""Session delete handler - deletes a session."""

from src.sessions import delete_session, list_sessions
from src import debug_log as _debug_log


class DeleteHandler:
    """Handles deleting a session."""

    def __init__(self, manager, session_list_view, page):
        self.manager = manager
        self.session_list_view = session_list_view
        self.page = page

    def delete(self, path):
        """Delete a session and refresh the list."""
        _debug_log.log_event("SESSION", f"delete — {path}")
        delete_session(path)
        self.manager.evict(path)
        self.session_list_view.refresh(list_sessions())
        self.page.update()
