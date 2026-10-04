"""
Command line interface for OmniGet.
Provides a fast, responsive, and clear terminal TUI experience.
"""

from __future__ import annotations
import argparse
from pathlib import Path
import sys
import time
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .clipboard import get_clipboard_text
from .engine import MediaEngine
from .history import HistoryManager
from .models import DownloadMode, DownloadProgress, HistoryItem, Platform, detect_platform


def render_banner(console: Console) -> None:
    banner = (
        "[bold cyan]📥 OmniGet[/bold cyan] [dim]v0.1.0[/dim] - "
        "Universal Social Media Post & Media Downloader\n"
        "[dim]Supports YouTube, X (Twitter), Instagram, Reddit, Facebook & Web URLs[/dim]"
    )
    console.print(Panel(banner, border_style="blue"))


def cli_inspect(engine: MediaEngine, url: str, console: Console):
    plat = detect_platform(url)
    console.print(f"\n[bold yellow]🔍 Inspecting post:[/bold yellow] [underline]{url}[/underline]")
    console.print(f"[bold]Platform detected:[/bold] {plat.display_name}")

    with console.status("[cyan]Fetching post metadata...[/cyan]", spinner="dots"):
        meta = engine.inspect_post(url)

    table = Table(title="Post Summary", border_style="bright_blue", show_header=False)
    table.add_column("Property", style="bold cyan", width=18)
    table.add_column("Value", style="white")

    table.add_row("Title", meta.title)
    table.add_row("Author / Channel", meta.author or "Unknown")
    table.add_row("Platform", meta.platform.display_name)
    if meta.duration_seconds:
        table.add_row("Duration", meta.formatted_duration)
    if meta.available_resolutions:
        table.add_row("Video Resolutions", ", ".join(meta.available_resolutions))
    if meta.image_urls:
        table.add_row("Images Attached", f"{len(meta.image_urls)} photos")
    if meta.description:
        if meta.translation:
            table.add_row("Original Text", meta.description.strip())
            table.add_row("English Translation", meta.translation.strip())
        else:
            table.add_row("Caption / Text", meta.description.strip())

    console.print(table)
    return meta


def prompt_video_quality(meta: PostMetadata, console: Console) -> str:
    console.print("\n[bold]Select Video Resolution / Quality:[/bold]")
    options = [("1", "best", "⭐ Best Available (Maximum Quality) [bold][DEFAULT][/bold]")]

    standard_res = ["1080p", "720p", "480p", "360p"]
    available = [r for r in meta.available_resolutions if r in standard_res or r.endswith("p")]

    candidate_list = []
    for r in available:
        if r not in candidate_list:
            candidate_list.append(r)
    for r in standard_res:
        if r not in candidate_list:
            candidate_list.append(r)

    for idx, r in enumerate(candidate_list[:4], start=2):
        label = r
        if r == "1080p":
            label = f"{r} (Full HD)"
        elif r == "720p":
            label = f"{r} (HD)"
        elif r == "480p":
            label = f"{r} (Standard)"
        elif r == "360p":
            label = f"{r} (Data Saver)"
        options.append((str(idx), r, label))

    for key, val, desc in options:
        console.print(f"  [bold cyan][{key}][/bold cyan] {desc}")

    valid_keys = [opt[0] for opt in options]
    choice = Prompt.ask("\n[bold]Enter quality choice[/bold]", choices=valid_keys, default="1")
    for key, val, _ in options:
        if key == choice:
            return val
    return "best"


