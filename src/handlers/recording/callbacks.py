"""Recording callbacks - transcriber event handlers."""

import flet as ft


class RecordingCallbacks:
    """Callbacks for transcriber events."""

    def __init__(self, manager, transcript_tab, page):
        self.manager = manager
        self.transcript_tab = transcript_tab
        self.page = page

    def on_confirmed(self, text: str, minute: int):
        """Transcriber confirmed text — write to RECORDING session."""
        rec = self.manager.recording_context
        if not rec:
            return
        rec.transcript_log.append(text=text, minute=minute)

        # Incremental save — persist immediately so a crash can't lose data
        if self.manager.recording_path:
            self.manager.save(self.manager.recording_path)

        # Only update the transcript UI if viewing the recording session
        if self.manager.viewing_recording:

            async def _update():
                self.transcript_tab.add_confirmed(text, minute)
                self.page.update()

            self.page.run_task(_update)

    def on_tentative(self, text: str):
        """Transcriber tentative text — update UI if viewing recording."""
        # Only show tentative text if viewing the recording session
        if self.manager.viewing_recording:

            async def _update():
                self.transcript_tab.set_tentative(text)
                self.page.update()

            self.page.run_task(_update)

    def on_ready(self, loading_ring, status_text):
        """Transcriber model loaded and ready."""
        async def _update():
            loading_ring.visible = False
            status_text.value = "🎧 Listening…"
            status_text.color = ft.Colors.PRIMARY
            self.page.update()

        self.page.run_task(_update)

    def on_error(self, message: str, start_btn, stop_btn, loading_ring, status_text):
        """Transcriber error occurred."""
        async def _update():
            loading_ring.visible = False
            start_btn.visible = True
            stop_btn.visible = False
            start_btn.disabled = False
            status_text.value = f"⚠️ {message}"
            status_text.color = ft.Colors.ERROR
            self.manager.stop_recording()
            self.page.update()

        self.page.run_task(_update)
