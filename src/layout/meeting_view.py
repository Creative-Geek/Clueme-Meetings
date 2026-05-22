"""Meeting view layout - creates the meeting view container."""

import flet as ft


def create_meeting_view(
    meeting_toolbar,
    recording_info_banner,
    tab_bar,
    panels,
    session_loading_overlay,
):
    """Create the meeting view container."""
    return ft.Column(
        controls=[
            meeting_toolbar,
            recording_info_banner,
            ft.Divider(height=1),
            tab_bar,
            ft.Container(
                content=ft.Stack([*panels, session_loading_overlay]),
                expand=True,
            ),
        ],
        expand=True,
        visible=False,
    )
