"""
Data models and Enums for OmniGet.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import List, Optional
from urllib.parse import urlparse


class Platform(str, Enum):
    YOUTUBE = "youtube"
    TWITTER = "x"
    INSTAGRAM = "instagram"
    REDDIT = "reddit"
    FACEBOOK = "facebook"
    GENERIC = "generic"

    @property
    def display_name(self) -> str:
        names = {
            Platform.YOUTUBE: "🔴 YouTube",
            Platform.TWITTER: "𝕏 Twitter / X",
            Platform.INSTAGRAM: "📸 Instagram",
            Platform.REDDIT: "🤖 Reddit",
            Platform.FACEBOOK: "📘 Facebook",
            Platform.GENERIC: "🌐 Web Link",
        }
        return names.get(self, "🌐 Link")


class DownloadMode(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGES = "images"
    TEXT = "text"
    BUNDLE = "bundle"

    @property
    def label(self) -> str:
        labels = {
            DownloadMode.VIDEO: "🎬 Best Video (MP4)",
            DownloadMode.AUDIO: "🎵 Audio Only (MP3)",
            DownloadMode.IMAGES: "🖼️ Gallery / Images",
            DownloadMode.TEXT: "📝 Post Text / Caption",
            DownloadMode.BUNDLE: "📦 Bundle Everything (.zip)",
        }
        return labels.get(self, self.value)


@dataclass
class PostMetadata:
    url: str
    platform: Platform
    title: str
    author: str
    description: str
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    has_video: bool = False
    has_audio: bool = False
    has_images: bool = False
    image_urls: List[str] = field(default_factory=list)
    available_resolutions: List[str] = field(default_factory=list)

    @property
    def formatted_duration(self) -> str:
        if not self.duration_seconds:
            return "Post"
        total_secs = int(round(float(self.duration_seconds)))
        mins, secs = divmod(total_secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"


@dataclass
class DownloadProgress:
    status: str = "idle" # idle, inspecting, downloading, converting, finished, error
    percent: float = 0.0
    speed_str: str = ""
    eta_str: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    filename: str = ""
    error_message: str = ""


@dataclass
class HistoryItem:
    id: str
    title: str
    platform: str
    mode: str
    file_path: str
    timestamp: float
    size_bytes: int

    @property
    def human_size(self) -> str:
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{size:.1f} TB"


def detect_platform(url: str) -> Platform:
    """Detect platform enum from URL domain pattern."""
    if not url:
        return Platform.GENERIC
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        parsed = urlparse(u)
        netloc = parsed.netloc.lower()
        netloc = netloc.split(":")[0]
    except Exception:
        netloc = ""

    if any(netloc == d or netloc.endswith("." + d) for d in ("youtube.com", "youtu.be")):
        return Platform.YOUTUBE
    if any(netloc == d or netloc.endswith("." + d) for d in ("twitter.com", "x.com", "t.co")):
        return Platform.TWITTER
    if any(netloc == d or netloc.endswith("." + d) for d in ("instagram.com", "instagr.am")):
        return Platform.INSTAGRAM
    if any(netloc == d or netloc.endswith("." + d) for d in ("reddit.com", "redd.it")):
        return Platform.REDDIT
    if any(netloc == d or netloc.endswith("." + d) for d in ("facebook.com", "fb.watch", "fb.com")):
        return Platform.FACEBOOK
    return Platform.GENERIC
