"""Session back handler - navigates back to session list."""


class BackHandler:
    """Handles navigating back to session list."""

    def __init__(self, manager, session_list_view, show_session_list_func, get_session_name_func):
        self.manager = manager
        self.session_list_view = session_list_view
        self.show_session_list_func = show_session_list_func
        self.get_session_name_func = get_session_name_func

    def back(self):
        """Navigate back to session list. Keep transcriber alive if recording."""
        self.manager.save_viewed()

        if self.manager.is_recording:
            rec_name = self.get_session_name_func(self.manager.recording_path)
            self.session_list_view.set_recording(
                True,
                session_name=rec_name,
                recording_path=self.manager.recording_path,
            )
        else:
            self.session_list_view.set_recording(False)

        self.manager.clear_viewed()
        self.show_session_list_func()
