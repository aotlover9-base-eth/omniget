"""
Download history view for OmniGet TUI.
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
import subprocess
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Static

from ..history import HistoryManager
from ..models import HistoryItem


class HistoryView(Container):
    """Displays download history with 1-click open actions."""

    def __init__(self, history: HistoryManager) -> None:
        super().__init__()
        self.history = history
        self.selected_item_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="hist-container"):
            with Horizontal(id="hist-header-bar"):
                yield Label("📚 Recent Downloads Library", classes="card-header")
                yield Label("", id="lbl-hist-count")

            yield DataTable(id="table-history", cursor_type="row", zebra_stripes=True)

            with Horizontal(id="hist-actions"):
                yield Button("▶️ Open File", id="btn-hist-open", variant="primary")
                yield Button("📁 Open Folder", id="btn-hist-folder", variant="default")
                yield Button("🗑️ Remove Entry", id="btn-hist-remove", variant="warning")
                yield Button("🧹 Clear All", id="btn-hist-clear", variant="error")
                yield Button("🔄 Refresh", id="btn-hist-refresh", variant="default")

    def on_mount(self) -> None:
        table = self.query_one("#table-history", DataTable)
        table.add_columns("Time", "Platform", "Type", "Title", "Size", "File Location")
        self.refresh_table()

    def refresh_table(self) -> None:
        table = self.query_one("#table-history", DataTable)
        table.clear()
        items = self.history.get_items()

        lbl_count = self.query_one("#lbl-hist-count", Label)
        lbl_count.update(f"Total: {len(items)} items")

        plat_icons = {
            "youtube": "🔴 YouTube",
            "x": "𝕏 Twitter",
            "instagram": "📸 Instagram",
            "reddit": "🤖 Reddit",
            "facebook": "📘 Facebook",
            "generic": "🌐 Web",
        }

        for item in items:
            dt = datetime.fromtimestamp(item.timestamp).strftime("%m-%d %H:%M")
            plat = plat_icons.get(item.platform, item.platform)
            mode = item.mode.upper()
            title = (item.title[:45] + "...") if len(item.title) > 48 else item.title
            size = item.human_size
            path = item.file_path

            table.add_row(dt, plat, mode, title, size, path, key=item.id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value if hasattr(event.row_key, "value") else str(event.row_key)
        self.selected_item_id = row_key
        self.open_selected_file()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key:
            self.selected_item_id = event.row_key.value if hasattr(event.row_key, "value") else str(event.row_key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-hist-open":
            self.open_selected_file()
        elif bid == "btn-hist-folder":
            self.open_selected_folder()
        elif bid == "btn-hist-remove":
            self.remove_selected()
        elif bid == "btn-hist-clear":
            self.history.clear()
            self.refresh_table()
            self.notify("Cleared download history.", timeout=2)
        elif bid == "btn-hist-refresh":
            self.refresh_table()
            self.notify("History refreshed.", timeout=2)

    def _get_current_item(self) -> Optional[HistoryItem]:
        if not self.selected_item_id:
            table = self.query_one("#table-history", DataTable)
            if table.row_count > 0:
                row_key = table.get_row_at(table.cursor_row)
                # row_key from get_row_at returns list of cells; let's find by selected_item_id or cursor
                items = self.history.get_items()
                if 0 <= table.cursor_row < len(items):
                    return items[table.cursor_row]
            return None
        items = self.history.get_items()
        for i in items:
            if i.id == self.selected_item_id:
                return i
        return None

    def open_selected_file(self) -> None:
        item = self._get_current_item()
        if not item:
            self.notify("Select an item from history first!", severity="warning", timeout=2)
            return

        target = Path(item.file_path)
        if not target.exists():
            self.notify(f"File no longer exists: {target.name}", severity="error", timeout=3)
            return

        try:
            subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.notify(f"Opening: {target.name}", timeout=2)
        except Exception as e:
            self.notify(f"Failed to open file: {e}", severity="error", timeout=2)

    def open_selected_folder(self) -> None:
        item = self._get_current_item()
        if item:
            target = Path(item.file_path)
            folder = target.parent if target.is_file() else target
        else:
            folder = Path.home() / "Downloads" / "omniget"

        folder.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.notify(f"Opened folder: {folder.name}", timeout=2)
        except Exception as e:
            self.notify(f"Failed to open directory: {e}", severity="error", timeout=2)

    def remove_selected(self) -> None:
        item = self._get_current_item()
        if not item:
            self.notify("Select an item to remove!", severity="warning", timeout=2)
            return

        self.history.remove_item(item.id)
        self.selected_item_id = None
        self.refresh_table()
        self.notify("Removed item from history.", timeout=2)
