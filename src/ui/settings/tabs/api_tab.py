"""API keys configuration tab."""

import flet as ft


def create_api_tab(cfg: dict) -> tuple[ft.Column, ft.TextField, ft.TextField, ft.TextField]:
    """Create the API keys configuration tab.

    Returns (panel, google_key_field, assemblyai_key_field, tavily_key_field).
    """
    google_key_field = ft.TextField(
        label="Google API Key",
        value=cfg.get("google_api_key", ""),
        password=True,
        can_reveal_password=True,
        border_radius=12,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    assemblyai_key_field = ft.TextField(
        label="AssemblyAI API Key (optional)",
        value=cfg.get("assemblyai_api_key", ""),
        password=True,
        can_reveal_password=True,
        border_radius=12,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    tavily_key_field = ft.TextField(
        label="Tavily API Key (optional — enables web search for Gemini 3.x)",
        value=cfg.get("tavily_api_key", ""),
        password=True,
        can_reveal_password=True,
        border_radius=12,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    panel = ft.Column(
        [
            google_key_field,
            assemblyai_key_field,
            tavily_key_field,
            ft.Text(
                "Settings are stored locally in ~/.clueme/config.json",
                size=11,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ],
        tight=True,
        spacing=16,
    )

    return panel, google_key_field, assemblyai_key_field, tavily_key_field
