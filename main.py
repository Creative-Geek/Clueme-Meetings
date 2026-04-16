"""Clueme Meetings — Real-time meeting assistant.

Entry point. Two views:
  - Session list (home page): pick or create a session
  - Meeting view: transcript + chat tabs with live recording

Supports multi-session prompting: browse and chat with any session
while recording continues on another.
"""

import os
import logging
import warnings
import asyncio
import faulthandler
import time as _time

warnings.filterwarnings("ignore", category=DeprecationWarning, module="google.genai")
logging.raiseExceptions = False  # prevent recursive '--- Logging error ---' cascade

# Load config and apply env vars before anything reads them.
from src.config import load as load_config, save as save_config, apply_env

apply_env()

from src import debug_log as _debug_log

_startup_cfg = load_config()
if _startup_cfg.get("debug_logging"):
    _debug_log.enable()

# Enable faulthandler to capture native crash tracebacks
_crash_log_path = _debug_log.get_log_dir() / "crash.log"
_crash_log_path.parent.mkdir(parents=True, exist_ok=True)
_crash_log_file = open(_crash_log_path, "a", encoding="utf-8")
faulthandler.enable(file=_crash_log_file)

import flet as ft

from src.agent import (
    reconfigure_client,
    MODELS,
    set_model_config,
    generate_session_title,
)
from src.sessions import list_sessions, rename_session, delete_session
from src.session_context import SessionManager
from src.transcriber import LiveTranscriber, list_devices
from src.ui.chat_tab import ChatTab, StreamChunk
from src.ui.transcript_tab import TranscriptTab
from src.ui.session_list import SessionList
from src.ui.settings_dialog import SettingsDialog


SUMMARIZE_PROMPT = (
    "Summarize everything discussed in this meeting so far (minus anything you already summarized), organized by topic. "
    "Be concise and use bullet points."
)


