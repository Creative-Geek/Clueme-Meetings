"""Chat send handler - sends user messages to AI and streams responses."""

import time as _time

from src.ui.chat_tab import StreamChunk


class ChatHandler:
    """Handles sending chat messages to the AI and streaming responses."""

    def __init__(self, manager, chat_tab, transcriber, page, settings, clear_menu_btn):
        self.manager = manager
        self.chat_tab = chat_tab
        self.transcriber = transcriber
        self.page = page
        self.settings = settings
        self.clear_menu_btn = clear_menu_btn

    async def send(self, user_message: str, images: list[str] | None = None):
        """Send a message to the AI and stream the response."""
        ctx = self.manager.viewed_context
        if not ctx:
            return

        self.chat_tab.add_user_message(user_message, images)
        self.chat_tab.start_assistant_message()
        self.chat_tab.set_streaming(True)
        self.settings.button.disabled = True
        self.clear_menu_btn.disabled = True
        self.page.update()

        # Use system-time minute for ordering
        minute = int(_time.time() // 60)
        tentative = (
            self.transcriber.tentative
            if (self.transcriber and self.manager.viewing_recording)
            else ""
        )

        try:
            async for chunk in ctx.chat.send(user_message, minute, tentative, images):
                self.chat_tab.append_chunk(chunk)
                self.page.update()
        except Exception as e:
            self.chat_tab.append_chunk(StreamChunk(text=f"\n\n⚠️ Error: {e}"))
            self.page.update()

        self.chat_tab.finish_assistant_message()
        self.chat_tab.set_streaming(False)
        self.settings.button.disabled = False
        self.clear_menu_btn.disabled = False
        self.page.update()

        # Auto-save after chat exchange
        self.manager.save_viewed()
