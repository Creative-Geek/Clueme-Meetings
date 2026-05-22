"""Toolbar layout - creates the meeting view toolbar."""

import flet as ft


def create_meeting_toolbar(
    back_btn,
    start_btn,
    stop_btn,
    loading_ring,
    session_title_text,
    naming_indicator,
    status_text,
    clear_menu_btn,
    settings_button,
):
    """Create the meeting view toolbar."""
    return ft.Row(
        controls=[
            back_btn,
            start_btn,
            stop_btn,
            loading_ring,
            session_title_text,
            naming_indicator,
            ft.Container(expand=True),
            status_text,
            clear_menu_btn,
            settings_button,
        ],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def create_session_toolbar(settings_button):
    """Create the session list toolbar."""
    return ft.Row(
        controls=[
            ft.Container(expand=True),
            settings_button,
        ],
        alignment=ft.MainAxisAlignment.END,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
