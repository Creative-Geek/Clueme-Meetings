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

warnings.filterwarnings("ignore", category=DeprecationWarning, module="google.genai")
logging.raiseExceptions = False  # prevent recursive '--- Logging error ---' cascade

# Load config and apply env vars before anything reads them.
from src.config import load as load_config, apply_env

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

# App setup
from src.app.page_setup import setup_page
from src.app.state import initialize_state

# Handlers
from src.handlers.chat.send_handler import ChatHandler
from src.handlers.chat.retry_handler import RetryHandler
from src.handlers.chat.summarize_handler import SummarizeHandler
from src.handlers.chat.suggest_handler import SuggestHandler
from src.handlers.chat.edit_handler import EditHandler
from src.handlers.chat.stop_handler import StopHandler
from src.handlers.recording.start_handler import StartHandler
from src.handlers.recording.stop_handler import StopHandler as RecordingStopHandler
from src.handlers.recording.callbacks import RecordingCallbacks
from src.handlers.session.create_handler import CreateHandler
from src.handlers.session.enter_handler import EnterHandler
from src.handlers.session.back_handler import BackHandler
from src.handlers.session.delete_handler import DeleteHandler
from src.handlers.session.rename_handler import RenameHandler
from src.handlers.session.auto_name_handler import AutoNameHandler
from src.handlers.toolbar.update_handler import UpdateToolbarHandler
from src.handlers.toolbar.clear_handler import ClearHandler
from src.handlers.view.switch_handler import SwitchHandler
from src.handlers.view.rebuild_handler import RebuildHandler

# Layout
from src.layout.toolbar import create_meeting_toolbar, create_session_toolbar
from src.layout.meeting_view import create_meeting_view
from src.layout.home_view import create_home_view

# UI components
from src.ui.chat_tab import ChatTab
from src.ui.transcript_tab import TranscriptTab
from src.ui.session_list import SessionList
from src.ui.settings_dialog import SettingsDialog

# Session management
from src.sessions import list_sessions


