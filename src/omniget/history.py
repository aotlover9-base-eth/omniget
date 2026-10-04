"""
Persistent download history store for OmniGet.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import time
from typing import List, Optional

from .models import HistoryItem


class HistoryManager:
    """Manages history records saved in ~/.local/share/omniget/history.json."""

    def __init__(self, data_file: Optional[Path] = None):
        if data_file:
            self.file_path = data_file
        else:
            data_dir = Path.home() / ".local" / "share" / "omniget"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.file_path = data_dir / "history.json"

    def get_items(self) -> List[HistoryItem]:
        """Read all history items ordered by newest first."""
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                items = [HistoryItem(**d) for d in raw]
                items.sort(key=lambda x: x.timestamp, reverse=True)
                return items
        except Exception:
            return []

    def add_item(self, item: HistoryItem) -> None:
        """Add new item to history."""
        items = self.get_items()
        # Filter duplicates by file_path
        items = [i for i in items if i.file_path != item.file_path]
        items.insert(0, item)
        # Cap at 100 items
        items = items[:100]
        self._save(items)

    def remove_item(self, item_id: str) -> None:
        """Remove item by ID."""
        items = [i for i in self.get_items() if i.id != item_id]
        self._save(items)

    def clear(self) -> None:
        """Clear all history."""
        self._save([])

    def _save(self, items: List[HistoryItem]) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                raw = [i.__dict__ for i in items]
                json.dump(raw, f, indent=2)
        except Exception:
            pass
