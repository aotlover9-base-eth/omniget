"""
Downloader view for OmniGet TUI.
"""

from __future__ import annotations
from pathlib import Path
import subprocess
import time
import uuid
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import (
    Button,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    Static,
)

from ..clipboard import copy_clipboard_text, get_clipboard_text
from ..engine import MediaEngine
from ..history import HistoryManager
from ..models import DownloadMode, DownloadProgress, HistoryItem, Platform, detect_platform


class DownloaderView(Container):
    """Main downloader tab allowing inspection and asset extraction."""

    class PostDownloaded(Message):
        """Notification when a post asset was downloaded."""
        def __init__(self, item: HistoryItem) -> None:
            super().__init__()
            self.item = item

    def __init__(self, engine: MediaEngine, history: HistoryManager) -> None:
        super().__init__()
        self.engine = engine
        self.history = history
        self.current_meta = None
        self.is_downloading = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="view-scroll"):
            # 1. Platform Chooser Filter
            with Horizontal(id="platform-bar"):
                yield Button("🔴 YouTube", id="btn-plat-youtube", classes="plat-btn")
                yield Button("𝕏 Twitter/X", id="btn-plat-twitter", classes="plat-btn")
                yield Button("📸 Instagram", id="btn-plat-instagram", classes="plat-btn")
                yield Button("🤖 Reddit", id="btn-plat-reddit", classes="plat-btn")
                yield Button("📘 Facebook", id="btn-plat-facebook", classes="plat-btn")
                yield Button("🌐 All / Generic", id="btn-plat-generic", classes="plat-btn")

            # 2. URL Input Bar
            with Horizontal(id="url-bar"):
                yield Input(
                    placeholder="Enter or paste social post URL (YouTube, X, Instagram, Reddit, Facebook)...",
                    id="input-url",
                )
                yield Button("📋 Paste", id="btn-paste", variant="default")
                yield Button("🔍 Inspect", id="btn-inspect", variant="primary")

            # 3. Platform Detection Indicator
            yield Label("Detected Platform: [dim]None (Enter a URL above)[/dim]", id="lbl-detected-platform")

            # 4. Post Info Card (Initially placeholder)
            with Vertical(id="card-post-info"):
                yield Label("📌 Post Details", classes="card-header")
                yield Label("[dim]Ready. Enter a post URL and click 'Inspect' to preview formats.[/dim]", id="lbl-post-title")
                yield Label("", id="lbl-post-meta")
                yield Label("", id="lbl-post-caption")

            # 5. Format & Asset Picker
            with Vertical(id="card-download-modes"):
                yield Label("📦 Choose Asset to Download:", classes="section-title")
                with RadioSet(id="mode-radios"):
                    yield RadioButton("🎬 Video (Best MP4 with Audio)", id="mode-video", value=True)
                    yield RadioButton("🎵 Audio Only (MP3 192kbps)", id="mode-audio")
                    yield RadioButton("🖼️ Gallery Images / Photos", id="mode-images")
                    yield RadioButton("📝 Post Caption / Markdown Notes", id="mode-text")
                    yield RadioButton("📦 Bundle Everything (Video + Audio + Images + Post Text -> .zip)", id="mode-bundle")

            # 6. Action Bar
            with Horizontal(id="action-bar"):
                yield Button("⬇️ Download Selected", id="btn-download", variant="success")
                yield Button("📦 Bundle Everything (.zip)", id="btn-bundle-all", variant="primary")
                yield Button("📋 Copy Caption", id="btn-copy-caption", variant="default")
                yield Button("📁 Open Folder", id="btn-open-folder", variant="default")

            # 7. Live Download Progress Area
            with Vertical(id="progress-card"):
                yield ProgressBar(id="dl-progress-bar", total=100, show_eta=True)
                yield Label("Status: Idle", id="lbl-status")

    def on_mount(self) -> None:
        self.query_one("#input-url", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update platform badge dynamically as user types."""
        url = event.value.strip()
        lbl = self.query_one("#lbl-detected-platform", Label)
        if not url:
            lbl.update("Detected Platform: [dim]None (Enter a URL above)[/dim]")
            return

        plat = detect_platform(url)
        lbl.update(f"Detected Platform: [bold cyan]{plat.display_name}[/bold cyan]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Inspect when Enter key is pressed in the input bar."""
        self.trigger_inspect()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "btn-paste":
            clip_text = get_clipboard_text()
            if clip_text:
                inp = self.query_one("#input-url", Input)
                inp.value = clip_text
                self.notify("Pasted URL from clipboard", timeout=2)
                self.trigger_inspect()
            else:
                self.notify("Clipboard is empty or not text", severity="warning", timeout=2)

        elif button_id == "btn-inspect":
            self.trigger_inspect()

        elif button_id == "btn-download":
            self.trigger_download()

        elif button_id == "btn-bundle-all":
            radios = self.query_one("#mode-radios", RadioSet)
            radios.query_one("#mode-bundle", RadioButton).value = True
            self.trigger_download(forced_mode=DownloadMode.BUNDLE)

        elif button_id == "btn-copy-caption":
            if self.current_meta and self.current_meta.description:
                if copy_clipboard_text(self.current_meta.description):
                    self.notify("Caption copied to clipboard!", timeout=2)
                else:
                    self.notify("Failed to copy to clipboard", severity="error", timeout=2)
            else:
                self.notify("No post caption to copy. Inspect a post first.", severity="warning", timeout=2)

        elif button_id == "btn-open-folder":
            self.open_output_dir()

        elif button_id and button_id.startswith("btn-plat-"):
            plat_name = button_id.replace("btn-plat-", "")
            examples = {
                "youtube": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "twitter": "https://x.com/karpathy/status/1760000000000000000",
                "instagram": "https://www.instagram.com/reel/C3_sample/",
                "reddit": "https://www.reddit.com/r/technology/comments/sample/",
                "facebook": "https://www.facebook.com/watch/?v=sample",
                "generic": "https://example.com/video.mp4",
            }
            inp = self.query_one("#input-url", Input)
            if not inp.value.strip() and plat_name in examples:
                inp.placeholder = f"Paste {plat_name.capitalize()} URL, e.g. {examples[plat_name]}"

    def trigger_inspect(self) -> None:
        url = self.query_one("#input-url", Input).value.strip()
        if not url:
            self.notify("Please enter a valid URL first!", severity="warning", timeout=2)
            return

        lbl_title = self.query_one("#lbl-post-title", Label)
        lbl_meta = self.query_one("#lbl-post-meta", Label)
        lbl_caption = self.query_one("#lbl-post-caption", Label)
        lbl_status = self.query_one("#lbl-status", Label)

        lbl_title.update(f"[bold yellow]🔍 Inspecting post...[/bold yellow]")
        lbl_meta.update("[dim]Querying metadata and available resolutions...[/dim]")
        lbl_caption.update("")
        lbl_status.update("Status: [yellow]Inspecting post metadata...[/yellow]")

        self.worker_inspect(url)

    @work(exclusive=True, thread=True)
    def worker_inspect(self, url: str) -> None:
        try:
            meta = self.engine.inspect_post(url)
            self.app.call_from_thread(self._finish_inspect, meta)
        except Exception as e:
            self.app.call_from_thread(self._error_inspect, str(e))

    def _finish_inspect(self, meta) -> None:
        self.current_meta = meta
        lbl_title = self.query_one("#lbl-post-title", Label)
        lbl_meta = self.query_one("#lbl-post-meta", Label)
        lbl_caption = self.query_one("#lbl-post-caption", Label)
        lbl_status = self.query_one("#lbl-status", Label)

        lbl_title.update(f"[bold green]Title:[/bold green] {meta.title}")

        meta_parts = [
            f"[bold]Author:[/bold] {meta.author or 'Unknown'}",
            f"[bold]Platform:[/bold] {meta.platform.display_name}",
        ]
        if meta.duration_seconds:
            meta_parts.append(f"[bold]Duration:[/bold] {meta.formatted_duration}")
        if meta.available_resolutions:
            meta_parts.append(f"[bold]Resolutions:[/bold] {', '.join(meta.available_resolutions)}")
        if meta.image_urls:
            meta_parts.append(f"[bold]Images:[/bold] {len(meta.image_urls)}")

        lbl_meta.update("  •  ".join(meta_parts))

        # Caption snippet preview (up to 220 chars)
        if meta.description:
            snippet = meta.description.strip()
            if len(snippet) > 220:
                snippet = snippet[:220] + "..."
            lbl_caption.update(f"[bold cyan]Caption Snippet:[/bold cyan] [italic]{snippet}[/italic]")
        else:
            lbl_caption.update("[dim](No text caption attached to this post)[/dim]")

        # Auto-recommend format based on content
        radios = self.query_one("#mode-radios", RadioSet)
        if meta.has_video:
            radios.query_one("#mode-video", RadioButton).value = True
        elif meta.has_images:
            radios.query_one("#mode-images", RadioButton).value = True
        elif meta.description:
            radios.query_one("#mode-text", RadioButton).value = True

        lbl_status.update("Status: [green]Post inspected. Ready to download![/green]")
        self.notify("Post details loaded!", timeout=2)

    def _error_inspect(self, error: str) -> None:
        lbl_title = self.query_one("#lbl-post-title", Label)
        lbl_status = self.query_one("#lbl-status", Label)
        lbl_title.update(f"[bold red]Inspection Failed[/bold red]")
        lbl_status.update(f"Status: [red]Error: {error}[/red]")
        self.notify(f"Inspection error: {error}", severity="error", timeout=4)

    def trigger_download(self, forced_mode: Optional[DownloadMode] = None) -> None:
        if self.is_downloading:
            self.notify("Download already in progress!", severity="warning", timeout=2)
            return

        url = self.query_one("#input-url", Input).value.strip()
        if not url:
            self.notify("Please enter a URL to download!", severity="warning", timeout=2)
            return

        if forced_mode:
            mode = forced_mode
        else:
            radios = self.query_one("#mode-radios", RadioSet)
            pressed = radios.pressed_button
            button_id = pressed.id if pressed else "mode-video"

            mode_map = {
                "mode-video": DownloadMode.VIDEO,
                "mode-audio": DownloadMode.AUDIO,
                "mode-images": DownloadMode.IMAGES,
                "mode-text": DownloadMode.TEXT,
                "mode-bundle": DownloadMode.BUNDLE,
            }
            mode = mode_map.get(button_id, DownloadMode.VIDEO)

        self.is_downloading = True
        btn_dl = self.query_one("#btn-download", Button)
        btn_dl.disabled = True
        btn_bundle = self.query_one("#btn-bundle-all", Button)
        btn_bundle.disabled = True
        pbar = self.query_one("#dl-progress-bar", ProgressBar)
        pbar.progress = 0

        self.worker_download(url, mode)

    @work(exclusive=True, thread=True)
    def worker_download(self, url: str, mode: DownloadMode) -> None:
        start_time = time.time()
        try:
            def on_progress(p: DownloadProgress):
                self.app.call_from_thread(self._update_progress, p)

            saved_path = self.engine.download(url, mode, progress_callback=on_progress)
            
            # Save history entry
            size_b = 0
            if saved_path.exists():
                if saved_path.is_file():
                    size_b = saved_path.stat().st_size
                elif saved_path.is_dir():
                    size_b = sum(f.stat().st_size for f in saved_path.glob("**/*") if f.is_file())

            title = self.current_meta.title if self.current_meta else saved_path.name
            plat = detect_platform(url)

            history_item = HistoryItem(
                id=str(uuid.uuid4())[:8],
                title=title,
                platform=plat.value,
                mode=mode.value,
                file_path=str(saved_path.resolve()),
                timestamp=time.time(),
                size_bytes=size_b,
            )
            self.history.add_item(history_item)

            self.app.call_from_thread(self._finish_download, saved_path, history_item)
        except Exception as e:
            self.app.call_from_thread(self._error_download, str(e))

    def _update_progress(self, p: DownloadProgress) -> None:
        pbar = self.query_one("#dl-progress-bar", ProgressBar)
        lbl_status = self.query_one("#lbl-status", Label)

        pbar.progress = p.percent
        if p.status == "downloading":
            detail = f"{p.speed_str} • ETA: {p.eta_str}" if p.speed_str else ""
            lbl_status.update(f"Status: [cyan]Downloading ({p.percent:.1f}%)...[/cyan] {detail} [dim]{p.filename}[/dim]")
        elif p.status == "converting":
            lbl_status.update("Status: [yellow]Converting & merging audio/video with ffmpeg...[/yellow]")
        elif p.status == "inspecting":
            lbl_status.update("Status: [yellow]Inspecting target...[/yellow]")
        elif p.status == "finished":
            lbl_status.update(f"Status: [green]Completed: {p.filename}[/green]")

    def _finish_download(self, saved_path: Path, item: HistoryItem) -> None:
        self.is_downloading = False
        btn_dl = self.query_one("#btn-download", Button)
        btn_dl.disabled = False
        btn_bundle = self.query_one("#btn-bundle-all", Button)
        btn_bundle.disabled = False

        pbar = self.query_one("#dl-progress-bar", ProgressBar)
        pbar.progress = 100

        lbl_status = self.query_one("#lbl-status", Label)
        lbl_status.update(f"Status: [bold green]Downloaded successfully![/bold green] -> [italic]{saved_path.name}[/italic]")

        self.notify(f"Saved: {saved_path.name}", title="Download Complete", timeout=4)
        self.post_message(self.PostDownloaded(item))

    def _error_download(self, error: str) -> None:
        self.is_downloading = False
        btn_dl = self.query_one("#btn-download", Button)
        btn_dl.disabled = False
        btn_bundle = self.query_one("#btn-bundle-all", Button)
        btn_bundle.disabled = False

        lbl_status = self.query_one("#lbl-status", Label)
        lbl_status.update(f"Status: [bold red]Download failed: {error}[/bold red]")
        self.notify(f"Download failed: {error}", severity="error", timeout=5)

    def open_output_dir(self) -> None:
        folder = self.engine.output_dir
        folder.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.notify(f"Opened folder: {folder}", timeout=2)
        except Exception as e:
            self.notify(f"Could not open folder: {e}", severity="error", timeout=2)
