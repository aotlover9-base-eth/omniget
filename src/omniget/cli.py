"""
Command line interface for OmniGet.
"""

from __future__ import annotations
import argparse
from pathlib import Path
import sys
import time
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.table import Table

from .engine import MediaEngine
from .history import HistoryManager
from .models import DownloadMode, DownloadProgress, HistoryItem, Platform, detect_platform


def render_banner(console: Console) -> None:
    banner = (
        "[bold cyan]📥 OmniGet[/bold cyan] [dim]v0.1.0[/dim] - "
        "Universal Social Media Post & Media Downloader\n"
        "[dim]Supports YouTube, X, Instagram, Reddit, Facebook & Web URLs[/dim]"
    )
    console.print(Panel(banner, border_style="blue"))


def cli_inspect(engine: MediaEngine, url: str, console: Console) -> None:
    plat = detect_platform(url)
    console.print(f"\n[bold yellow]🔍 Inspecting post:[/bold yellow] {url}")
    console.print(f"[bold]Platform detected:[/bold] {plat.display_name}")

    with console.status("[cyan]Fetching post metadata...[/cyan]", spinner="dots"):
        meta = engine.inspect_post(url)

    table = Table(title="Post Metadata", border_style="bright_blue", show_header=False)
    table.add_column("Property", style="bold cyan", width=18)
    table.add_column("Value", style="white")

    table.add_row("Title", meta.title)
    table.add_row("Author / Channel", meta.author or "Unknown")
    table.add_row("Platform", meta.platform.display_name)
    if meta.duration_seconds:
        table.add_row("Duration", meta.formatted_duration)
    if meta.available_resolutions:
        table.add_row("Resolutions", ", ".join(meta.available_resolutions))
    if meta.image_urls:
        table.add_row("Images Count", str(len(meta.image_urls)))
    if meta.description:
        desc_snippet = meta.description.strip()
        if len(desc_snippet) > 300:
            desc_snippet = desc_snippet[:300] + "..."
        table.add_row("Caption Preview", desc_snippet)

    console.print(table)


def cli_download(
    engine: MediaEngine,
    history: HistoryManager,
    url: str,
    mode: DownloadMode,
    output_dir: Path,
    console: Console,
) -> None:
    plat = detect_platform(url)
    console.print(f"\n[bold cyan]📥 Starting download:[/bold cyan] {url}")
    console.print(f"[bold]Platform:[/bold] {plat.display_name}  •  [bold]Mode:[/bold] {mode.label}")
    console.print(f"[bold]Destination:[/bold] {output_dir.resolve()}")

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    task_id = progress.add_task("Downloading...", total=100)

    def on_progress(p: DownloadProgress):
        if p.total_bytes and p.total_bytes > 0:
            progress.update(task_id, completed=p.downloaded_bytes, total=p.total_bytes)
        else:
            progress.update(task_id, completed=p.percent, total=100)

        if p.status == "converting":
            progress.update(task_id, description="[yellow]Converting media with ffmpeg...[/yellow]")
        elif p.status == "inspecting":
            progress.update(task_id, description="[yellow]Inspecting target...[/yellow]")

    with progress:
        saved_path = engine.download(
            url=url,
            mode=mode,
            output_dir=output_dir,
            progress_callback=on_progress,
        )

    # Save to history
    size_b = 0
    if saved_path.exists():
        if saved_path.is_file():
            size_b = saved_path.stat().st_size
        elif saved_path.is_dir():
            size_b = sum(f.stat().st_size for f in saved_path.glob("**/*") if f.is_file())

    history.add_item(
        HistoryItem(
            id=str(uuid.uuid4())[:8],
            title=saved_path.name,
            platform=plat.value,
            mode=mode.value,
            file_path=str(saved_path.resolve()),
            timestamp=time.time(),
            size_bytes=size_b,
        )
    )

    console.print(f"[bold green]✓ Download finished:[/bold green] [underline]{saved_path}[/underline]")


def cli_history(history: HistoryManager, console: Console) -> None:
    items = history.get_items()
    if not items:
        console.print("[yellow]No download history found.[/yellow]")
        return

    table = Table(title="OmniGet Download History", border_style="bright_blue")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Platform", style="cyan", width=14)
    table.add_column("Mode", style="magenta", width=10)
    table.add_column("Title", style="white", min_width=25)
    table.add_column("Size", style="green", width=10)
    table.add_column("File Path", style="dim")

    for item in items:
        table.add_row(
            item.id,
            item.platform.upper(),
            item.mode.upper(),
            item.title[:40],
            item.human_size,
            item.file_path,
        )

    console.print(table)


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="omniget",
        description="OmniGet: Universal Social Post & Media Downloader (TUI & CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Social post or media URL to download or inspect",
    )

    parser.add_argument(
        "-v", "--video",
        action="store_true",
        help="Download best MP4 video with audio",
    )
    parser.add_argument(
        "-a", "--audio",
        action="store_true",
        help="Download audio only (HQ MP3)",
    )
    parser.add_argument(
        "--images",
        action="store_true",
        help="Download gallery photos or post images",
    )
    parser.add_argument(
        "-t", "--text",
        action="store_true",
        help="Save post caption & text content as Markdown",
    )
    parser.add_argument(
        "-b", "--bundle",
        action="store_true",
        help="Download full post bundle (Media + Captions + Metadata)",
    )
    parser.add_argument(
        "-i", "--inspect",
        action="store_true",
        help="Inspect and display post metadata without downloading",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Custom output directory (default: ~/Downloads/omniget)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Display recent download history",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Force launch interactive TUI mode",
    )

    args = parser.parse_args(argv)

    console = Console()
    dest_dir = args.output_dir or (Path.home() / "Downloads" / "omniget")
    engine = MediaEngine(default_output_dir=dest_dir)
    history = HistoryManager()

    # 1. History flag
    if args.history:
        render_banner(console)
        cli_history(history, console)
        return

    # 2. Inspect flag
    if args.inspect:
        if not args.url:
            console.print("[red]Error: --inspect requires a URL argument.[/red]")
            sys.exit(1)
        render_banner(console)
        cli_inspect(engine, args.url, console)
        return

    # 3. Headless Download Modes
    has_headless_flag = any([args.video, args.audio, args.images, args.text, args.bundle])

    if has_headless_flag:
        if not args.url:
            console.print("[red]Error: Download flags require a URL argument.[/red]")
            sys.exit(1)

        mode = DownloadMode.VIDEO
        if args.audio:
            mode = DownloadMode.AUDIO
        elif args.images:
            mode = DownloadMode.IMAGES
        elif args.text:
            mode = DownloadMode.TEXT
        elif args.bundle:
            mode = DownloadMode.BUNDLE

        render_banner(console)
        cli_download(engine, history, args.url, mode, dest_dir, console)
        return

    # 4. Interactive TUI mode
    from .tui.app import OmniGetApp
    app = OmniGetApp(engine=engine, history=history, initial_url=args.url)
    app.run()


if __name__ == "__main__":
    main()