def main(page: ft.Page):
    # ── Page setup ─────────────────────────────────────────────────
    page.title = "Clueme Meetings"
    page.theme_mode = ft.ThemeMode.DARK
    page.dark_theme = ft.Theme(
        color_scheme_seed=ft.Colors.CYAN,
    )
    page.padding = 16
    page.window.width = 700
    page.window.height = 800

    # App icon (Windows taskbar + title bar)
    _icon_path = os.path.join(
        os.path.dirname(__file__), "assets", "logo_no_text_cropped.ico"
    )
    if os.path.exists(_icon_path):
        page.window.icon = _icon_path

    # ── State ──────────────────────────────────────────────────────
    cfg = load_config()
    transcriber: LiveTranscriber | None = None
    manager = SessionManager()

    # Apply saved model config
    set_model_config(
        cfg.get("model", "gemma-4-31b-it"), cfg.get("thinking_level", "HIGH")
    )

    # ── UI components ──────────────────────────────────────────────
    transcript_tab = TranscriptTab()
    chat_tab = ChatTab()
    session_list_view = SessionList()
    settings = SettingsDialog(page)

    status_text = ft.Text(
        "Ready",
        size=12,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    loading_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    # Overlay shown while loading heavy sessions
    _session_loading_overlay = ft.Container(
        content=ft.Column(
            [
                ft.ProgressRing(width=32, height=32, stroke_width=3),
                ft.Text(
                    "Loading session…", size=14, color=ft.Colors.ON_SURFACE_VARIANT
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.SURFACE),
        visible=False,
    )

    session_title_text = ft.Text("", size=13, weight=ft.FontWeight.W_500)
    naming_indicator = ft.Row(
        [
            ft.ProgressRing(width=12, height=12, stroke_width=2),
            ft.Text(
                "Naming…", size=12, italic=True, color=ft.Colors.ON_SURFACE_VARIANT
            ),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False,
    )

    # ── Recording banner for non-recording sessions ───────────────
    def _goto_recording_session(e):
        """Navigate to the recording session from the banner."""
        if manager.recording_path:
            _enter_session(manager.recording_path)

    recording_info_banner = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=12, color=ft.Colors.ERROR),
                ft.Text(
                    "Recording active on another session",
                    size=12,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                ),
                ft.Container(expand=True),
                ft.Text(
                    "Go to recording",
                    size=12,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    italic=True,
                ),
                ft.Icon(
                    ft.Icons.ARROW_FORWARD, size=14, color=ft.Colors.ON_ERROR_CONTAINER
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        ),
        padding=ft.Padding(left=12, top=8, right=12, bottom=8),
        border_radius=8,
        bgcolor=ft.Colors.ERROR_CONTAINER,
        ink=True,
        on_click=_goto_recording_session,
        visible=False,
    )

    # ── Clear menu ────────────────────────────────────────────────
    def handle_clear_menu(e):
        action = e.control.data
        ctx = manager.viewed_context
        if not ctx:
            return
        if action == "chat":
            ctx.chat_log.clear()
            chat_tab.clear()
        elif action == "transcript":
            ctx.transcript_log.clear()
            transcript_tab.clear()
        elif action == "all":
            ctx.chat_log.clear()
            chat_tab.clear()
            ctx.transcript_log.clear()
            transcript_tab.clear()
        page.update()

    clear_menu_btn = ft.PopupMenuButton(
        icon=ft.Icons.DELETE_OUTLINE,
        tooltip="Clear…",
        items=[
            ft.PopupMenuItem(
                content="Clear chat",
                icon=ft.Icons.CHAT_OUTLINED,
                data="chat",
                on_click=handle_clear_menu,
            ),
            ft.PopupMenuItem(
                content="Clear transcript",
                icon=ft.Icons.SUBTITLES_OUTLINED,
                data="transcript",
                on_click=handle_clear_menu,
            ),
            ft.PopupMenuItem(),  # divider
            ft.PopupMenuItem(
                content="Clear all",
                icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                data="all",
                on_click=handle_clear_menu,
            ),
        ],
    )

    start_btn = ft.Button(
        "Start Listening",
        icon=ft.Icons.MIC,
        on_click=lambda e: start_listening(e),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=12),
        ),
    )

    stop_btn = ft.Button(
        "Stop",
        icon=ft.Icons.STOP,
        on_click=lambda e: stop_listening(e),
        visible=False,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=12),
            color=ft.Colors.ERROR,
        ),
    )

    # ── Session name helpers ──────────────────────────────────────
    def _get_session_name(path) -> str:
        """Return the display name for a session path."""
        for s in list_sessions():
            if s["path"] == path:
                return s.get("name", "") or "Untitled Session"
        return "Untitled Session"

    # ── Auto-save helper ──────────────────────────────────────────
    def _auto_save():
        """Save the currently viewed session."""
        manager.save_viewed()

    async def _auto_name_session(session_path):
        """Generate an AI title based on the auto_name config setting."""
        if not session_path:
            return

        c = load_config()
        auto_name = c.get("auto_name", "first_stop")

        if auto_name == "never":
            _debug_log.log_event("AUTO_NAME", "skipped — auto_name=never")
            return

        # Find session metadata
        session_meta = None
        for s in list_sessions():
            if s["path"] == session_path:
                session_meta = s
                break
        if not session_meta:
            _debug_log.log_event("AUTO_NAME", "skipped — session not found in list")
            return

        # Never overwrite a manually-set name
        if session_meta.get("name_source") == "manual":
            _debug_log.log_event(
                "AUTO_NAME",
                f"skipped — manual name anchored: {session_meta.get('name')!r}",
            )
            return

        # "first_stop": skip if any name already exists
        if auto_name == "first_stop" and session_meta.get("name"):
            _debug_log.log_event(
                "AUTO_NAME",
                f"skipped — first_stop and already named: {session_meta.get('name')!r}",
            )
            return

        # Generate from transcript
        ctx = manager.get_or_load(session_path)
        transcript_text = " ".join(e.text for e in ctx.transcript_log.entries)
        if not transcript_text.strip():
            _debug_log.log_event("AUTO_NAME", "skipped — transcript is empty")
            return
        _debug_log.log_event(
            "AUTO_NAME",
            f"calling AI — mode={auto_name} transcript_len={len(transcript_text)}",
        )
        if manager.viewed_path == session_path:
            session_title_text.visible = False
            naming_indicator.visible = True
            page.update()
        try:
            title = await generate_session_title(transcript_text)
            _debug_log.log_event("AUTO_NAME", f"AI returned: {title!r}")
            rename_session(session_path, title, source="auto")
            if manager.viewed_path == session_path:
                session_title_text.value = title
                session_title_text.visible = True
                naming_indicator.visible = False
            session_list_view.refresh(list_sessions())
            page.update()
        except Exception as ex:
            _debug_log.log_event("AUTO_NAME", f"ERROR: {ex}")
            if manager.viewed_path == session_path:
                session_title_text.visible = True
                naming_indicator.visible = False
                page.update()

    # ── Transcriber callbacks ──────────────────────────────────────
    def on_confirmed(text: str, minute: int):
        """Transcriber confirmed text — write to RECORDING session."""
        rec = manager.recording_context
        if not rec:
            return
        rec.transcript_log.append(text=text, minute=minute)

        # Incremental save — persist immediately so a crash can't lose data
        if manager.recording_path:
            manager.save(manager.recording_path)

        # Only update the transcript UI if viewing the recording session
        if manager.viewing_recording:

            async def _update():
                transcript_tab.add_confirmed(text, minute)
                page.update()

            page.run_task(_update)

    def on_tentative(text: str):
        # Only show tentative text if viewing the recording session
        if manager.viewing_recording:

            async def _update():
                transcript_tab.set_tentative(text)
                page.update()

            page.run_task(_update)

    def on_transcriber_ready():
        async def _update():
            loading_ring.visible = False
            status_text.value = "🎧 Listening…"
            status_text.color = ft.Colors.PRIMARY
            page.update()

        page.run_task(_update)

    def on_transcriber_error(message: str):
        async def _update():
            loading_ring.visible = False
            start_btn.visible = True
            stop_btn.visible = False
            start_btn.disabled = False
            status_text.value = f"⚠️ {message}"
            status_text.color = ft.Colors.ERROR
            manager.stop_recording()
            page.update()

        page.run_task(_update)

    # ── Start / Stop ───────────────────────────────────────────────
    def start_listening(e):
        nonlocal transcriber
        if manager.is_recording:
            return  # already recording another session

        # Ensure previous transcriber is fully cleaned up before creating a new one
        if transcriber:
            transcriber.stop(wait=True)
            transcriber = None

        start_btn.visible = False
        stop_btn.visible = True
        loading_ring.visible = True
        recording_info_banner.visible = False
        status_text.value = "Loading model…"
        status_text.color = ft.Colors.ON_SURFACE_VARIANT
        page.update()

        # Mark this session as the recording target
        if manager.viewed_path:
            manager.start_recording(manager.viewed_path)

        c = load_config()
        transcriber = LiveTranscriber(
            model_size=c.get("whisper_model", "tiny"),
            speaker_device_name=c.get("speaker_device", ""),
            mic_device_name=c.get("mic_device", ""),
            on_confirmed=on_confirmed,
            on_tentative=on_tentative,
            on_ready=on_transcriber_ready,
            on_error=on_transcriber_error,
        )
        transcriber.start()

    def stop_listening(e):
        page.run_task(handle_stop_listening)

    async def handle_stop_listening():
        nonlocal transcriber
        recording_path = manager.recording_path

        # Disable button during wait
        stop_btn.disabled = True
        status_text.value = "Finalizing transcript…"
        status_text.color = ft.Colors.ON_SURFACE_VARIANT
        page.update()

        if transcriber:
            # Wait for backend threads to finish promotion
            await asyncio.to_thread(transcriber.stop, wait=True)
            transcriber = None

        manager.stop_recording()
        start_btn.visible = True
        stop_btn.visible = False
        stop_btn.disabled = False
        start_btn.disabled = False
        loading_ring.visible = False
        recording_info_banner.visible = False
        status_text.value = "Stopped"
        status_text.color = ft.Colors.ON_SURFACE_VARIANT
        session_list_view.set_recording(False)
        page.update()

        # Auto-save the recording session
        if recording_path:
            manager.save(recording_path)
            await _auto_name_session(recording_path)

    # ── Toolbar state helper ──────────────────────────────────────
    def _update_toolbar_for_session():
        """Update Start/Stop buttons and banners based on recording state vs viewed session."""
        if not manager.is_recording:
            # No recording active — show Start, hide banner
            start_btn.visible = True
            start_btn.disabled = False
            stop_btn.visible = False
            recording_info_banner.visible = False
            status_text.value = "Ready"
            status_text.color = ft.Colors.ON_SURFACE_VARIANT
        elif manager.viewing_recording:
            # Viewing the recording session — show Stop
            start_btn.visible = False
            stop_btn.visible = True
            recording_info_banner.visible = False
            status_text.value = "🎧 Listening…"
            status_text.color = ft.Colors.PRIMARY
        else:
            # Recording, but viewing a different session
            start_btn.visible = True
            start_btn.disabled = True
            start_btn.tooltip = "Stop the active recording first"
            stop_btn.visible = False
            recording_info_banner.visible = True
            rec_name = _get_session_name(manager.recording_path)
            recording_info_banner.content.controls[1].value = f"Recording: {rec_name}"
            status_text.value = "Browsing saved session"
            status_text.color = ft.Colors.ON_SURFACE_VARIANT

    # ── Chat handlers ──────────────────────────────────────────────
    async def handle_chat_send(user_message: str):
        ctx = manager.viewed_context
        if not ctx:
            return

        chat_tab.add_user_message(user_message)
        chat_tab.start_assistant_message()
        chat_tab.set_streaming(True)
        settings.button.disabled = True
        clear_menu_btn.disabled = True
        page.update()

        # Use system-time minute for ordering
        minute = int(_time.time() // 60)
        tentative = (
            transcriber.tentative if (transcriber and manager.viewing_recording) else ""
        )

        try:
            async for chunk in ctx.chat.send(user_message, minute, tentative):
                chat_tab.append_chunk(chunk)
                page.update()
        except Exception as e:
            chat_tab.append_chunk(StreamChunk(text=f"\n\n⚠️ Error: {e}"))
            page.update()

        chat_tab.finish_assistant_message()
        chat_tab.set_streaming(False)
        settings.button.disabled = False
        clear_menu_btn.disabled = False
        page.update()

        # Auto-save after chat exchange
        _auto_save()

    def on_chat_send(message: str):
        page.run_task(handle_chat_send, message)

    def on_chat_stop():
        ctx = manager.viewed_context
        if ctx:
            ctx.chat.cancel()

    def on_chat_edit(bubble_index: int):
        """User edited a message — truncate ChatLog to match."""
        ctx = manager.viewed_context
        if ctx:
            ctx.chat_log.truncate_from(bubble_index)

    def on_chat_retry():
        """User clicked retry — remove last model response, re-stream."""
        ctx = manager.viewed_context
        if not ctx:
            return
        last_user_text = ctx.chat.pop_last_model_response()
        if last_user_text:
            page.run_task(handle_retry)

    async def handle_retry():
        """Re-send the last user message (already in ChatLog)."""
        ctx = manager.viewed_context
        if not ctx:
            return

        chat_tab.start_assistant_message()
        chat_tab.set_streaming(True)
        settings.button.disabled = True
        clear_menu_btn.disabled = True
        page.update()

        minute = int(_time.time() // 60)
        tentative = (
            transcriber.tentative if (transcriber and manager.viewing_recording) else ""
        )

        try:
            async for chunk in ctx.chat.resend(minute, tentative):
                chat_tab.append_chunk(chunk)
                page.update()
        except Exception as e:
            chat_tab.append_chunk(StreamChunk(text=f"\n\n⚠️ Error: {e}"))
            page.update()

        chat_tab.finish_assistant_message()
        chat_tab.set_streaming(False)
        settings.button.disabled = False
        clear_menu_btn.disabled = False
        page.update()

        # Auto-save after retry
        _auto_save()

    def on_summarize():
        on_chat_send(SUMMARIZE_PROMPT)

    chat_tab._on_send = on_chat_send
    chat_tab._on_summarize = on_summarize
    chat_tab._on_stop = on_chat_stop
    chat_tab._on_edit = on_chat_edit
    chat_tab._on_retry = on_chat_retry

    # ── Transcript data provider ──────────────────────────────────
    def _format_transcript_text() -> str:
        """Format transcript log entries as plain text with minute headers."""
        ctx = manager.viewed_context
        if not ctx:
            return ""
        lines: list[str] = []
        last_min = -1
        for entry in ctx.transcript_log.entries:
            if entry.minute > last_min:
                last_min = entry.minute
                t = _time.localtime(entry.minute * 60)
                lines.append(f"\n[{t.tm_hour:02d}:{t.tm_min:02d}]")
            lines.append(entry.text)
        return "\n".join(lines).strip()

    transcript_tab._get_text = _format_transcript_text

    # ── View switching (session list ↔ meeting view) ──────────────
    def _rebuild_ui_from_context(ctx):
        """Rebuild transcript and chat UI from a session context."""
        transcript_tab.clear()
        for entry in ctx.transcript_log.entries:
            transcript_tab.add_confirmed(entry.text, entry.minute)

        chat_tab.clear()
        for entry in ctx.chat_log.entries:
            if entry.role == "user":
                chat_tab.add_user_message(entry.text)
            elif entry.role == "model":
                chat_tab.start_assistant_message()
                chat_tab.append_chunk(StreamChunk(text=entry.text))
                chat_tab.finish_assistant_message()

        # Update session title in toolbar
        name = _get_session_name(ctx.path)
        session_title_text.value = name
        session_title_text.visible = True
        naming_indicator.visible = False

    def _enter_session(session_path):
        """Load a session and switch to meeting view. Always allowed."""
        _debug_log.log_event("SESSION", f"enter — {session_path}")
        # Save current viewed session first
        manager.save_viewed()

        # Show loading overlay immediately, then defer heavy work
        _session_loading_overlay.visible = True
        _show_meeting_view()
        page.update()

        async def _do_load():
            # Yield to event loop so the spinner renders
            await asyncio.sleep(0.05)

            # Heavy work: load + rebuild UI
            ctx = manager.get_or_load(session_path)
            manager.set_viewed(session_path)
            _rebuild_ui_from_context(ctx)
            _update_toolbar_for_session()

            _session_loading_overlay.visible = False
            page.update()

        page.run_task(_do_load)

    def _new_session():
        """Create a fresh session and switch to meeting view. Always allowed."""
        _debug_log.log_event("SESSION", "new session created")
        # Save current viewed session first
        manager.save_viewed()

        ctx = manager.create_new()
        manager.set_viewed(ctx.path)
        transcript_tab.clear()
        chat_tab.clear()
        session_title_text.value = ""
        naming_indicator.visible = False
        _update_toolbar_for_session()
        _show_meeting_view()

    def _back_to_sessions(e=None):
        """Navigate back to session list. Keep transcriber alive if recording."""
        _auto_save()

        if manager.is_recording:
            rec_name = _get_session_name(manager.recording_path)
            session_list_view.set_recording(
                True,
                session_name=rec_name,
                recording_path=manager.recording_path,
            )
        else:
            session_list_view.set_recording(False)

        manager.clear_viewed()
        _show_session_list()

    def _resume_active_session():
        """Return to the recording session from the session list."""
        if manager.recording_path:
            _enter_session(manager.recording_path)

    def _delete_and_refresh(path):
        _debug_log.log_event("SESSION", f"delete — {path}")
        delete_session(path)
        manager.evict(path)
        session_list_view.refresh(list_sessions())
        page.update()

    # ── Rename helpers (logic callbacks for SessionList dialog) ────
    async def _ai_suggest_name(path):
        """Generate an AI title from a session's transcript."""
        ctx = manager.get_or_load(path)
        transcript_text = " ".join(entry.text for entry in ctx.transcript_log.entries)
        _debug_log.log_event(
            "RENAME", f"AI suggest — transcript_len={len(transcript_text)}"
        )
        title = await generate_session_title(transcript_text)
        _debug_log.log_event("RENAME", f"AI returned: {title!r}")
        return title

    def _confirm_rename(path, new_name):
        """Commit a rename and refresh the UI."""
        _debug_log.log_event("RENAME", f"manual rename: {new_name!r} (source=manual)")
        rename_session(path, new_name, source="manual")
        if manager.viewed_path == path:
            session_title_text.value = new_name
        session_list_view.refresh(list_sessions())
        page.update()

    def _handle_rename_session(path, current_name):
        session_list_view.show_rename_dialog(
            path,
            current_name,
            on_ai_suggest=_ai_suggest_name,
            on_confirm=_confirm_rename,
        )

    # Wire session list callbacks
    session_list_view._on_new_session = _new_session
    session_list_view._on_select_session = _enter_session
    session_list_view._on_delete_session = _delete_and_refresh
    session_list_view._on_resume_session = _resume_active_session
    session_list_view._on_rename_session = _handle_rename_session

    # ── Layout ─────────────────────────────────────────────────────
    transcript_panel = ft.Container(content=transcript_tab, expand=True, visible=True)
    chat_panel = ft.Container(content=chat_tab, expand=True, visible=False)
    panels = [transcript_panel, chat_panel]

    def on_tab_change(e):
        idx = int(e.data) if isinstance(e.data, str) else e.control.selected_index
        for i, p in enumerate(panels):
            p.visible = i == idx
        # Scroll the newly-visible tab to bottom
        if idx == 0:
            transcript_tab.scroll_to_bottom()
        elif idx == 1:
            chat_tab.scroll_to_bottom()
        page.update()

    tab_bar = ft.Tabs(
        ft.TabBar(
            tabs=[
                ft.Tab("Transcript", icon=ft.Icons.SUBTITLES_OUTLINED),
                ft.Tab("Chat", icon=ft.Icons.CHAT_OUTLINED),
            ],
        ),
        length=2,
        selected_index=0,
        on_change=on_tab_change,
    )

    back_btn = ft.IconButton(
        icon=ft.Icons.ARROW_BACK,
        tooltip="Back to sessions",
        on_click=_back_to_sessions,
    )

    meeting_toolbar = ft.Row(
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
            settings.button,
        ],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # Meeting view container (hidden initially)
    meeting_view = ft.Column(
        controls=[
            meeting_toolbar,
            recording_info_banner,
            ft.Divider(height=1),
            tab_bar,
            ft.Container(
                content=ft.Stack([*panels, _session_loading_overlay]),
                expand=True,
            ),
        ],
        expand=True,
        visible=False,
    )

    # Session list toolbar
    session_toolbar = ft.Row(
        controls=[
            ft.Container(expand=True),
            settings.button,
        ],
        alignment=ft.MainAxisAlignment.END,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # Session list view container (visible initially)
    _logo_path = os.path.join(os.path.dirname(__file__), "assets", "full_logo.svg")
    home_view = ft.Column(
        controls=[
            session_toolbar,
            ft.Container(
                content=ft.Image(src=_logo_path, width=120, height=120, color="#83d3e3")
                if os.path.exists(_logo_path)
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

    def _show_meeting_view():
        home_view.visible = False
        meeting_view.visible = True
        page.update()

    def _show_session_list():
        meeting_view.visible = False
        home_view.visible = True
        session_list_view.refresh(list_sessions())
        page.update()

    # Initialize session list
    session_list_view.refresh(list_sessions())

    page.add(
        ft.Stack(
            [home_view, meeting_view],
            expand=True,
        ),
    )


if __name__ == "__main__":
    print("version: 0.0.2")
    import multiprocessing

    multiprocessing.freeze_support()
    ft.run(main)
