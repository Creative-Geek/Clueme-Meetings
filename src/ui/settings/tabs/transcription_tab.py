"""Transcription method and device settings tab."""

import flet as ft


def create_transcription_tab(cfg: dict, on_method_change) -> tuple[ft.Column, ft.Dropdown, ft.Dropdown, ft.Column, ft.Text]:
    """Create the transcription settings tab."""
    transcription_method_dropdown = ft.Dropdown(
        label="Transcription method",
        options=[
            ft.dropdown.Option(key="local_whisper", text="Local Whisper"),
            ft.dropdown.Option(key="assemblyai", text="AssemblyAI"),
        ],
        value=cfg.get("transcription_method", "local_whisper"),
        border_radius=12,
        filled=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    transcription_method_dropdown.on_select = on_method_change

    whisper_model_dropdown = ft.Dropdown(
        label="Whisper model size",
        options=[
            ft.dropdown.Option(key="tiny", text="Tiny — fastest, lower accuracy"),
            ft.dropdown.Option(key="base", text="Base — fast, decent accuracy"),
            ft.dropdown.Option(key="small", text="Small — balanced (needs GPU)"),
            ft.dropdown.Option(key="turbo", text="Turbo — best (needs good GPU)"),
        ],
        value=cfg.get("whisper_model", "tiny"),
        border_radius=12,
        filled=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    whisper_options_container = ft.Column(
        [
            whisper_model_dropdown,
            ft.Text(
                "Tiny/Base work on CPU. Small/Turbo need a dedicated GPU.",
                size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
            ),
        ],
        tight=True,
        spacing=8,
        visible=cfg.get("transcription_method", "local_whisper") == "local_whisper",
    )

    assemblyai_hint = ft.Text(
        "Requires an AssemblyAI API key (set in API Keys tab).\n"
        "$50 free credit — up to ~333 hours of transcription.",
        size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
        visible=cfg.get("transcription_method", "local_whisper") == "assemblyai",
    )

    panel = ft.Column(
        [
            transcription_method_dropdown,
            whisper_options_container,
            assemblyai_hint,
            ft.Text(
                "Changes take effect next time you start listening.",
                size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
            ),
        ],
        tight=True,
        spacing=16,
    )

    return panel, transcription_method_dropdown, whisper_model_dropdown, whisper_options_container, assemblyai_hint
