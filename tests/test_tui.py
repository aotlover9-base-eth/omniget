import pytest
from omniget.tui.app import OmniGetApp
from omniget.tui.views_dl import DownloaderView
from omniget.tui.views_hist import HistoryView
from omniget.engine import MediaEngine
from omniget.history import HistoryManager
from textual.widgets import Input, Label, RadioButton


@pytest.mark.asyncio
async def test_app_composition_and_tabs(tmp_path):
    engine = MediaEngine(default_output_dir=tmp_path)
    history = HistoryManager(data_file=tmp_path / "hist.json")
    app = OmniGetApp(engine=engine, history=history)

    async with app.run_test() as pilot:
        # Check views mounted
        assert app.query_one(DownloaderView) is not None
        assert app.query_one(HistoryView) is not None

        # Check Tab switching via keys
        await pilot.press("f2")
        await pilot.pause()
        assert app.query_one("#tabs").active == "tab-hist"

        await pilot.press("f1")
        await pilot.pause()
        assert app.query_one("#tabs").active == "tab-dl"


@pytest.mark.asyncio
async def test_tui_platform_detection_badge(tmp_path):
    engine = MediaEngine(default_output_dir=tmp_path)
    history = HistoryManager(data_file=tmp_path / "hist.json")
    app = OmniGetApp(engine=engine, history=history)

    async with app.run_test() as pilot:
        inp = app.query_one("#input-url", Input)
        badge = app.query_one("#lbl-detected-platform", Label)

        inp.value = "https://x.com/someuser/status/123"
        await pilot.pause()
        assert "Twitter" in str(badge.render()) or "X" in str(badge.render())

        inp.value = "https://www.youtube.com/watch?v=sample"
        await pilot.pause()
        assert "YouTube" in str(badge.render())

        inp.value = "https://www.reddit.com/r/technology/comments/sample"
        await pilot.pause()
        assert "Reddit" in str(badge.render())
