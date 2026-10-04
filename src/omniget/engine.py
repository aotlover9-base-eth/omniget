"""
Core media extraction and downloading engine powered by yt-dlp and ffmpeg.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import re
import urllib.request
from typing import Callable, List, Optional
import yt_dlp

from .models import Platform, DownloadMode, PostMetadata, DownloadProgress, detect_platform


def sanitize_filename(name: str) -> str:
    """Strip illegal filesystem characters."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:120] if clean else "download"


class MediaEngine:
    """Handles metadata extraction and asset downloading across platforms."""

    def __init__(self, default_output_dir: Optional[Path] = None):
        self.output_dir = default_output_dir or (Path.home() / "Downloads" / "omniget")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def inspect_post(self, url: str) -> PostMetadata:
        """
        Fast inspection of post metadata without downloading media.
        """
        platform = detect_platform(url)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                # If extraction failed, provide minimal metadata fallback
                return PostMetadata(
                    url=url,
                    platform=platform,
                    title="Social Post",
                    author=platform.display_name,
                    description=f"Error inspecting URL: {e}",
                    has_video=True,
                    has_audio=True,
                )

        if not info:
            return PostMetadata(
                url=url,
                platform=platform,
                title="Unknown Post",
                author="",
                description="",
            )

        title = info.get("title") or info.get("description") or "Untitled Post"
        author = info.get("uploader") or info.get("channel") or info.get("creator") or platform.display_name
        description = info.get("description") or ""
        duration = info.get("duration")
        thumbnail = info.get("thumbnail")
        view_count = info.get("view_count")
        like_count = info.get("like_count")

        # Collect available video resolutions
        resolutions = []
        formats = info.get("formats") or []
        for f in formats:
            height = f.get("height")
            if height and f"{height}p" not in resolutions:
                resolutions.append(f"{height}p")
        resolutions.sort(key=lambda x: int(x.replace("p", "")) if x.replace("p", "").isdigit() else 0, reverse=True)

        # Collect image URLs if present
        image_urls = []
        if thumbnail:
            image_urls.append(thumbnail)
        thumbnails = info.get("thumbnails") or []
        for t in thumbnails:
            u = t.get("url")
            if u and u not in image_urls:
                image_urls.append(u)

        has_video = bool(formats and any(f.get("vcodec") != "none" for f in formats))
        has_audio = bool(formats and any(f.get("acodec") != "none" for f in formats)) or bool(duration)

        return PostMetadata(
            url=url,
            platform=platform,
            title=title.strip()[:150],
            author=author,
            description=description.strip(),
            duration_seconds=duration,
            thumbnail_url=thumbnail,
            view_count=view_count,
            like_count=like_count,
            has_video=has_video,
            has_audio=has_audio,
            has_images=bool(image_urls),
            image_urls=image_urls,
            available_resolutions=resolutions[:5],
        )

    def download(
        self,
        url: str,
        mode: DownloadMode,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> Path:
        """
        Download media asset according to mode (VIDEO, AUDIO, IMAGES, TEXT, BUNDLE).
        """
        dest_dir = output_dir or self.output_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        cb = progress_callback or (lambda _: None)

        # 1. Mode: TEXT Only
        if mode == DownloadMode.TEXT:
            cb(DownloadProgress(status="inspecting", percent=10.0))
            meta = self.inspect_post(url)
            safe_name = sanitize_filename(meta.title)
            md_path = dest_dir / f"{safe_name}.md"

            content = (
                f"# {meta.title}\n\n"
                f"- **Platform**: {meta.platform.display_name}\n"
                f"- **Author**: {meta.author}\n"
                f"- **Source URL**: {meta.url}\n\n"
                f"## Post Content\n\n"
                f"{meta.description}\n"
            )
            md_path.write_text(content, encoding="utf-8")
            cb(DownloadProgress(status="finished", percent=100.0, filename=md_path.name))
            return md_path

        # 2. Mode: BUNDLE
        if mode == DownloadMode.BUNDLE:
            cb(DownloadProgress(status="inspecting", percent=5.0))
            meta = self.inspect_post(url)
            safe_folder_name = sanitize_filename(meta.title)
            bundle_dir = dest_dir / safe_folder_name
            bundle_dir.mkdir(parents=True, exist_ok=True)

            # Save Markdown caption
            md_path = bundle_dir / "caption.md"
            md_path.write_text(
                f"# {meta.title}\n\n"
                f"- **Author**: {meta.author}\n"
                f"- **Platform**: {meta.platform.display_name}\n"
                f"- **URL**: {meta.url}\n\n"
                f"### Caption\n\n{meta.description}\n",
                encoding="utf-8",
            )

            # Save media into bundle directory
            if meta.has_video:
                self.download(url, DownloadMode.VIDEO, output_dir=bundle_dir, progress_callback=cb)
            elif meta.has_images:
                self.download(url, DownloadMode.IMAGES, output_dir=bundle_dir, progress_callback=cb)

            cb(DownloadProgress(status="finished", percent=100.0, filename=bundle_dir.name))
            return bundle_dir

        # 3. Mode: IMAGES Only
        if mode == DownloadMode.IMAGES:
            cb(DownloadProgress(status="inspecting", percent=10.0))
            meta = self.inspect_post(url)
            safe_title = sanitize_filename(meta.title)

            downloaded = []
            for idx, img_url in enumerate(meta.image_urls[:8]):
                try:
                    ext = ".jpg"
                    if ".png" in img_url:
                        ext = ".png"
                    elif ".webp" in img_url:
                        ext = ".webp"

                    target_file = dest_dir / f"{safe_title}_{idx+1}{ext}"
                    req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req) as resp, open(target_file, "wb") as out_f:
                        out_f.write(resp.read())
                    downloaded.append(target_file)
                    pct = 10.0 + (idx + 1) / len(meta.image_urls[:8]) * 80.0
                    cb(DownloadProgress(status="downloading", percent=pct, filename=target_file.name))
                except Exception:
                    pass

            if downloaded:
                cb(DownloadProgress(status="finished", percent=100.0, filename=downloaded[0].name))
                return downloaded[0]
            else:
                # Fallback to normal yt-dlp thumbnail extraction
                pass

        # 4. Mode: VIDEO or AUDIO (yt-dlp)
        downloaded_file: Optional[Path] = None

        def ydl_hook(d):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded_b = d.get("downloaded_bytes", 0)
                pct = (downloaded_b / total * 100) if total else 0.0

                speed = d.get("speed") or 0
                speed_str = f"{speed / (1024*1024):.1f} MB/s" if speed else ""

                eta = d.get("eta") or 0
                eta_str = f"{eta}s" if eta else ""

                cb(DownloadProgress(
                    status="downloading",
                    percent=min(99.0, pct),
                    speed_str=speed_str,
                    eta_str=eta_str,
                    downloaded_bytes=downloaded_b,
                    total_bytes=total,
                    filename=os.path.basename(d.get("filename", "")),
                ))
            elif status == "finished":
                cb(DownloadProgress(
                    status="converting",
                    percent=99.0,
                    filename=os.path.basename(d.get("filename", "")),
                ))

        out_template = str(dest_dir / "%(title).100B-%(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [ydl_hook],
        }

        if mode == DownloadMode.AUDIO:
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else: # VIDEO
            ydl_opts.update({
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                # Find final saved filepath
                requested = info.get("requested_downloads")
                if requested and requested[0].get("filepath"):
                    downloaded_file = Path(requested[0]["filepath"])
                else:
                    # Look for prepared filename
                    raw_fn = ydl.prepare_filename(info)
                    if mode == DownloadMode.AUDIO:
                        base, _ = os.path.splitext(raw_fn)
                        downloaded_file = Path(f"{base}.mp3")
                    else:
                        base, _ = os.path.splitext(raw_fn)
                        mp4_candidate = Path(f"{base}.mp4")
                        downloaded_file = mp4_candidate if mp4_candidate.exists() else Path(raw_fn)

        final_path = downloaded_file or (dest_dir / "media.mp4")
        cb(DownloadProgress(
            status="finished",
            percent=100.0,
            filename=final_path.name,
        ))
        return final_path
