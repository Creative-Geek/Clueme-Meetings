"""Session create handler - creates a new session."""


class CreateHandler:
    """Handles creating a new session."""

    def __init__(self, manager, transcript_tab, chat_tab, session_title_text, naming_indicator, update_toolbar_func, show_meeting_view_func):
        self.manager = manager
        self.transcript_tab = transcript_tab
        self.chat_tab = chat_tab
        self.session_title_text = session_title_text
        self.naming_indicator = naming_indicator
        self.update_toolbar_func = update_toolbar_func
        self.show_meeting_view_func = show_meeting_view_func

    def create(self):
        """Create a fresh session and switch to meeting view."""
        # Save current viewed session first
        self.manager.save_viewed()

        ctx = self.manager.create_new()
        self.manager.set_viewed(ctx.path)
        self.transcript_tab.clear()
        self.chat_tab.clear()
        self.session_title_text.value = ""
        self.naming_indicator.visible = False
        self.update_toolbar_func()
        self.show_meeting_view_func()
