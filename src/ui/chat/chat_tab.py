"""Chat tab — message history with AI responses."""

import base64
import io
from PIL import Image, ImageGrab

import flet as ft

from src.ui.chat.stream_chunk import StreamChunk
from src.ui.chat.user_bubble import UserBubble
from src.ui.chat.assistant_bubble import AssistantBubble


class ChatTab(ft.Column):
    """Chat interface with message list, input bar, and summarize button."""

    def __init__(self, on_send=None, on_summarize=None):
        super().__init__(expand=True)

        self._on_send = on_send  # callback(message: str, images: list[str])
        self._on_summarize = on_summarize  # callback()
        self._on_suggest = None  # callback()
        self._on_edit = None  # callback(bubble_index: int, text: str)
        self._on_retry = None  # callback()
        self._on_stop = None  # callback()
        self._is_near_bottom: bool = True  # smart scroll state
        self._scroll_pending: bool = False
        self._attached_images: list[str] = []
        self._input_has_focus: bool = False

        # Current streaming response
        self._streaming_bubble: AssistantBubble | None = None

        # Session title label — shows which session this chat belongs to
        self._session_title = ft.Text(
            "",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
            visible=False,
        )

        self._list = ft.ListView(
            expand=True,
            spacing=4,
            padding=ft.Padding.all(16),
            on_scroll=self._on_scroll,
        )

        self._thumbnails_row = ft.Row(wrap=True, spacing=8, visible=False)
        self._file_picker = ft.FilePicker()

        self._input = ft.TextField(
            hint_text="Ask about the meeting…",
            autofocus=True,
            shift_enter=True,
            min_lines=1,
            max_lines=3,
            filled=True,
            expand=True,
            border_radius=24,
            on_submit=self._handle_send,
            on_focus=lambda e: self._set_focus(True),
            on_blur=lambda e: self._set_focus(False),
        )

        self._attach_btn = ft.IconButton(
            icon=ft.Icons.ATTACH_FILE,
            tooltip="Attach Image",
            on_click=self._on_attach_click,
        )

        self._send_btn = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            tooltip="Send",
            on_click=self._handle_send,
        )

        self._stop_btn = ft.IconButton(
            icon=ft.Icons.STOP_ROUNDED,
            tooltip="Stop generating",
            icon_color=ft.Colors.ERROR,
            on_click=self._handle_stop,
            visible=False,
        )

        self._loading_ring = ft.ProgressRing(
            width=20, height=20, stroke_width=2, visible=False
        )

        self._summarize_btn = ft.IconButton(
            icon=ft.Icons.SUMMARIZE_OUTLINED,
            tooltip="Summarize",
            on_click=self._handle_summarize,
        )

        self._suggest_btn = ft.IconButton(
            icon=ft.Icons.RECORD_VOICE_OVER_OUTLINED,
            tooltip="What should I say?",
            on_click=self._handle_suggest,
        )

        self.controls = [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CHAT_OUTLINED, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                        self._session_title,
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(left=16, top=6, right=16, bottom=0),
                visible=False,
            ),
            ft.Container(
                content=self._list,
                expand=True,
                border_radius=12,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
            ),
            ft.Column(
                controls=[
                    self._thumbnails_row,
                    ft.Row(
                        controls=[
                            self._attach_btn,
                            self._input,
                            self._loading_ring,
                            self._summarize_btn,
                            self._suggest_btn,
                            self._send_btn,
                            self._stop_btn,
                        ],
                        spacing=8,
                    ),
                ],
                spacing=8,
            ),
        ]
        # Keep a reference to the title container for toggling
        self._title_container = self.controls[0]

    def did_mount(self):
        self.page.services.append(self._file_picker)
        self.page.on_keyboard_event = self._on_keyboard  # pyrefly: ignore
        self.page.update()

    def will_unmount(self):
        self.page.services.remove(self._file_picker)
        self.page.on_keyboard_event = None  # pyrefly: ignore
        self.page.update()

    def _set_focus(self, focused: bool):
        self._input_has_focus = focused

    def _on_keyboard(self, e: ft.KeyboardEvent):
        if not self._input_has_focus:
            return
        if (e.ctrl or e.meta) and e.key == "V":
            try:
                clip = ImageGrab.grabclipboard()
            except Exception:
                clip = None
            
            if isinstance(clip, Image.Image):
                self._process_and_attach_image(clip)
            elif isinstance(clip, list):
                for path in clip:
                    try:
                        img = Image.open(path)
                        self._process_and_attach_image(img)
                    except Exception:
                        pass

    async def _on_attach_click(self, e):
        result = await self._file_picker.pick_files(
            allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE
        )
        files = getattr(result, "files", result) if result else None
        if not files:
            return
            
        for f in files:
            try:
                path = getattr(f, "path", None)
                if not path:
                    continue
                img = Image.open(path)
                self._process_and_attach_image(img)
            except Exception:
                pass

    def _process_and_attach_image(self, img: Image.Image):
        img.thumbnail((1920, 1080))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        self._attached_images.append(b64)
        self._update_thumbnails_ui()

    def _update_thumbnails_ui(self):
        self._thumbnails_row.controls.clear()
        for i, b64 in enumerate(self._attached_images):
            img_ctrl = ft.Image(src=f"data:image/jpeg;base64,{b64}", width=64, height=64, fit=ft.BoxFit.COVER, border_radius=8, gapless_playback=True)
            remove_btn = ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_size=14,
                width=24, height=24,
                style=ft.ButtonStyle(padding=ft.Padding.all(0), bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK)),
                on_click=lambda e, idx=i: self._remove_attached_image(idx)
            )
            stack = ft.Stack(
                controls=[
                    img_ctrl,
                    ft.Container(content=remove_btn, top=2, right=2)
                ],
                width=64, height=64
            )
            self._thumbnails_row.controls.append(stack)
        
        self._thumbnails_row.visible = len(self._attached_images) > 0
        self.update()

    def _remove_attached_image(self, idx: int):
        if 0 <= idx < len(self._attached_images):
            self._attached_images.pop(idx)
            self._update_thumbnails_ui()

    # ── Input handlers ──────────────────────────────────────────

    def _handle_send(self, e):
        text = self._input.value.strip()
        if (text or self._attached_images) and self._on_send and not self._stop_btn.visible:
            images_to_send = list(self._attached_images)
            self._input.value = ""
            self._attached_images.clear()
            self._update_thumbnails_ui()
            self._input.update()
            self._on_send(text, images_to_send)

    def _handle_summarize(self, e):
        if self._on_summarize and not self._stop_btn.visible:
            self._on_summarize()

    def _handle_suggest(self, e):
        if self._on_suggest and not self._stop_btn.visible:
            self._on_suggest()

    def _handle_stop(self, e):
        if self._on_stop:
            self._on_stop()

    # ── Smart scroll ────────────────────────────────────────────

    def _on_scroll(self, e: ft.OnScrollEvent):
        """Track whether the user is near the bottom of the list."""
        event_str = getattr(e.event_type, "value", e.event_type)
        if event_str in ("start", "user", "update"):
            self._is_near_bottom = (e.max_scroll_extent - e.pixels) < 80

    def _auto_scroll_if_needed(self):
        """Scroll to bottom only if the user was already near the bottom."""
        if self._is_near_bottom and self.page and not self._scroll_pending:
            self._scroll_pending = True
            async def _scroll():
                try:
                    await self._list.scroll_to(offset=-1, duration=150)
                except Exception:
                    pass
                finally:
                    self._scroll_pending = False
            self.page.run_task(_scroll)  # pyrefly: ignore

    def scroll_to_bottom(self):
        """Force scroll to the bottom (e.g. on tab switch)."""
        self._is_near_bottom = True
        if self.page:
            async def _scroll():
                await self._list.scroll_to(offset=-1, duration=150)
            self.page.run_task(_scroll)  # pyrefly: ignore

    # ── Streaming state ─────────────────────────────────────────

    def set_streaming(self, streaming: bool):
        """Toggle input controls for streaming state."""
        self._input.disabled = streaming
        self._send_btn.visible = not streaming
        self._summarize_btn.disabled = streaming
        self._suggest_btn.disabled = streaming
        self._stop_btn.visible = streaming
        self._loading_ring.visible = streaming

    # ── Message management ──────────────────────────────────────

    def add_user_message(self, text: str, images: list[str] | None = None):
        """Add a user message bubble with edit button."""
        idx = len(self._list.controls)
        bubble = UserBubble(
            text,
            images=images,
            on_edit=lambda i=idx: self._trigger_edit(i),
        )
        self._list.controls.append(bubble)
        self._auto_scroll_if_needed()

    def _trigger_edit(self, bubble_index: int):
        """User clicked edit on a message — populate input and truncate."""
        if self._stop_btn.visible:
            return  # don't edit while streaming
        bubble = self._list.controls[bubble_index]
        if isinstance(bubble, UserBubble):
            text = bubble.message_text

            def confirm(e):
                dlg.open = False
                self.page.update()
                # Remove this bubble and everything after it
                del self._list.controls[bubble_index:]
                self._input.value = text
                self._attached_images = list(bubble.images)
                self._update_thumbnails_ui()
                
                async def _focus():
                    try:
                        await self._input.focus()
                    except Exception:
                        pass
                
                self.page.run_task(_focus)  # pyrefly: ignore
                
                if self._on_edit:
                    self._on_edit(bubble_index)
                self.update()

            def cancel(e):
                dlg.open = False
                self.page.update()

            dlg = ft.AlertDialog(
                title=ft.Text("Edit Message"),
                content=ft.Text("Editing this message will clear all subsequent messages. Continue?"),
                actions=[
                    ft.TextButton("Cancel", on_click=cancel),
                    ft.TextButton("Edit", on_click=confirm, style=ft.ButtonStyle(color=ft.Colors.PRIMARY))
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()

    def start_assistant_message(self):
        """Start a new streaming assistant message."""
        bubble = AssistantBubble(
            on_retry=lambda: self._trigger_retry(),
            on_copy=lambda text: self._trigger_copy(text),
        )
        self._streaming_bubble = bubble
        self._list.controls.append(bubble)
        self._auto_scroll_if_needed()

    def append_chunk(self, chunk: StreamChunk):
        """Append a thinking or response chunk to the current streaming bubble."""
        if not self._streaming_bubble:
            return
        if chunk.is_thought:
            self._streaming_bubble.append_thinking(chunk.text)
        else:
            self._streaming_bubble.append_response(chunk.text)
        self._auto_scroll_if_needed()

    def finish_assistant_message(self):
        """Mark the current assistant message as complete."""
        if self._streaming_bubble:
            self._streaming_bubble.finish()
        self._streaming_bubble = None

    def _trigger_retry(self):
        """User clicked retry on an assistant message."""
        if self._stop_btn.visible:
            return  # don't retry while streaming
        if not self._list.controls:
            return
        # Remove the last assistant bubble
        last = self._list.controls[-1]
        if isinstance(last, AssistantBubble):
            self._list.controls.pop()
            if self._on_retry:
                self._on_retry()

    async def _handle_copy_task(self, text: str):
        clipboard = ft.Clipboard()
        self.page.services.append(clipboard)
        await clipboard.set(text)
        snack = ft.SnackBar(content=ft.Text("Message copied to clipboard"))
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    def _trigger_copy(self, text: str):
        """User clicked copy on an assistant message."""
        if self.page:
                self.page.run_task(self._handle_copy_task, text)  # pyrefly: ignore

    def truncate_from_bubble(self, bubble_index: int):
        """Remove all bubbles from bubble_index onward (used by edit)."""
        del self._list.controls[bubble_index:]

    def set_session_title(self, title: str) -> None:
        """Show or hide the session title label above the chat."""
        if title:
            self._session_title.value = f"Chat: {title}"
            self._session_title.visible = True
            self._title_container.visible = True
        else:
            self._session_title.visible = False
            self._title_container.visible = False

    def clear(self):
        """Clear all chat messages."""
        self._list.controls.clear()
        self._streaming_bubble = None
        self._is_near_bottom = True
