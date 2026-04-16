"""Session list — home page showing saved sessions."""

from typing import Callable

import flet as ft


class SessionList(ft.Column):
    """Home page: list of sessions with 'New Session' button."""

    def __init__(self):
        super().__init__(expand=True)

        self._on_new_session = None      # callback()
        self._on_select_session = None   # callback(path)
        self._on_delete_session = None   # callback(path)
        self._on_resume_session = None   # callback() — return to active recording
        self._on_rename_session = None   # callback(path, current_name)

        self._recording_path = None  # Path of the currently recording session

        self._list = ft.ListView(
            expand=True,
            spacing=8,
            padding=ft.Padding.all(16),
        )

        self._empty_text = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.EVENT_NOTE_OUTLINED, size=48, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        "No sessions yet",
                        size=16,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        "Start a new session to begin recording",
                        size=13,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            visible=False,
        )

        # Recording banner — shown when a session is recording in the background
        self._recording_banner = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=12, color=ft.Colors.ERROR),
                    ft.Text(
                        "Session recording in progress",
                        size=13,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.ON_ERROR_CONTAINER,
                    ),
                    ft.Container(expand=True),
                    ft.Text(
                        "Tap to return",
                        size=12,
                        color=ft.Colors.ON_ERROR_CONTAINER,
                        italic=True,
                    ),
                    ft.Icon(ft.Icons.ARROW_FORWARD, size=16, color=ft.Colors.ON_ERROR_CONTAINER),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.Padding(left=16, top=10, right=16, bottom=10),
            border_radius=12,
            bgcolor=ft.Colors.ERROR_CONTAINER,
            ink=True,
            on_click=lambda e: self._on_resume_session() if self._on_resume_session else None,
            visible=False,
        )

        self._recording_name_text = self._recording_banner.content.controls[1]

        self._new_session_btn = ft.Button(
            "New Session",
            icon=ft.Icons.ADD,
            on_click=lambda e: self._on_new_session() if self._on_new_session else None,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
        )

        self.controls = [
            ft.Row(
                controls=[
                    ft.Text("Sessions", size=20, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    self._new_session_btn,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Divider(height=1),
            self._recording_banner,
            ft.Stack(
                [self._list, self._empty_text],
                expand=True,
            ),
        ]

    def set_recording(self, recording: bool, session_name: str = "", recording_path=None):
        """Show/hide the recording banner. Sessions and New Session stay enabled."""
        self._recording_path = recording_path
        self._recording_banner.visible = recording
        if recording and session_name:
            self._recording_name_text.value = f"Recording: {session_name}"
        elif recording:
            self._recording_name_text.value = "Session recording in progress"

    def refresh(self, sessions: list[dict]):
        """Rebuild the session list from session metadata dicts."""
        self._list.controls.clear()

        if not sessions:
            self._empty_text.visible = True
            self._list.visible = False
            return

        self._empty_text.visible = False
        self._list.visible = True

        for s in sessions:
            created = s.get("created", "")[:16].replace("T", " ") if s.get("created") else ""
            name = s.get("name", "") or "Untitled Session"
            t_count = s.get("transcript_count", 0)
            c_count = s.get("chat_count", 0)
            path = s["path"]
            is_recording = self._recording_path and path == self._recording_path

            # Recording indicator
            leading_icon = ft.Icon(
                ft.Icons.FIBER_MANUAL_RECORD,
                size=10,
                color=ft.Colors.ERROR,
                visible=bool(is_recording),
            )

            tile = ft.Container(
                content=ft.Row(
                    controls=[
                        leading_icon,
                        ft.Column(
                            [
                                ft.Text(name, size=14, weight=ft.FontWeight.W_500),
                                ft.Text(
                                    f"{created}  •  {t_count} transcript, {c_count} chat",
                                    size=11,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.EDIT_OUTLINED,
                            icon_size=18,
                            tooltip="Rename",
                            icon_color=ft.Colors.ON_SURFACE_VARIANT,
                            on_click=lambda e, p=path, n=name: (
                                self._on_rename_session(p, n) if self._on_rename_session else None
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_size=18,
                            tooltip="Delete",
                            icon_color=ft.Colors.ON_SURFACE_VARIANT,
                            on_click=lambda e, p=path: self._handle_delete(p),
                            disabled=is_recording,  # can't delete the recording session
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.Padding.all(12),
                border_radius=12,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                ink=True,
                on_click=lambda e, p=path: self._on_select_session(p) if self._on_select_session else None,
            )
            self._list.controls.append(tile)

    def _handle_delete(self, path):
        def confirm(e):
            dlg.open = False
            self.page.update()
            if self._on_delete_session:
                self._on_delete_session(path)

        def cancel(e):
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Delete Session"),
            content=ft.Text("Are you sure you want to delete this session? This action cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Delete", on_click=confirm, style=ft.ButtonStyle(color=ft.Colors.ERROR))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    def show_rename_dialog(
        self,
        path,
        current_name: str,
        on_ai_suggest: Callable | None = None,
        on_confirm: Callable | None = None,
    ):
        """Show a rename dialog for a session.

        Args:
            path: Session path to rename.
            current_name: Current display name.
            on_ai_suggest: async callback() -> str | None — returns AI-suggested name.
            on_confirm: callback(path, new_name) — called when user confirms.
        """
        display_name = current_name if current_name != "Untitled Session" else ""
        rename_field = ft.TextField(
            label="Session name",
            value=display_name,
            autofocus=True,
            border_radius=12,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
            expand=True,
        )
        ai_loading = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

        async def _ai_suggest(e):
            if not on_ai_suggest:
                return
            ai_btn.disabled = True
            ai_loading.visible = True
            self.page.update()
            try:
                title = await on_ai_suggest(path)
                if title and title != "Untitled Session":
                    rename_field.value = title
            except Exception:
                pass
            finally:
                ai_btn.disabled = False
                ai_loading.visible = False
                self.page.update()

        ai_btn = ft.IconButton(
            icon=ft.Icons.AUTO_AWESOME,
            tooltip="AI suggest name",
            on_click=lambda e: self.page.run_task(_ai_suggest, e),
            icon_size=20,
        )

        def confirm(e):
            new_name = rename_field.value.strip()
            if new_name and on_confirm:
                on_confirm(path, new_name)
            self.page.pop_dialog()

        def cancel(e):
            self.page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text("Rename Session"),
            content=ft.Row(
                [rename_field, ai_loading, ai_btn],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                width=350,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.FilledButton("Save", on_click=confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)
