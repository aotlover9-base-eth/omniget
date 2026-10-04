"""
Main Textual Application for OmniGet.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Label, TabbedContent, TabPane

from ..clipboard import get_clipboard_text
from ..engine import MediaEngine
from ..history import HistoryManager
from .views_dl import DownloaderView
from .views_hist import HistoryView


CSS = """
Screen {
    background: #0d1117;
    color: #c9d1d9;
}

Header {
    background: #161b22;
    color: #58a6ff;
    dock: top;
    height: 3;
    content-align: center middle;
    text-style: bold;
    border-bottom: heavy #30363d;
}

Footer {
    background: #161b22;
    color: #8b949e;
    dock: bottom;
    height: 1;
}

.view-scroll {
    padding: 1 2;
    height: 1fr;
}

#platform-bar {
    height: 3;
    margin-bottom: 1;
    align: center middle;
}

.plat-btn {
    min-width: 13;
    margin-right: 1;
    background: #21262d;
    color: #e6edf3;
    border: tall #30363d;
}

.plat-btn:hover {
    background: #30363d;
    border: tall #58a6ff;
}

#url-bar {
    height: 3;
    margin-bottom: 1;
}

#input-url {
    width: 1fr;
    background: #161b22;
    border: tall #30363d;
    color: #58a6ff;
    margin-right: 1;
}

#input-url:focus {
    border: tall #58a6ff;
}

#btn-paste {
    min-width: 11;
    margin-right: 1;
    background: #21262d;
    color: #f0883e;
    border: tall #30363d;
}

#btn-paste:hover {
    background: #f0883e;
    color: #0d1117;
}

#btn-inspect {
    min-width: 12;
    background: #1f6feb;
    color: #ffffff;
    border: tall #388bfd;
}

#lbl-detected-platform {
    margin-bottom: 1;
    color: #8b949e;
}

#card-post-info {
    background: #161b22;
    border: round #30363d;
    padding: 1 2;
    margin-bottom: 1;
    min-height: 8;
}

.card-header {
    text-style: bold;
    color: #58a6ff;
    margin-bottom: 1;
}

#lbl-post-title {
    margin-bottom: 1;
    text-style: bold;
}

#lbl-post-meta {
    color: #8b949e;
    margin-bottom: 1;
}

#lbl-post-caption {
    color: #c9d1d9;
}

#card-download-modes {
    background: #161b22;
    border: round #30363d;
    padding: 1 2;
    margin-bottom: 1;
}

.section-title {
    text-style: bold;
    color: #e6edf3;
    margin-bottom: 1;
}

#mode-radios {
    background: transparent;
    border: none;
}

RadioButton {
    padding: 0 1;
    color: #c9d1d9;
}

RadioButton:focus {
    color: #58a6ff;
}

#action-bar {
    height: 3;
    margin-bottom: 1;
}

#btn-download {
    min-width: 22;
    margin-right: 2;
    background: #238636;
    color: #ffffff;
    border: tall #2ea043;
    text-style: bold;
}

#btn-download:hover {
    background: #2ea043;
}

#btn-bundle-all {
    min-width: 25;
    margin-right: 2;
    background: #8957e5;
    color: #ffffff;
    border: tall #a371f7;
    text-style: bold;
}

#btn-bundle-all:hover {
    background: #a371f7;
}

#btn-copy-caption {
    min-width: 17;
    margin-right: 1;
    background: #21262d;
    color: #bc8cff;
    border: tall #30363d;
}

#btn-copy-caption:hover {
    background: #bc8cff;
    color: #0d1117;
}

#btn-open-folder {
    min-width: 15;
    background: #21262d;
    color: #79c0ff;
    border: tall #30363d;
}

#progress-card {
    background: #161b22;
    border: round #30363d;
    padding: 1 2;
    margin-bottom: 1;
}

#dl-progress-bar {
    width: 100%;
    margin-bottom: 1;
}

#lbl-status {
    color: #8b949e;
}

/* History view styles */
.hist-container {
    padding: 1 2;
    height: 1fr;
}

#hist-header-bar {
    height: 3;
    align: left middle;
    margin-bottom: 1;
}

#lbl-hist-count {
    color: #8b949e;
    text-align: right;
}

#table-history {
    height: 1fr;
    background: #161b22;
    border: round #30363d;
    margin-bottom: 1;
}

#hist-actions {
    height: 3;
}

#hist-actions Button {
    margin-right: 1;
    min-width: 14;
}

TabbedContent {
    height: 1fr;
}

TabPane {
    height: 1fr;
    padding: 0;
}

Tabs {
    background: #161b22;
    border-bottom: solid #30363d;
}

Tab {
    color: #8b949e;
}

Tab.-active {
    color: #58a6ff;
    text-style: bold;
}
"""


class OmniGetApp(App):
    """OmniGet: Universal Social Post & Media Downloader TUI."""

    TITLE = "OmniGet"
    SUB_TITLE = "Universal Social Post & Media Downloader"
    CSS = CSS

    BINDINGS = [
        Binding("f1", "switch_tab('tab-dl')", "F1 Downloader", show=True, priority=True),
        Binding("f2", "switch_tab('tab-hist')", "F2 History", show=True, priority=True),
        Binding("ctrl+p", "paste_url", "Ctrl+P Paste", show=True, priority=True),
        Binding("ctrl+d", "start_download", "Ctrl+D Download", show=True, priority=True),
        Binding("ctrl+q", "quit", "Quit", show=True, priority=True),
        Binding("escape", "unfocus", "Unfocus", show=False, priority=True),
        Binding("1", "switch_tab('tab-dl')", "1 Downloader", show=False),
        Binding("2", "switch_tab('tab-hist')", "2 History", show=False),
        Binding("q", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        engine: Optional[MediaEngine] = None,
        history: Optional[HistoryManager] = None,
        initial_url: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.engine = engine or MediaEngine()
        self.history = history or HistoryManager()
        self.initial_url = initial_url

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-dl", id="tabs"):
            with TabPane("📥 Downloader", id="tab-dl"):
                yield DownloaderView(self.engine, self.history)
            with TabPane("📚 Download History", id="tab-hist"):
                yield HistoryView(self.history)
        yield Footer()

    def on_mount(self) -> None:
        if self.initial_url:
            dl_view = self.query_one(DownloaderView)
            inp = dl_view.query_one("#input-url")
            inp.value = self.initial_url
            dl_view.trigger_inspect()

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_unfocus(self) -> None:
        if self.focused:
            self.set_focus(None)

    def action_paste_url(self) -> None:
        self.action_switch_tab("tab-dl")
        dl_view = self.query_one(DownloaderView)
        clip_text = get_clipboard_text()
        if clip_text:
            inp = dl_view.query_one("#input-url")
            inp.value = clip_text
            self.notify("Pasted URL from clipboard", timeout=2)
            dl_view.trigger_inspect()
        else:
            self.notify("Clipboard is empty", severity="warning", timeout=2)

    def action_start_download(self) -> None:
        self.action_switch_tab("tab-dl")
        dl_view = self.query_one(DownloaderView)
        dl_view.trigger_download()

    def on_downloader_view_post_downloaded(self, event: DownloaderView.PostDownloaded) -> None:
        """When an item finishes downloading, refresh the history table."""
        try:
            hist_view = self.query_one(HistoryView)
            hist_view.refresh_table()
        except Exception:
            pass