def main(page: ft.Page):
    # ── Page setup ─────────────────────────────────────────────────
    setup_page(page)

    # ── State ──────────────────────────────────────────────────────
    cfg, transcriber, manager = initialize_state()
    transcriber_var = [transcriber]  # Mutable reference for handlers

    # ── UI components ──────────────────────────────────────────────
    transcript_tab = TranscriptTab()
    chat_tab = ChatTab()
    session_list_view = SessionList()
    settings = SettingsDialog(page)

    status_text = ft.Text("Ready", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    loading_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    # Overlay shown while loading heavy sessions
    session_loading_overlay = ft.Container(
        content=ft.Column(
            [
                ft.ProgressRing(width=32, height=32, stroke_width=3),
                ft.Text("Loading session…", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
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
            ft.Text("Naming…", size=12, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False,
    )

    # ── Recording banner for non-recording sessions ───────────────
    recording_info_banner = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=12, color=ft.Colors.ERROR),
                ft.Text("Recording active on another session", size=12, color=ft.Colors.ON_ERROR_CONTAINER),
                ft.Container(expand=True),
                ft.Text("Go to recording", size=12, color=ft.Colors.ON_ERROR_CONTAINER, italic=True),
                ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=ft.Colors.ON_ERROR_CONTAINER),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        ),
        padding=ft.Padding(left=12, top=8, right=12, bottom=8),
        border_radius=8,
        bgcolor=ft.Colors.ERROR_CONTAINER,
        ink=True,
        on_click=lambda e: enter_handler.enter(manager.recording_path) if manager.recording_path else None,
        visible=False,
    )

    # ── Clear menu ────────────────────────────────────────────────
    clear_menu_btn = ft.PopupMenuButton(
        icon=ft.Icons.DELETE_OUTLINE,
        tooltip="Clear…",
        items=[
            ft.PopupMenuItem(
                content="Clear chat",
                icon=ft.Icons.CHAT_OUTLINED,
                data="chat",
            ),
            ft.PopupMenuItem(
                content="Clear transcript",
                icon=ft.Icons.SUBTITLES_OUTLINED,
                data="transcript",
            ),
            ft.PopupMenuItem(),  # divider
            ft.PopupMenuItem(
                content="Clear all",
                icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                data="all",
            ),
        ],
    )

    start_btn = ft.Button(
        "Start Listening",
        icon=ft.Icons.MIC,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
    )

    stop_btn = ft.Button(
        "Stop",
        icon=ft.Icons.STOP,
        visible=False,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), color=ft.Colors.ERROR),
    )

    # ── Helper functions ────────────────────────────────────────────
    def get_session_name(path) -> str:
        """Return the display name for a session path."""
        for s in list_sessions():
            if s["path"] == path:
                return s.get("name", "") or "Untitled Session"
        return "Untitled Session"

    # ── Initialize handlers ─────────────────────────────────────────
    # Recording callbacks
    recording_callbacks = RecordingCallbacks(manager, transcript_tab, page)

    # Recording handlers
    start_handler = StartHandler(
        manager,
        transcriber_var,
        start_btn,
        stop_btn,
        loading_ring,
        recording_info_banner,
        status_text,
        page,
        recording_callbacks.on_confirmed,
        recording_callbacks.on_tentative,
        lambda: recording_callbacks.on_ready(loading_ring, status_text),
        lambda msg: recording_callbacks.on_error(msg, start_btn, stop_btn, loading_ring, status_text),
    )

    stop_handler = RecordingStopHandler(
        manager,
        transcriber_var,
        start_btn,
        stop_btn,
        loading_ring,
        recording_info_banner,
        status_text,
        session_list_view,
        page,
        session_title_text,
        naming_indicator,
        None,  # Will be set after auto_name_handler is created
    )

    # Chat handlers
    chat_handler = ChatHandler(manager, chat_tab, transcriber_var[0], page, settings, clear_menu_btn)
    retry_handler = RetryHandler(manager, chat_tab, transcriber_var[0], page, settings, clear_menu_btn)
    summarize_handler = SummarizeHandler(chat_handler)
    suggest_handler = SuggestHandler(chat_handler)
    edit_handler = EditHandler(manager)
    stop_chat_handler = StopHandler(manager)

    # Session handlers
    auto_name_handler = AutoNameHandler(manager, session_title_text, naming_indicator, session_list_view, page)
    stop_handler.auto_name_session_func = auto_name_handler.auto_name_session

    create_handler = CreateHandler(
        manager,
        transcript_tab,
        chat_tab,
        session_title_text,
        naming_indicator,
        None,  # Will be set after update_toolbar_handler is created
        None,  # Will be set after show_meeting_view is defined
    )

    enter_handler = EnterHandler(
        manager,
        session_loading_overlay,
        None,  # Will be set after show_meeting_view is defined
        None,  # Will be set after rebuild_handler is created
        None,  # Will be set after update_toolbar_handler is created
        page,
    )

    back_handler = BackHandler(manager, session_list_view, None, get_session_name)  # show_session_list will be set
    delete_handler = DeleteHandler(manager, session_list_view, page)
    rename_handler = RenameHandler(manager, session_list_view, session_title_text, page)

    # Toolbar handlers
    update_toolbar_handler = UpdateToolbarHandler(manager, start_btn, stop_btn, recording_info_banner, status_text, get_session_name)
    clear_handler = ClearHandler(manager, chat_tab, transcript_tab)

    # View handlers
    rebuild_handler = RebuildHandler(transcript_tab, chat_tab, session_title_text, naming_indicator, get_session_name)
    enter_handler.rebuild_ui_func = rebuild_handler.rebuild
    enter_handler.update_toolbar_func = update_toolbar_handler.update

    # Wire clear menu
    for item in clear_menu_btn.items:
        item.on_click = lambda e, action=item.data: clear_handler.handle_clear(action)

    # Wire start/stop buttons
    start_btn.on_click = lambda e: start_handler.start()
    stop_btn.on_click = lambda e: page.run_task(stop_handler.stop)

    # Wire session handlers
    create_handler.update_toolbar_func = update_toolbar_handler.update

    # Wire chat tab handlers
    chat_tab._on_send = lambda msg, imgs: page.run_task(chat_handler.send, msg, imgs)
    chat_tab._on_summarize = lambda: page.run_task(summarize_handler.summarize)
    chat_tab._on_suggest = lambda: page.run_task(suggest_handler.suggest)
    chat_tab._on_stop = lambda: stop_chat_handler.stop()
    chat_tab._on_edit = lambda idx: edit_handler.edit(idx)
    chat_tab._on_retry = lambda: page.run_task(retry_handler.retry)

    # ── Transcript data provider ──────────────────────────────────
    import time as _time
    from src.ui.chat_tab import StreamChunk

    def format_transcript_text() -> str:
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

    transcript_tab._get_text = format_transcript_text

    # ── View switching functions ───────────────────────────────────
    def show_meeting_view():
        """Switch to meeting view."""
        home_view.visible = False
        meeting_view.visible = True
        page.update()

    def show_session_list():
        """Switch to session list view."""
        meeting_view.visible = False
        home_view.visible = True
        session_list_view.refresh(list_sessions())
        page.update()

    # Wire view handlers
    enter_handler.show_meeting_view_func = show_meeting_view
    create_handler.show_meeting_view_func = show_meeting_view
    back_handler.show_session_list_func = show_session_list

    # Wire session list callbacks
    session_list_view._on_new_session = create_handler.create
    session_list_view._on_select_session = enter_handler.enter
    session_list_view._on_delete_session = delete_handler.delete
    session_list_view._on_resume_session = lambda: enter_handler.enter(manager.recording_path) if manager.recording_path else None
    session_list_view._on_rename_session = lambda path, name: session_list_view.show_rename_dialog(
        path, name, on_ai_suggest=rename_handler.ai_suggest_name, on_confirm=rename_handler.confirm_rename
    )

    # ── Layout ─────────────────────────────────────────────────────
    transcript_panel = ft.Container(content=transcript_tab, expand=True, visible=True)
    chat_panel = ft.Container(content=chat_tab, expand=True, visible=False)
    panels = [transcript_panel, chat_panel]

    # View switch handler
    switch_handler = SwitchHandler(transcript_tab, chat_tab, panels)

    tab_bar = ft.Tabs(
        ft.TabBar(
            tabs=[
                ft.Tab("Transcript", icon=ft.Icons.SUBTITLES_OUTLINED),
                ft.Tab("Chat", icon=ft.Icons.CHAT_OUTLINED),
            ],
        ),
        length=2,
        selected_index=0,
        on_change=switch_handler.switch,
    )

    back_btn = ft.IconButton(
        icon=ft.Icons.ARROW_BACK,
        tooltip="Back to sessions",
        on_click=lambda e: back_handler.back(),
    )

    meeting_toolbar = create_meeting_toolbar(
        back_btn,
        start_btn,
        stop_btn,
        loading_ring,
        session_title_text,
        naming_indicator,
        status_text,
        clear_menu_btn,
        settings.button,
    )

    # Meeting view container (hidden initially)
    meeting_view = create_meeting_view(
        meeting_toolbar,
        recording_info_banner,
        tab_bar,
        panels,
        session_loading_overlay,
    )

    # Session list toolbar
    session_toolbar = create_session_toolbar(settings.button)

    # Session list view container (visible initially)
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "full_logo.svg")
    home_view = create_home_view(session_toolbar, session_list_view, logo_path)

    # Initialize session list
    session_list_view.refresh(list_sessions())

    page.add(
        ft.Stack(
            [home_view, meeting_view],
            expand=True,
        ),
    )


if __name__ == "__main__":
    print("version: 0.0.5")
    import multiprocessing

    multiprocessing.freeze_support()
    ft.run(main)
