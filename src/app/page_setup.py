"""Page setup - configures the Flet page."""

import os
import flet as ft


def setup_page(page: ft.Page):
    """Configure the Flet page with window settings and theme."""
    page.title = "Clueme Meetings"
    page.theme_mode = ft.ThemeMode.DARK
    page.dark_theme = ft.Theme(
        color_scheme_seed=ft.Colors.CYAN,
    )
    page.padding = 16
    page.window.width = 700
    page.window.height = 800

    # App icon (Windows taskbar + title bar)
    icon_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "assets", "logo_no_text_cropped.ico"
    )
    if os.path.exists(icon_path):
        page.window.icon = icon_path
