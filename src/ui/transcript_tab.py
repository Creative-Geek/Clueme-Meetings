"""Transcript tab — live scrolling transcript display with copy/export."""

from typing import Callable

import flet as ft


class TranscriptTab(ft.Column):
    """Live transcript display with confirmed + tentative segments."""

    def __init__(self):
        super().__init__(expand=True)

        self._last_displayed_minute: int = -1
        self._is_near_bottom: bool = True  # smart scroll state
        self._scroll_pending: bool = False

        # External callback: returns formatted transcript text string
        self._get_text: Callable[[], str] | None = None
        # External callbacks set by main.py
        self._on_copy: Callable[[], None] | None = None
        self._on_export: Callable[[], None] | None = None

        self._copy_btn = ft.IconButton(
            icon=ft.Icons.COPY_OUTLINED,
            tooltip="Copy transcript",
            on_click=lambda e: e.page.run_task(self._handle_copy),
            icon_size=18,
        )
        self._export_btn = ft.IconButton(
            icon=ft.Icons.SAVE_ALT_OUTLINED,
            tooltip="Export as .txt",
            on_click=lambda e: e.page.run_task(self._handle_export),
            icon_size=18,
        )

        self._toolbar = ft.Row(
            controls=[
                ft.Container(expand=True),
                self._copy_btn,
                self._export_btn,
            ],
            alignment=ft.MainAxisAlignment.END,
            height=32,
        )

        self._tentative_text = ft.Text(
            "",
            italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
            size=14,
        )

        self._list = ft.ListView(
            expand=True,
            spacing=4,
            padding=ft.Padding.all(16),
            on_scroll=self._on_scroll,
        )

        self._export_picker = ft.FilePicker()

        self.controls = [
            self._toolbar,
            ft.Container(
                content=self._list,
                expand=True,
                border_radius=12,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                padding=0,
            ),
        ]

    def did_mount(self):
        """Register the file picker service when the control mounts."""
        self.page.services.append(self._export_picker)

    # ── Smart scroll ────────────────────────────────────────────

    def _on_scroll(self, e: ft.OnScrollEvent):
        """Track whether the user is near the bottom of the list."""
        event_str = getattr(e.event_type, "value", e.event_type)
        if event_str in ("start", "user", "update"):
            self._is_near_bottom = (e.max_scroll_extent - e.pixels) < 80

    def _auto_scroll_if_needed(self):
        """Scroll to bottom only if the user was already near the bottom."""
        if self._is_near_bottom and self.page and not self._scroll_pending:
            self._scroll_pending = True
            async def _scroll():
                try:
                    await self._list.scroll_to(offset=-1, duration=150)
                except Exception:
                    pass
                finally:
                    self._scroll_pending = False
            self.page.run_task(_scroll)

    def scroll_to_bottom(self):
        """Force scroll to the bottom (e.g. on tab switch)."""
        self._is_near_bottom = True
        if self.page:
            async def _scroll():
                await self._list.scroll_to(offset=-1, duration=150)
            self.page.run_task(_scroll)

    def add_confirmed(self, text: str, minute: int):
        """Add a confirmed (locked-in) transcript segment."""
        # Remove tentative from list if present
        if self._tentative_text in self._list.controls:
            self._list.controls.remove(self._tentative_text)

        # Insert minute marker if new minute
        if minute > self._last_displayed_minute:
            self._last_displayed_minute = minute
            import time as _time
            t = _time.localtime(minute * 60)
            label = f"  {t.tm_hour:02d}:{t.tm_min:02d}"
            self._list.controls.append(
                ft.Text(
                    label,
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                    weight=ft.FontWeight.W_500,
                )
            )

        self._list.controls.append(
            ft.Text(
                text,
                size=14,
                selectable=True,
            )
        )

        # Re-add tentative at the end
        self._tentative_text.value = ""
        self._list.controls.append(self._tentative_text)
        self._auto_scroll_if_needed()

    def set_tentative(self, text: str):
        """Update the tentative (in-progress) text at the bottom."""
        self._tentative_text.value = text
        if self._tentative_text not in self._list.controls:
            self._list.controls.append(self._tentative_text)
        self._auto_scroll_if_needed()

    def clear(self):
        """Clear all transcript content."""
        self._list.controls.clear()
        self._tentative_text.value = ""
        self._last_displayed_minute = -1
        self._is_near_bottom = True

    # ── Copy & export ─────────────────────────────────────────────

    async def _handle_copy(self):
        """Copy transcript text to clipboard."""
        if self._on_copy:
            await self._on_copy()
            return
        # Built-in: use _get_text callback
        if not self._get_text:
            return
        text = self._get_text()
        if not text:
            return
        clipboard = ft.Clipboard()
        self.page.services.append(clipboard)
        await clipboard.set(text)
        snack = ft.SnackBar(content=ft.Text("Transcript copied to clipboard"))
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    async def _handle_export(self):
        """Export transcript text to a .txt file."""
        if self._on_export:
            await self._on_export()
            return
        # Built-in: use _get_text callback
        if not self._get_text:
            return
        text = self._get_text()
        if not text:
            return
        path = await self._export_picker.save_file(
            dialog_title="Export transcript",
            file_name="transcript.txt",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt"],
        )
        if not path:
            return
        if not path.endswith(".txt"):
            path += ".txt"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            snack = ft.SnackBar(content=ft.Text(f"Exported to {path}"))
            self.page.overlay.append(snack)
            snack.open = True
            self.page.update()
        except OSError as exc:
            snack = ft.SnackBar(content=ft.Text(f"Export failed: {exc}"))
            self.page.overlay.append(snack)
            snack.open = True
            self.page.update()
