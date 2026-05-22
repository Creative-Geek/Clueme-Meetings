"""View switch handler - switches between transcript and chat tabs."""

import flet as ft


class SwitchHandler:
    """Handles switching between transcript and chat tabs."""

    def __init__(self, transcript_tab, chat_tab, panels):
        self.transcript_tab = transcript_tab
        self.chat_tab = chat_tab
        self.panels = panels

    def switch(self, e):
        """Handle tab change event."""
        idx = int(e.data) if isinstance(e.data, str) else e.control.selected_index
        for i, p in enumerate(self.panels):
            p.visible = i == idx
        # Scroll the newly-visible tab to bottom
        if idx == 0:
            self.transcript_tab.scroll_to_bottom()
        elif idx == 1:
            self.chat_tab.scroll_to_bottom()
