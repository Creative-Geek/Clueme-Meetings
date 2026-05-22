"""Audio device settings tab."""

import flet as ft


def create_audio_tab(cfg: dict) -> tuple[ft.Column, ft.Dropdown, ft.Dropdown]:
    """Create the audio device settings tab."""
    speaker_dropdown = ft.Dropdown(
        label="Speaker device (system audio)",
        options=[ft.dropdown.Option(key="", text="Default")],
        value=cfg.get("speaker_device", ""),
        border_radius=12,
        filled=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    mic_dropdown = ft.Dropdown(
        label="Microphone",
        options=[ft.dropdown.Option(key="", text="Disabled")],
        value=cfg.get("mic_device", ""),
        border_radius=12,
        filled=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    panel = ft.Column(
        [
            speaker_dropdown,
            mic_dropdown,
            ft.Text(
                "Mic and speaker audio are mixed together — no speaker labels yet.\n"
                "Changes take effect next time you start listening.",
                size=11,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
        tight=True,
        spacing=16,
    )

    return panel, speaker_dropdown, mic_dropdown