def cli_download(
    engine: MediaEngine,
    history: HistoryManager,
    url: str,
    mode: DownloadMode,
    output_dir: Path,
    console: Console,
    quality: Optional[str] = None,
) -> Path:
    plat = detect_platform(url)
    subfolder = engine.get_platform_subfolder(plat)
    dest_subfolder = output_dir / subfolder
    console.print(f"\n[bold cyan]📥 Starting download:[/bold cyan] {url}")
    quality_str = f"  •  [bold]Quality:[/bold] {quality}" if (quality and mode in (DownloadMode.VIDEO, DownloadMode.BUNDLE)) else ""
    console.print(f"[bold]Platform:[/bold] {plat.display_name}  •  [bold]Mode:[/bold] {mode.label}{quality_str}")
    console.print(f"[bold]Destination:[/bold] [dim]{dest_subfolder.resolve()}[/dim]\n")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=35),
        TextColumn("[bold green]{task.percentage:>3.0f}%[/bold green]"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    task_id = progress.add_task("Preparing download...", total=None)

    def on_progress(p: DownloadProgress):
        if p.status == "downloading":
            if p.total_bytes and p.total_bytes > 0:
                progress.update(
                    task_id,
                    completed=p.downloaded_bytes,
                    total=p.total_bytes,
                    description=f"Downloading {p.filename[:28]}..." if p.filename else "Downloading media...",
                )
            elif p.percent:
                progress.update(
                    task_id,
                    description=f"Downloading {p.filename[:28]}..." if p.filename else "Downloading...",
                )
        elif p.status == "converting":
            progress.update(task_id, description="[yellow]Processing & packaging into ZIP...[/yellow]")
        elif p.status == "inspecting":
            progress.update(task_id, description="[yellow]Inspecting target...[/yellow]")
        elif p.status == "finished":
            if progress.tasks[task_id].total:
                progress.update(task_id, completed=progress.tasks[task_id].total, description="[green]✓ Complete[/green]")
            else:
                progress.update(task_id, description="[green]✓ Complete[/green]")

    with progress:
        saved_path = engine.download(
            url=url,
            mode=mode,
            quality=quality,
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

    item = HistoryItem(
        id=str(uuid.uuid4())[:8],
        title=saved_path.name,
        platform=plat.value,
        mode=mode.value,
        file_path=str(saved_path.resolve()),
        timestamp=time.time(),
        size_bytes=size_b,
    )
    history.add_item(item)

    panel_content = (
        f"[bold green]✔ Download Complete![/bold green]\n\n"
        f"[bold]Saved File:[/bold] [underline cyan]{saved_path}[/underline cyan]\n"
        f"[bold]Size:[/bold] {item.human_size}  •  [bold]Mode:[/bold] {mode.label}\n\n"
        f"[dim]Folder: {saved_path.parent}[/dim]"
    )
    console.print(Panel(panel_content, border_style="green"))
    return saved_path


def cli_history(history: HistoryManager, console: Console) -> None:
    items = history.get_items()
    if not items:
        console.print("[yellow]No download history found.[/yellow]")
        return

    table = Table(title="OmniGet Download Library", border_style="bright_blue")
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


def interactive_tui(engine: MediaEngine, history: HistoryManager, initial_url: str | None, console: Console) -> None:
    render_banner(console)

    url = initial_url
    if not url:
        # Check clipboard automatically
        clip = get_clipboard_text()
        if clip and (clip.startswith("http://") or clip.startswith("https://")):
            console.print(f"[dim]📋 Found link in clipboard:[/dim] [bold cyan]{clip}[/bold cyan]")
            use_clip = Confirm.ask("Download this link?", default=True)
            if use_clip:
                url = clip

    if not url:
        url = Prompt.ask("\n[bold yellow]Paste social post URL[/bold yellow] (YouTube, X, Instagram, Reddit, Facebook)")

    url = url.strip()
    if not url:
        console.print("[red]No URL provided. Exiting.[/red]")
        return

    # Inspect post
    meta = cli_inspect(engine, url, console)

    # Prompt user for mode
    console.print("\n[bold]Select Download Option:[/bold]")
    console.print("  [bold green][1] 📦 Bundle Everything (.zip)[/bold green] [dim](Video + Audio + Images + Post Text into ZIP)[/dim] [bold][DEFAULT][/bold]")

    if meta.has_video:
        res_info = f" [dim]({meta.available_resolutions[0]} available)[/dim]" if meta.available_resolutions else ""
        console.print(f"  [bold cyan][2] 🎬 Video (Select Quality){res_info}[/bold cyan]")
    else:
        console.print("  [dim][2] 🎬 Video (No video stream detected)[/dim]")

    if meta.has_audio:
        console.print("  [bold magenta][3] 🎵 Audio Only (HQ MP3)[/bold magenta]")
    else:
        console.print("  [dim][3] 🎵 Audio Only (No audio track)[/dim]")

    if meta.image_urls:
        img_label = f"{len(meta.image_urls)} photo{'s' if len(meta.image_urls) > 1 else ''} attached"
        console.print(f"  [bold yellow][4] 🖼️ Gallery Images ({img_label})[/bold yellow]")
    elif meta.thumbnail_url:
        console.print("  [bold yellow][4] 🖼️ Post Thumbnail / Cover (1 image)[/bold yellow]")
    else:
        console.print("  [dim][4] 🖼️ Gallery Images (No photos found)[/dim]")

    console.print("  [bold blue][5] 📝 Post Text / Captions (post.txt & caption.md)[/bold blue]")

    default_choice = "1"
    if not meta.has_video and meta.image_urls:
        default_choice = "4"

    choice = Prompt.ask("\n[bold]Enter choice [1-5][/bold]", choices=["1", "2", "3", "4", "5"], default=default_choice)

    mode_map = {
        "1": DownloadMode.BUNDLE,
        "2": DownloadMode.VIDEO,
        "3": DownloadMode.AUDIO,
        "4": DownloadMode.IMAGES,
        "5": DownloadMode.TEXT,
    }
    mode = mode_map.get(choice, DownloadMode.BUNDLE)

    quality: Optional[str] = None
    if mode == DownloadMode.VIDEO and meta.has_video:
        quality = prompt_video_quality(meta, console)

    dest_dir = engine.output_dir
    cli_download(engine, history, url, mode, dest_dir, console, quality=quality)


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
        "-b", "--bundle",
        action="store_true",
        help="Bundle Everything into a ZIP archive (Video + Audio + Images + Text)",
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
        help="Save post caption & text content as plain text and Markdown",
    )
    parser.add_argument(
        "-i", "--inspect",
        action="store_true",
        help="Inspect and display post metadata without downloading",
    )
    parser.add_argument(
        "-q", "--quality",
        type=str,
        default=None,
        help="Select video quality/resolution (e.g. 1080p, 720p, 480p, 360p, best)",
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

    # 3. Headless Download Modes via flags
    has_headless_flag = any([args.video, args.audio, args.images, args.text, args.bundle])

    if has_headless_flag:
        if not args.url:
            console.print("[red]Error: Download flags require a URL argument.[/red]")
            sys.exit(1)

        mode = DownloadMode.BUNDLE
        if args.video:
            mode = DownloadMode.VIDEO
        elif args.audio:
            mode = DownloadMode.AUDIO
        elif args.images:
            mode = DownloadMode.IMAGES
        elif args.text:
            mode = DownloadMode.TEXT
        elif args.bundle:
            mode = DownloadMode.BUNDLE

        render_banner(console)
        cli_download(engine, history, args.url, mode, dest_dir, console, quality=args.quality)
        return

    # 5. Default: Fast Interactive Terminal TUI
    interactive_tui(engine, history, args.url, console)


if __name__ == "__main__":
    main()
