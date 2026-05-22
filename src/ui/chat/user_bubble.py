"""User message bubble component."""

import flet as ft


class UserBubble(ft.Container):
    """User message bubble with edit button."""

    def __init__(self, text: str, images: list[str] | None = None, on_edit=None):
        self.message_text = text
        self.images = images or []

        edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED,
            icon_size=14,
            tooltip="Edit",
            on_click=lambda e: on_edit() if on_edit else None,
            style=ft.ButtonStyle(padding=ft.Padding.all(4)),
        )

        content_col = ft.Column(spacing=8, tight=True)
        if text:
            content_col.controls.append(ft.Text(text, size=14, selectable=True))
        if images:
            img_row = ft.Row(wrap=True, spacing=8)
            for b64 in images:
                img_row.controls.append(
                    ft.Image(src=f"data:image/jpeg;base64,{b64}", width=200, fit=ft.BoxFit.CONTAIN, border_radius=8, gapless_playback=True)
                )
            content_col.controls.append(img_row)

        row = ft.Row(
            controls=[
                ft.Container(
                    content=content_col,
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
