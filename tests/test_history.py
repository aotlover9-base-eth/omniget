import time
from omniget.history import HistoryManager
from omniget.models import HistoryItem


def test_history_crud(tmp_path):
    hist_file = tmp_path / "history.json"
    manager = HistoryManager(data_file=hist_file)

    assert manager.get_items() == []

    item1 = HistoryItem(
        id="item-1",
        title="Test Video 1",
        platform="youtube",
        mode="video",
        file_path=str(tmp_path / "video1.mp4"),
        timestamp=time.time(),
        size_bytes=1024 * 1024 * 5,  # 5 MB
    )
    manager.add_item(item1)

    items = manager.get_items()
    assert len(items) == 1
    assert items[0].id == "item-1"
    assert items[0].human_size == "5.0 MB"

    item2 = HistoryItem(
        id="item-2",
        title="Test Audio 2",
        platform="x",
        mode="audio",
        file_path=str(tmp_path / "audio2.mp3"),
        timestamp=time.time() + 10,
        size_bytes=512,  # 512 B
    )
    manager.add_item(item2)

    items = manager.get_items()
    assert len(items) == 2
    # newest item first
    assert items[0].id == "item-2"
    assert items[0].human_size == "512 B"

    # Remove single item
    manager.remove_item("item-1")
    items = manager.get_items()
    assert len(items) == 1
    assert items[0].id == "item-2"

    # Clear all
    manager.clear()
    assert manager.get_items() == []
