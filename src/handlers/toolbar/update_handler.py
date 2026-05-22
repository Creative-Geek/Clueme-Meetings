"""Toolbar update handler - updates toolbar state based on recording/viewed session."""

import flet as ft


class UpdateToolbarHandler:
    """Handles updating toolbar state based on recording and viewed session."""

    def __init__(
        self,
        manager,
        start_btn,
        stop_btn,
        recording_info_banner,
        status_text,
        get_session_name_func,
    ):
        self.manager = manager
        self.start_btn = start_btn
        self.stop_btn = stop_btn
        self.recording_info_banner = recording_info_banner
        self.status_text = status_text
        self.get_session_name_func = get_session_name_func

    def update(self):
        """Update Start/Stop buttons and banners based on recording state vs viewed session."""
        if not self.manager.is_recording:
            # No recording active — show Start, hide banner
            self.start_btn.visible = True
            self.start_btn.disabled = False
            self.stop_btn.visible = False
            self.recording_info_banner.visible = False
            self.status_text.value = "Ready"
            self.status_text.color = "#9E9E9E"  # ON_SURFACE_VARIANT
        elif self.manager.viewing_recording:
            # Viewing the recording session — show Stop
            self.start_btn.visible = False
            self.stop_btn.visible = True
            self.recording_info_banner.visible = False
            self.status_text.value = "🎧 Listening…"
            self.status_text.color = ft.Colors.PRIMARY
        else:
            # Recording, but viewing a different session
            self.start_btn.visible = True
            self.start_btn.disabled = True
            self.start_btn.tooltip = "Stop the active recording first"
            self.stop_btn.visible = False
            self.recording_info_banner.visible = True
            rec_name = self.get_session_name_func(self.manager.recording_path)
            self.recording_info_banner.content.controls[1].value = f"Recording: {rec_name}"
            self.status_text.value = "Browsing saved session"
            self.status_text.color = "#9E9E9E"  # ON_SURFACE_VARIANT
