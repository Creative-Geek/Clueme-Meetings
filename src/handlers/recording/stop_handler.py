"""Recording stop handler - stops audio recording and transcription."""

import asyncio

from src.agent import generate_session_title
from src.config import load as load_config
from src import debug_log as _debug_log


class StopHandler:
    """Handles stopping audio recording and transcription."""

    def __init__(
        self,
        manager,
        transcriber_var,
        start_btn,
        stop_btn,
        loading_ring,
        recording_info_banner,
        status_text,
        session_list_view,
        page,
        session_title_text,
        naming_indicator,
        auto_name_session_func,
    ):
        self.manager = manager
        self.transcriber_var = transcriber_var  # Reference to mutable variable
        self.start_btn = start_btn
        self.stop_btn = stop_btn
        self.loading_ring = loading_ring
        self.recording_info_banner = recording_info_banner
        self.status_text = status_text
        self.session_list_view = session_list_view
        self.page = page
        self.session_title_text = session_title_text
        self.naming_indicator = naming_indicator
        self.auto_name_session_func = auto_name_session_func

    async def stop(self):
        """Stop recording and transcription."""
        recording_path = self.manager.recording_path

        # Disable button during wait
        self.stop_btn.disabled = True
        self.status_text.value = "Finalizing transcript…"
        self.status_text.color = "#9E9E9E"  # ON_SURFACE_VARIANT
        self.page.update()

        if self.transcriber_var[0]:
            # Wait for backend threads to finish promotion
            await asyncio.to_thread(self.transcriber_var[0].stop, wait=True)
            self.transcriber_var[0] = None

        self.manager.stop_recording()
        self.start_btn.visible = True
        self.stop_btn.visible = False
        self.stop_btn.disabled = False
        self.start_btn.disabled = False
        self.loading_ring.visible = False
        self.recording_info_banner.visible = False
        self.status_text.value = "Stopped"
        self.status_text.color = "#9E9E9E"  # ON_SURFACE_VARIANT
        self.session_list_view.set_recording(False)
        self.page.update()

        # Auto-save the recording session
        if recording_path:
            self.manager.save(recording_path)
            await self.auto_name_session_func(recording_path)
