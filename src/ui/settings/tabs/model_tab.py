"""Model settings tab."""

import flet as ft

from src.agent import MODELS


def create_model_tab(cfg: dict, on_model_change) -> tuple[ft.Column, ft.Dropdown, ft.Dropdown, ft.Dropdown]:
    """Create the model settings tab."""
    model_options = [
        ft.dropdown.Option(key=k, text=v["display"]) for k, v in MODELS.items()
    ]
    model_dropdown = ft.Dropdown(
        label="Model",
        options=model_options,
        value=cfg.get("model", "gemma-4-31b-it"),
        border_radius=12,
        filled=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    thinking_dropdown = ft.Dropdown(
        label="Thinking effort",
        options=_thinking_options_for(cfg.get("model", "gemma-4-31b-it")),
        value=cfg.get("thinking_level", "HIGH"),
        border_radius=12,
        filled=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    model_dropdown.on_select = on_model_change

    auto_name_dropdown = ft.Dropdown(
        label="Auto-name sessions",
        options=[
            ft.dropdown.Option(key="every_stop", text="Every stop"),
            ft.dropdown.Option(key="first_stop", text="First stop only"),
            ft.dropdown.Option(key="never", text="Never"),
        ],
        value=cfg.get("auto_name", "first_stop"),
        border_radius=12,
        filled=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    panel = ft.Column(
        [
            model_dropdown,
            thinking_dropdown,
            ft.Divider(height=1),
            auto_name_dropdown,
            ft.Text(
                "Controls when AI generates a session name after recording stops.",
                size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
            ),
        ],
        tight=True,
        spacing=16,
    )

    return panel, model_dropdown, thinking_dropdown, auto_name_dropdown


def _thinking_options_for(model_key: str) -> list[ft.dropdown.Option]:
    """Get thinking level options for a given model."""
    levels = MODELS.get(model_key, {}).get("levels", ["HIGH"])
    return [ft.dropdown.Option(key=lv, text=lv.capitalize()) for lv in levels]
