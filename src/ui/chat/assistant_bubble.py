"""Assistant message bubble component."""

import flet as ft

from src.ui.chat.stream_chunk import StreamChunk


def _make_md(text: str = "") -> ft.Markdown:
    """Create a Markdown component with dark mode styling."""
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

    return ft.Markdown(
        text,
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
        code_style_sheet=_code_style_sheet,
        md_style_sheet=_md_style_sheet,
    )


class AssistantBubble(ft.Container):
    """Assistant message bubble with optional thinking tile and retry button."""

    def __init__(self, on_retry=None, on_copy=None):
        self._thinking_text = ""
        self._response_text = ""
        self._on_retry = on_retry
        self._on_copy = on_copy

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

        # Copy button — shown after streaming completes
        self._copy_btn = ft.IconButton(
            icon=ft.Icons.CONTENT_COPY_OUTLINED,
            icon_size=14,
            tooltip="Copy message",
            on_click=lambda e: self._on_copy(self._response_text) if self._on_copy else None,
            visible=False,
            style=ft.ButtonStyle(padding=ft.Padding.all(4)),
        )

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
                    controls=[self._copy_btn, self._retry_btn],
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
        """Mark streaming as complete — show actions, update thinking title."""
        self._retry_btn.visible = True
        self._copy_btn.visible = True
        if self._thinking_text:
            self._thinking_tile.title = "Thought process"

    @property
    def response_text(self) -> str:
        return self._response_text

    @property
    def thinking_text(self) -> str:
        return self._thinking_text
