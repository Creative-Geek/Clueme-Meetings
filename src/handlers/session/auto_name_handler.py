"""Session auto-name handler - generates AI titles for sessions."""

from src.config import load as load_config
from src.agent import generate_session_title
from src.sessions import list_sessions, rename_session
from src import debug_log as _debug_log


class AutoNameHandler:
    """Handles auto-naming sessions with AI-generated titles."""

    def __init__(self, manager, session_title_text, naming_indicator, session_list_view, page):
        self.manager = manager
        self.session_title_text = session_title_text
        self.naming_indicator = naming_indicator
        self.session_list_view = session_list_view
        self.page = page

    async def auto_name_session(self, session_path):
        """Generate an AI title based on the auto_name config setting."""
        if not session_path:
            return

        c = load_config()
        auto_name = c.get("auto_name", "first_stop")

        if auto_name == "never":
            _debug_log.log_event("AUTO_NAME", "skipped — auto_name=never")
            return

        # Find session metadata
        session_meta = None
        for s in list_sessions():
            if s["path"] == session_path:
                session_meta = s
                break
        if not session_meta:
            _debug_log.log_event("AUTO_NAME", "skipped — session not found in list")
            return

        # Never overwrite a manually-set name
        if session_meta.get("name_source") == "manual":
            _debug_log.log_event(
                "AUTO_NAME",
                f"skipped — manual name anchored: {session_meta.get('name')!r}",
            )
            return

        # "first_stop": skip if any name already exists
        if auto_name == "first_stop" and session_meta.get("name"):
            _debug_log.log_event(
                "AUTO_NAME",
                f"skipped — first_stop and already named: {session_meta.get('name')!r}",
            )
            return

        # Generate from transcript
        ctx = self.manager.get_or_load(session_path)
        transcript_text = " ".join(e.text for e in ctx.transcript_log.entries)
        if not transcript_text.strip():
            _debug_log.log_event("AUTO_NAME", "skipped — transcript is empty")
            return
        _debug_log.log_event(
            "AUTO_NAME",
            f"calling AI — mode={auto_name} transcript_len={len(transcript_text)}",
        )
        if self.manager.viewed_path == session_path:
            self.session_title_text.visible = False
            self.naming_indicator.visible = True
            self.page.update()
        try:
            title = await generate_session_title(transcript_text)
            _debug_log.log_event("AUTO_NAME", f"AI returned: {title!r}")
            rename_session(session_path, title, source="auto")
            if self.manager.viewed_path == session_path:
                self.session_title_text.value = title
                self.session_title_text.visible = True
                self.naming_indicator.visible = False
            self.session_list_view.refresh(list_sessions())
            self.page.update()
        except Exception as ex:
            _debug_log.log_event("AUTO_NAME", f"ERROR: {ex}")
            if self.manager.viewed_path == session_path:
                self.session_title_text.visible = True
                self.naming_indicator.visible = False
                self.page.update()
