"""Session enter handler - loads and enters a session."""

import asyncio

from src import debug_log as _debug_log


class EnterHandler:
    """Handles entering a session."""

    def __init__(
        self,
        manager,
        session_loading_overlay,
        show_meeting_view_func,
        rebuild_ui_func,
        update_toolbar_func,
        page,
    ):
        self.manager = manager
        self.session_loading_overlay = session_loading_overlay
        self.show_meeting_view_func = show_meeting_view_func
        self.rebuild_ui_func = rebuild_ui_func
        self.update_toolbar_func = update_toolbar_func
        self.page = page

    def enter(self, session_path):
        """Load a session and switch to meeting view."""
        _debug_log.log_event("SESSION", f"enter — {session_path}")
        # Save current viewed session first
        self.manager.save_viewed()

        # Show loading overlay immediately, then defer heavy work
        self.session_loading_overlay.visible = True
        self.show_meeting_view_func()
        self.page.update()

        async def _do_load():
            # Yield to event loop so the spinner renders
            await asyncio.sleep(0.05)

            # Heavy work: load + rebuild UI
            ctx = self.manager.get_or_load(session_path)
            self.manager.set_viewed(session_path)
            self.rebuild_ui_func(ctx)
            self.update_toolbar_func()

            self.session_loading_overlay.visible = False
            self.page.update()

        self.page.run_task(_do_load)
