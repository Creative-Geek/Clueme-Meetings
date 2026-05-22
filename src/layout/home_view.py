"""Home view layout - creates the session list view container."""

import os
import flet as ft


def create_home_view(session_toolbar, session_list_view, logo_path):
    """Create the home view container."""
    return ft.Column(
        controls=[
            session_toolbar,
            ft.Container(
                content=ft.Image(
                    src=logo_path, width=120, height=120, color="#83d3e3"
                )
                if os.path.exists(logo_path)
                else None,
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding(top=-30, bottom=0, left=0, right=0),
            ),
            ft.Divider(height=1),
            session_list_view,
        ],
        expand=True,
        visible=True,
    )
