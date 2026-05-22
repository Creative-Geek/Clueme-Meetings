"""Debug logging tab."""

import flet as ft

from src import debug_log as _debug_log


def create_debug_tab(cfg: dict, on_debug_switch_change) -> tuple[ft.Column, ft.Switch, ft.Text]:
    """Create the debug logging tab."""
    debug_switch = ft.Switch(
        label="Enable debug logging",
        value=cfg.get("debug_logging", False),
        on_change=on_debug_switch_change,
    )
    debug_path_text = ft.Text(
        f"Logs: {_debug_log.get_log_dir()}" if cfg.get("debug_logging") else "",
        size=11,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
        visible=cfg.get("debug_logging", False),
    )

    panel = ft.Column(
        [
            debug_switch,
            debug_path_text,
        ],
        tight=True,
        spacing=16,
    )

    return panel, debug_switch, debug_path_text
