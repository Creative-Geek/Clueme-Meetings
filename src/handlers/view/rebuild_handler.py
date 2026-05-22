"""View rebuild handler - rebuilds transcript and chat UI from session context."""

import time as _time

from src.ui.chat_tab import StreamChunk


class RebuildHandler:
    """Handles rebuilding transcript and chat UI from session context."""

    def __init__(self, transcript_tab, chat_tab, session_title_text, naming_indicator, get_session_name_func):
        self.transcript_tab = transcript_tab
        self.chat_tab = chat_tab
        self.session_title_text = session_title_text
        self.naming_indicator = naming_indicator
        self.get_session_name_func = get_session_name_func

    def rebuild(self, ctx):
        """Rebuild transcript and chat UI from a session context."""
        self.transcript_tab.clear()
        for entry in ctx.transcript_log.entries:
            self.transcript_tab.add_confirmed(entry.text, entry.minute)

        self.chat_tab.clear()
        for entry in ctx.chat_log.entries:
            if entry.role == "user":
                self.chat_tab.add_user_message(entry.text, entry.images)
            elif entry.role == "model":
                self.chat_tab.start_assistant_message()
                self.chat_tab.append_chunk(StreamChunk(text=entry.text))
                self.chat_tab.finish_assistant_message()

        # Update session title in toolbar
        name = self.get_session_name_func(ctx.path)
        self.session_title_text.value = name
        self.session_title_text.visible = True
        self.naming_indicator.visible = False
