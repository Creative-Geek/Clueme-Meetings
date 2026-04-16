"""Chat tab — message history with AI responses."""

from dataclasses import dataclass

import flet as ft

# Shared Markdown style sheets for dark mode
_md_style_sheet = ft.MarkdownStyleSheet(
    # Inline code: light text on dark bg, monospace
    code_text_style=ft.TextStyle(
        font_family="Consolas",
        size=13,
        color="#E0E0E0",
        bgcolor="#2A2A3D",
    ),
    # Block quotes: muted text, dark bg with accent left border
    blockquote_text_style=ft.TextStyle(
        color="#B0B0C0",
        italic=True,
    ),
    blockquote_decoration=ft.BoxDecoration(
        bgcolor="#1E1E2E",
        border=ft.Border.only(left=ft.BorderSide(3, "#7C4DFF")),
        border_radius=4,
    ),
    blockquote_padding=ft.Padding(left=12, top=8, right=12, bottom=8),
)

_code_style_sheet = ft.MarkdownStyleSheet(
    # Fenced code block container
    codeblock_decoration=ft.BoxDecoration(
        bgcolor="#1E1E2E",
    ),
    codeblock_padding=ft.Padding(left=12, top=12, right=12, bottom=12),
)


@dataclass
class StreamChunk:
    """A chunk yielded during streaming — either thinking or response text."""

    text: str
    is_thought: bool = False


def _make_md(text: str = "") -> ft.Markdown:
    return ft.Markdown(
        text,
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
        code_style_sheet=_code_style_sheet,
        md_style_sheet=_md_style_sheet,
    )


class UserBubble(ft.Container):
    """User message bubble with edit button."""

    def __init__(self, text: str, on_edit=None):
        self.message_text = text

        edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED,
            icon_size=14,
            tooltip="Edit",
            on_click=lambda e: on_edit() if on_edit else None,
            style=ft.ButtonStyle(padding=ft.Padding.all(4)),
        )

        row = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text(text, size=14, selectable=True),
                    expand=True,
                ),
                edit_btn,
            ],
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        super().__init__(
            content=row,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            alignment=ft.Alignment.CENTER_LEFT,
            margin=ft.Margin(left=60, right=8, top=4, bottom=4),
            padding=ft.Padding.all(12),
            border_radius=16,
        )


class AssistantBubble(ft.Container):
    """Assistant message bubble with optional thinking tile and retry button."""

    def __init__(self, on_retry=None):
        self._thinking_text = ""
        self._response_text = ""
        self._on_retry = on_retry

        # Thinking: expandable tile, hidden until we get thinking chunks
        self._thinking_md = ft.Text(
            "", size=12, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True
        )
        self._thinking_tile = ft.ExpansionTile(
            title="Thinking…",
            leading=ft.Icons.PSYCHOLOGY_OUTLINED,
            controls=[
                ft.Container(
                    content=self._thinking_md,
                    padding=ft.Padding(left=8, top=0, right=8, bottom=8),
                )
            ],
            dense=True,
            collapsed_text_color=ft.Colors.ON_SURFACE_VARIANT,
            text_color=ft.Colors.ON_SURFACE_VARIANT,
            icon_color=ft.Colors.ON_SURFACE_VARIANT,
            tile_padding=ft.Padding(left=0, top=0, right=0, bottom=0),
            min_tile_height=32,
            visible=False,
        )

        # Response markdown
        self._response_md = _make_md()

        # Retry button — shown after streaming completes
        self._retry_btn = ft.IconButton(
            icon=ft.Icons.REFRESH_OUTLINED,
            icon_size=14,
            tooltip="Retry",
            on_click=lambda e: self._on_retry() if self._on_retry else None,
            visible=False,
            style=ft.ButtonStyle(padding=ft.Padding.all(4)),
        )

        self._column = ft.Column(
            controls=[
                self._thinking_tile,
                self._response_md,
                ft.Row(
                    controls=[self._retry_btn],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=4,
            tight=True,
        )

        super().__init__(
            content=self._column,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            alignment=ft.Alignment.CENTER_LEFT,
            margin=ft.Margin(left=8, right=60, top=4, bottom=4),
            padding=ft.Padding.all(12),
            border_radius=16,
        )

    def append_thinking(self, text: str):
        self._thinking_text += text
        self._thinking_tile.visible = True
        self._thinking_md.value = self._thinking_text

    def append_response(self, text: str):
        self._response_text += text
        self._response_md.value = self._response_text

    def finish(self):
        """Mark streaming as complete — show retry, update thinking title."""
        self._retry_btn.visible = True
        if self._thinking_text:
            self._thinking_tile.title = "Thought process"

    @property
    def response_text(self) -> str:
        return self._response_text

    @property
    def thinking_text(self) -> str:
        return self._thinking_text


class ChatTab(ft.Column):
    """Chat interface with message list, input bar, and summarize button."""

    def __init__(self, on_send=None, on_summarize=None):
        super().__init__(expand=True)

        self._on_send = on_send  # callback(message: str)
        self._on_summarize = on_summarize  # callback()
        self._on_edit = None  # callback(bubble_index: int, text: str)
        self._on_retry = None  # callback()
        self._on_stop = None  # callback()
        self._is_near_bottom: bool = True  # smart scroll state
        self._scroll_pending: bool = False

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

        self._summarize_btn = ft.TextButton(
            "Summarize",
            icon=ft.Icons.SUMMARIZE_OUTLINED,
            on_click=self._handle_summarize,
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
            ft.Row(
                controls=[
                    self._input,
                    self._loading_ring,
                    self._summarize_btn,
                    self._send_btn,
                    self._stop_btn,
                ],
                spacing=8,
            ),
        ]
        # Keep a reference to the title container for toggling
        self._title_container = self.controls[0]

    # ── Input handlers ──────────────────────────────────────────

    def _handle_send(self, e):
        text = self._input.value.strip()
        if text and self._on_send and not self._stop_btn.visible:
            self._input.value = ""
            self._input.update()
            self._on_send(text)

    def _handle_summarize(self, e):
        if self._on_summarize and not self._stop_btn.visible:
            self._on_summarize()

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
            self.page.run_task(_scroll)

    def scroll_to_bottom(self):
        """Force scroll to the bottom (e.g. on tab switch)."""
        self._is_near_bottom = True
        if self.page:
            async def _scroll():
                await self._list.scroll_to(offset=-1, duration=150)
            self.page.run_task(_scroll)

    # ── Streaming state ─────────────────────────────────────────

    def set_streaming(self, streaming: bool):
        """Toggle input controls for streaming state."""
        self._input.disabled = streaming
        self._send_btn.visible = not streaming
        self._summarize_btn.disabled = streaming
        self._stop_btn.visible = streaming
        self._loading_ring.visible = streaming

    # ── Message management ──────────────────────────────────────

    def add_user_message(self, text: str):
        """Add a user message bubble with edit button."""
        idx = len(self._list.controls)
        bubble = UserBubble(
            text,
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
                
                async def _focus():
                    try:
                        await self._input.focus()
                    except Exception:
                        pass
                
                self.page.run_task(_focus)
                
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
