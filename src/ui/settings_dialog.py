"""Settings dialog — API keys, model, transcription, audio, debug."""

import flet as ft

from src import debug_log as _debug_log
from src.agent import reconfigure_client, MODELS, set_model_config
from src.config import load as load_config, save as save_config, apply_env
from src.transcriber import list_devices


class SettingsDialog:
    """Tabbed settings dialog: API Keys · Model · Transcription · Audio · Debug."""

    def __init__(self, page: ft.Page):
        self._page = page
        cfg = load_config()

        # ── API Keys tab ──────────────────────────────────────────────
        self._google_key_field = ft.TextField(
            label="Google API Key",
            value=cfg.get("google_api_key", ""),
            password=True,
            can_reveal_password=True,
            border_radius=12,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )
        self._assemblyai_key_field = ft.TextField(
            label="AssemblyAI API Key (optional)",
            value=cfg.get("assemblyai_api_key", ""),
            password=True,
            can_reveal_password=True,
            border_radius=12,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )

        # ── Model tab ─────────────────────────────────────────────────
        model_options = [
            ft.dropdown.Option(key=k, text=v["display"]) for k, v in MODELS.items()
        ]
        self._model_dropdown = ft.Dropdown(
            label="Model",
            options=model_options,
            value=cfg.get("model", "gemma-4-31b-it"),
            border_radius=12,
            filled=True,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )

        self._thinking_dropdown = ft.Dropdown(
            label="Thinking effort",
            options=self._thinking_options_for(cfg.get("model", "gemma-4-31b-it")),
            value=cfg.get("thinking_level", "HIGH"),
            border_radius=12,
            filled=True,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )

        self._model_dropdown.on_select = self._on_model_change

        self._auto_name_dropdown = ft.Dropdown(
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

        # ── Transcription tab ─────────────────────────────────────────
        self._transcription_method_dropdown = ft.Dropdown(
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
        self._transcription_method_dropdown.on_select = self._on_transcription_method_change

        self._whisper_model_dropdown = ft.Dropdown(
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

        self._whisper_options_container = ft.Column(
            [
                self._whisper_model_dropdown,
                ft.Text(
                    "Tiny/Base work on CPU. Small/Turbo need a dedicated GPU.",
                    size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
                ),
            ],
            tight=True,
            spacing=8,
            visible=cfg.get("transcription_method", "local_whisper") == "local_whisper",
        )

        self._assemblyai_hint = ft.Text(
            "Requires an AssemblyAI API key (set in API Keys tab).\n"
            "$50 free credit — up to ~333 hours of transcription.",
            size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
            visible=cfg.get("transcription_method", "local_whisper") == "assemblyai",
        )

        # ── Audio tab ─────────────────────────────────────────────────
        self._speaker_dropdown = ft.Dropdown(
            label="Speaker device (system audio)",
            options=[ft.dropdown.Option(key="", text="Default")],
            value=cfg.get("speaker_device", ""),
            border_radius=12,
            filled=True,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )
        self._mic_dropdown = ft.Dropdown(
            label="Microphone",
            options=[ft.dropdown.Option(key="", text="Disabled")],
            value=cfg.get("mic_device", ""),
            border_radius=12,
            filled=True,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )

        # ── Debug tab ─────────────────────────────────────────────────
        self._debug_switch = ft.Switch(
            label="Enable debug logging",
            value=cfg.get("debug_logging", False),
            on_change=self._on_debug_switch_change,
        )
        self._debug_path_text = ft.Text(
            f"Logs: {_debug_log.get_log_dir()}" if cfg.get("debug_logging") else "",
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
            visible=cfg.get("debug_logging", False),
        )

        # ── Tab panels ────────────────────────────────────────────────
        self._api_keys_panel = ft.Column(
            [
                self._google_key_field,
                self._assemblyai_key_field,
                ft.Text(
                    "Settings are stored locally in ~/.clueme/config.json",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=16,
            visible=True,
        )
        self._model_panel = ft.Column(
            [
                self._model_dropdown,
                self._thinking_dropdown,
                ft.Divider(height=1),
                self._auto_name_dropdown,
                ft.Text(
                    "Controls when AI generates a session name after recording stops.",
                    size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
                ),
            ],
            tight=True,
            spacing=16,
            visible=False,
        )
        self._transcription_panel = ft.Column(
            [
                self._transcription_method_dropdown,
                self._whisper_options_container,
                self._assemblyai_hint,
                ft.Text(
                    "Changes take effect next time you start listening.",
                    size=11, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
                ),
            ],
            tight=True,
            spacing=16,
            visible=False,
        )
        self._audio_panel = ft.Column(
            [
                self._speaker_dropdown,
                self._mic_dropdown,
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
            visible=False,
        )
        self._debug_panel = ft.Column(
            [
                self._debug_switch,
                self._debug_path_text,
            ],
            tight=True,
            spacing=16,
            visible=False,
        )
        self._panels = [
            self._api_keys_panel,
            self._model_panel,
            self._transcription_panel,
            self._audio_panel,
            self._debug_panel,
        ]

        self._tab_bar = ft.Tabs(
            ft.TabBar(
                tabs=[
                    ft.Tab("API Keys", icon=ft.Icons.VPN_KEY_OUTLINED),
                    ft.Tab("Model", icon=ft.Icons.PSYCHOLOGY_OUTLINED),
                    ft.Tab("Transcription", icon=ft.Icons.SUBTITLES_OUTLINED),
                    ft.Tab("Audio", icon=ft.Icons.HEADPHONES_OUTLINED),
                    ft.Tab("Debug", icon=ft.Icons.BUG_REPORT_OUTLINED),
                ],
            ),
            length=5,
            selected_index=0,
            on_change=self._on_tab_change,
        )

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Settings"),
            content=ft.Column(
                [
                    self._tab_bar,
                    ft.Container(
                        content=ft.Stack(self._panels),
                        height=280,
                        width=400,
                        padding=ft.Padding.only(top=12),
                    ),
                ],
                tight=True,
                spacing=8,
                width=420,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self._close),
                ft.FilledButton("Save", on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # Public: the toolbar button that opens this dialog
        self.button = ft.IconButton(
            icon=ft.Icons.SETTINGS_OUTLINED,
            tooltip="Settings",
            on_click=self.open,
        )

    # ── Public API ────────────────────────────────────────────────────

    def open(self, e=None):
        """Open the settings dialog, refreshing all values from config."""
        if self.button.disabled:
            return  # locked during streaming
        c = load_config()
        self._google_key_field.value = c.get("google_api_key", "")
        self._assemblyai_key_field.value = c.get("assemblyai_api_key", "")
        self._model_dropdown.value = c.get("model", "gemma-4-31b-it")
        self._thinking_dropdown.options = self._thinking_options_for(self._model_dropdown.value)
        self._thinking_dropdown.value = c.get("thinking_level", "HIGH")
        self._auto_name_dropdown.value = c.get("auto_name", "first_stop")
        # Transcription
        method = c.get("transcription_method", "local_whisper")
        self._transcription_method_dropdown.value = method
        self._whisper_model_dropdown.value = c.get("whisper_model", "tiny")
        self._whisper_options_container.visible = method == "local_whisper"
        self._assemblyai_hint.visible = method == "assemblyai"
        # Populate audio devices from live enumeration
        self._populate_device_dropdowns()
        speaker_keys = [opt.key for opt in self._speaker_dropdown.options]
        mic_keys = [opt.key for opt in self._mic_dropdown.options]
        saved_spk = c.get("speaker_device", "")
        saved_mic = c.get("mic_device", "")
        self._speaker_dropdown.value = saved_spk if saved_spk in speaker_keys else ""
        self._mic_dropdown.value = saved_mic if saved_mic in mic_keys else ""
        self._debug_switch.value = c.get("debug_logging", False)
        self._debug_path_text.value = f"Logs: {_debug_log.get_log_dir()}" if c.get("debug_logging") else ""
        self._debug_path_text.visible = c.get("debug_logging", False)
        # Reset to first tab
        self._tab_bar.selected_index = 0
        for i, p in enumerate(self._panels):
            p.visible = i == 0
        self._page.show_dialog(self._dialog)

    # ── Internals ─────────────────────────────────────────────────────

    @staticmethod
    def _thinking_options_for(model_key: str) -> list[ft.dropdown.Option]:
        levels = MODELS.get(model_key, {}).get("levels", ["HIGH"])
        return [ft.dropdown.Option(key=lv, text=lv.capitalize()) for lv in levels]

    def _on_model_change(self, e):
        new_model = self._model_dropdown.value
        allowed = MODELS.get(new_model, {}).get("levels", ["HIGH"])
        new_value = self._thinking_dropdown.value if self._thinking_dropdown.value in allowed else allowed[-1]
        self._thinking_dropdown.options = self._thinking_options_for(new_model)
        self._thinking_dropdown.value = new_value
        self._thinking_dropdown.update()
        self._page.update()

    def _on_transcription_method_change(self, e):
        method = self._transcription_method_dropdown.value
        self._whisper_options_container.visible = method == "local_whisper"
        self._assemblyai_hint.visible = method == "assemblyai"
        self._page.update()

    def _on_debug_switch_change(self, e):
        self._debug_path_text.value = f"Logs: {_debug_log.get_log_dir()}" if self._debug_switch.value else ""
        self._debug_path_text.visible = self._debug_switch.value
        self._page.update()

    def _on_tab_change(self, e):
        idx = int(e.data) if isinstance(e.data, str) else e.control.selected_index
        for i, p in enumerate(self._panels):
            p.visible = i == idx
        self._page.update()

    def _populate_device_dropdowns(self):
        devices = list_devices()
        self._speaker_dropdown.options = [ft.dropdown.Option(key="", text="Default")] + [
            ft.dropdown.Option(key=d["name"], text=d["name"]) for d in devices["speakers"]
        ]
        self._mic_dropdown.options = [ft.dropdown.Option(key="", text="Disabled")] + [
            ft.dropdown.Option(key=d["name"], text=d["name"]) for d in devices["mics"]
        ]

    def _close(self, e):
        self._page.pop_dialog()

    def _save(self, e):
        new_cfg = {
            "google_api_key": self._google_key_field.value.strip(),
            "assemblyai_api_key": self._assemblyai_key_field.value.strip(),
            "model": self._model_dropdown.value,
            "thinking_level": self._thinking_dropdown.value,
            "transcription_method": self._transcription_method_dropdown.value or "local_whisper",
            "whisper_model": self._whisper_model_dropdown.value or "tiny",
            "speaker_device": self._speaker_dropdown.value or "",
            "mic_device": self._mic_dropdown.value or "",
            "debug_logging": self._debug_switch.value,
            "auto_name": self._auto_name_dropdown.value or "first_stop",
        }
        save_config(new_cfg)
        apply_env(new_cfg)
        reconfigure_client(new_cfg["google_api_key"])
        set_model_config(new_cfg["model"], new_cfg["thinking_level"])
        if new_cfg["debug_logging"]:
            _debug_log.enable()
            _debug_log.log_event("SETTINGS", f"saved — model={new_cfg['model']} thinking={new_cfg['thinking_level']} auto_name={new_cfg['auto_name']} speaker={new_cfg['speaker_device']!r} mic={new_cfg['mic_device']!r}")
        else:
            _debug_log.disable()
        self._page.pop_dialog()
