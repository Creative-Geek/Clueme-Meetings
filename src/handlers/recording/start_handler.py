"""Recording start handler - starts audio recording and transcription."""

from src.config import load as load_config
from src.transcriber import LiveTranscriber


class StartHandler:
    """Handles starting audio recording and transcription."""

    def __init__(
        self,
        manager,
        transcriber_var,
        start_btn,
        stop_btn,
        loading_ring,
        recording_info_banner,
        status_text,
        page,
        on_confirmed,
        on_tentative,
        on_ready,
        on_error,
    ):
        self.manager = manager
        self.transcriber_var = transcriber_var  # Reference to mutable variable
        self.start_btn = start_btn
        self.stop_btn = stop_btn
        self.loading_ring = loading_ring
        self.recording_info_banner = recording_info_banner
        self.status_text = status_text
        self.page = page
        self.on_confirmed = on_confirmed
        self.on_tentative = on_tentative
        self.on_ready = on_ready
        self.on_error = on_error

    def start(self):
        """Start recording and transcription."""
        if self.manager.is_recording:
            return  # already recording another session

        # Ensure previous transcriber is fully cleaned up
        if self.transcriber_var[0]:
            self.transcriber_var[0].stop(wait=True)
            self.transcriber_var[0] = None

        self.start_btn.visible = False
        self.stop_btn.visible = True
        self.loading_ring.visible = True
        self.recording_info_banner.visible = False
        self.status_text.value = "Loading model…"
        self.status_text.color = "#9E9E9E"  # ON_SURFACE_VARIANT
        self.page.update()

        # Mark this session as the recording target
        if self.manager.viewed_path:
            self.manager.start_recording(self.manager.viewed_path)

        c = load_config()
        transcriber = LiveTranscriber(
            model_size=c.get("whisper_model", "tiny"),
            speaker_device_name=c.get("speaker_device", ""),
            mic_device_name=c.get("mic_device", ""),
            on_confirmed=self.on_confirmed,
            on_tentative=self.on_tentative,
            on_ready=self.on_ready,
            on_error=self.on_error,
        )
        transcriber.start()
        self.transcriber_var[0] = transcriber
