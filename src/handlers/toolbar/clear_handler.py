"""Toolbar clear handler - clears chat/transcript/all data."""


class ClearHandler:
    """Handles clearing chat/transcript data."""

    def __init__(self, manager, chat_tab, transcript_tab):
        self.manager = manager
        self.chat_tab = chat_tab
        self.transcript_tab = transcript_tab

    def handle_clear(self, action: str):
        """Handle clear menu action."""
        ctx = self.manager.viewed_context
        if not ctx:
            return
        if action == "chat":
            ctx.chat_log.clear()
            self.chat_tab.clear()
        elif action == "transcript":
            ctx.transcript_log.clear()
            self.transcript_tab.clear()
        elif action == "all":
            ctx.chat_log.clear()
            self.chat_tab.clear()
            ctx.transcript_log.clear()
            self.transcript_tab.clear()
