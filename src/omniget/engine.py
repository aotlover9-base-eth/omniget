"""
Core media extraction and downloading engine powered by yt-dlp and ffmpeg.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from typing import Callable, List, Optional
import yt_dlp

from .models import Platform, DownloadMode, PostMetadata, DownloadProgress, detect_platform


def is_ffmpeg_installed() -> bool:
    """Check if ffmpeg executable is present in system PATH."""
    return shutil.which("ffmpeg") is not None


_UNSHORTEN_CACHE: dict[str, str] = {}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler)


def unshorten_url(url: str, timeout: float = 2.5) -> str:
    """Expand shortened URL (such as t.co) to full visible destination URL."""
    if not url:
        return url
    if url in _UNSHORTEN_CACHE:
        return _UNSHORTEN_CACHE[url]

    resolved = url
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
        )
        req.get_method = lambda: "HEAD"
        with _NO_REDIRECT_OPENER.open(req, timeout=timeout) as resp:
            loc = resp.headers.get("Location")
            if loc:
                resolved = loc
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            loc = e.headers.get("Location")
            if loc:
                resolved = loc
    except Exception:
        pass

    _UNSHORTEN_CACHE[url] = resolved
    return resolved


def unshorten_text_urls(text: str) -> str:
    """Replace all t.co shortened links in text with their full destination URLs."""
    if not text:
        return ""
    return re.sub(r"https?://t\.co/[a-zA-Z0-9]+", lambda m: unshorten_url(m.group(0)), text)


def is_likely_non_english(text: str, lang: str = "") -> bool:
    """Check if text is in a non-English language."""
    if lang and lang.lower() not in ("en", "und", ""):
        return True
    cjk_or_non_latin = re.search(
        r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff\u0900-\u097f]",
        text,
    )
    return bool(cjk_or_non_latin)


def translate_to_english_fallback(text: str) -> Optional[str]:
    """Free translation fallback if service did not provide translation."""
    if not text.strip():
        return None
    try:
        sample = text.strip()[:500]
        encoded = urllib.parse.quote(sample)
        url = f"https://api.mymemory.translated.net/get?q={encoded}&langpair=autodetect|en"
        req = urllib.request.Request(url, headers={"User-Agent": "omniget/0.1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            match = data.get("responseData", {}).get("translatedText")
            if match and match.strip() and match.strip().lower() != sample.lower():
                return match.strip()
    except Exception:
        pass
    return None


def sanitize_filename(name: str) -> str:
    """Strip illegal filesystem characters."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:120] if clean else "download"


PLATFORM_SUBFOLDERS = {
    Platform.TWITTER: "x",
    Platform.YOUTUBE: "youtube",
    Platform.INSTAGRAM: "instagram",
    Platform.REDDIT: "reddit",
    Platform.FACEBOOK: "facebook",
    Platform.GENERIC: "other",
}

PLATFORM_PREFIXES = {
    Platform.TWITTER: "tweet",
    Platform.YOUTUBE: "youtube",
    Platform.INSTAGRAM: "instagram",
    Platform.REDDIT: "reddit",
    Platform.FACEBOOK: "facebook",
    Platform.GENERIC: "media",
}


def get_next_sequence_name(dest_dir: Path, prefix: str) -> str:
    """
    Find the next available sequential entity name in dest_dir for a given prefix.
    E.g. if 'tweet 1.zip' or directory 'tweet 1' exists, returns 'tweet 2'.
    """
    if not dest_dir.exists():
        return f"{prefix} 1"

    pattern = re.compile(rf"^{re.escape(prefix)}[ _](\d+)(?:[._].*)?$", re.IGNORECASE)
    existing_indices: list[int] = []

    try:
        for entry in dest_dir.iterdir():
            m = pattern.match(entry.name)
            if m:
                try:
                    existing_indices.append(int(m.group(1)))
                except ValueError:
                    pass
    except Exception:
        pass

    next_idx = max(existing_indices, default=0) + 1
    return f"{prefix} {next_idx}"


def upgrade_image_url(url: str) -> str:
    """Upgrade preview/thumbnail URLs to full uncompressed quality."""
    if not url:
        return url
    # Twitter / X original high-res image
    if "twimg.com" in url:
        if "name=" in url:
            url = re.sub(r"name=[a-zA-Z0-9_]+", "name=orig", url)
        else:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}name=orig"
    # YouTube maximum resolution thumbnail
    elif "ytimg.com" in url:
        for low_res in ("hqdefault.jpg", "mqdefault.jpg", "default.jpg", "sddefault.jpg"):
            if low_res in url:
                url = url.replace(low_res, "maxresdefault.jpg")
                break
    # Reddit preview to original i.redd.it
    elif "preview.redd.it" in url:
        url = url.replace("preview.redd.it", "i.redd.it").split("?")[0]
    return url


def deduplicate_image_urls(urls: List[str]) -> List[str]:
    """
    Deduplicate image URLs.
    Removes low-res variants and avatars while preserving unique original images.
    """
    seen_bases = set()
    result = []
    for u in urls:
        if not u:
            continue
        # Filter profile avatars and UI icons
        if any(bad in u.lower() for bad in ("profile_images", "user_avatar", "default_avatar", "favicon", "emoji")):
            continue
        upgraded = upgrade_image_url(u)
        base_key = upgraded.split("?")[0]
        if base_key not in seen_bases:
            seen_bases.add(base_key)
            result.append(upgraded)
    return result


def fetch_twitter_fallback(url: str) -> Optional[PostMetadata]:
    """
    Extract Twitter / X metadata via FxTwitter API v2 / v1.
    Provides complete untruncated post text, unshortened URLs,
    high-res photos, videos, and English translation.
    """
    m = re.search(r"status/(\d+)", url)
    if not m:
        return None
    tid = m.group(1)

    tweet = None
    # 1. Try FxTwitter API v2 with English translation query
    try:
        req_v2 = urllib.request.Request(
            f"https://api.fxtwitter.com/2/status/{tid}?lang=en",
            headers={"User-Agent": "omniget/0.1.0 (Linux; x86_64)"},
        )
        with urllib.request.urlopen(req_v2, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and (data.get("code") == 200 or "status" in data):
                tweet = data.get("status") or data.get("tweet")
    except Exception:
        tweet = None

    # 2. Fallback to v1 endpoint
    if not tweet:
        try:
            req_v1 = urllib.request.Request(
                f"https://api.fxtwitter.com/status/{tid}/en",
                headers={"User-Agent": "omniget/0.1.0 (Linux; x86_64)"},
            )
            with urllib.request.urlopen(req_v1, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and data.get("code") == 200:
                    tweet = data.get("tweet")
        except Exception:
            tweet = None

    if not tweet:
        return None

    try:
        author_data = tweet.get("author") or {}
        author = author_data.get("name") or author_data.get("screen_name") or "𝕏 Twitter / X"
        raw_text = tweet.get("text") or ""
        # Unshorten any t.co links in original tweet text
        desc = unshorten_text_urls(raw_text)
        title = f"{author}: {desc[:60]}..." if desc else f"{author}'s Post"

        # Translation extraction
        trans_data = tweet.get("translation") or {}
        trans_text = trans_data.get("text") or ""
        source_lang = trans_data.get("source_lang") or tweet.get("lang") or ""

        if trans_text:
            trans_text = unshorten_text_urls(trans_text)
        elif is_likely_non_english(desc, source_lang):
            fallback = translate_to_english_fallback(desc)
            if fallback:
                trans_text = fallback

        translation = trans_text if (trans_text and trans_text.strip().lower() != desc.strip().lower()) else None

        media = tweet.get("media") or {}
        photos = media.get("photos") or []
        videos = media.get("videos") or []

        image_urls = []
        for p in photos:
            pu = p.get("url")
            if pu:
                image_urls.append(upgrade_image_url(pu))

        has_video = bool(videos)
        has_audio = False
        resolutions = []
        if has_video:
            v = videos[0]
            has_audio = True
            for f in v.get("formats") or v.get("variants") or []:
                h = f.get("height")
                if h and f"{h}p" not in resolutions:
                    resolutions.append(f"{h}p")
            if not resolutions:
                resolutions = ["720p"]
            if not image_urls and v.get("thumbnail_url"):
                image_urls.append(upgrade_image_url(v["thumbnail_url"]))

        deduped = deduplicate_image_urls(image_urls)
        return PostMetadata(
            url=url,
            platform=Platform.TWITTER,
            title=title[:120],
            author=author,
            description=desc,
            has_video=has_video,
            has_audio=has_audio,
            has_images=bool(deduped),
            image_urls=deduped,
            available_resolutions=resolutions,
            translation=translation,
            source_language=source_lang or None,
        )
    except Exception:
        return None


def fetch_reddit_fallback(url: str) -> Optional[PostMetadata]:
    """
    Extract Reddit post metadata via Pullpush API or OEmbed fallback.
    Handles situations where Reddit returns 403 Blocked to standard requests.
    """
    m = re.search(r"comments/([a-zA-Z0-9]+)", url)
    sub_id = m.group(1) if m else None

    # 1. Try Pullpush API
    if sub_id:
        try:
            req = urllib.request.Request(
                f"https://api.pullpush.io/reddit/submission/search?ids={sub_id}",
                headers={"User-Agent": "omniget/0.1.0"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("data") or []
                if items:
                    item = items[0]
                    title = item.get("title") or "Reddit Post"
                    author = f"u/{item.get('author')}" if item.get("author") else "Reddit User"
                    desc = item.get("selftext") or ""
                    post_url = item.get("url") or ""
                    is_video = bool(item.get("is_video")) or "v.redd.it" in post_url

                    image_urls = []
                    if "i.redd.it" in post_url or any(post_url.lower().endswith(ext) for ext in (".jpg", ".png", ".webp", ".gif")):
                        image_urls.append(post_url)

                    return PostMetadata(
                        url=url,
                        platform=Platform.REDDIT,
                        title=title[:120],
                        author=author,
                        description=desc,
                        has_video=is_video,
                        has_audio=is_video,
                        has_images=bool(image_urls),
                        image_urls=deduplicate_image_urls(image_urls),
                        available_resolutions=["720p"] if is_video else [],
                    )
        except Exception:
            pass

    # 2. Try Reddit OEmbed
    try:
        oembed_url = f"https://www.reddit.com/oembed?url={urllib.parse.quote(url)}"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and data.get("title"):
                return PostMetadata(
                    url=url,
                    platform=Platform.REDDIT,
                    title=data["title"][:120],
                    author=f"u/{data.get('author_name', 'Reddit User')}",
                    description="",
                    has_video=False,
                    has_audio=False,
                    has_images=False,
                )
    except Exception:
        pass

    return None


def fetch_opengraph_fallback(url: str, platform: Platform) -> Optional[PostMetadata]:
    """Extract OpenGraph metadata from web page HTML as universal fallback."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

            title_m = re.search(r"<meta\s+property=[\"']og:title[\"']\s+content=[\"']([^\"']+)[\"']", html, re.I)
            if not title_m:
                title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
            title = title_m.group(1).strip() if title_m else "Web Post"

            desc_m = re.search(r"<meta\s+property=[\"']og:description[\"']\s+content=[\"']([^\"']+)[\"']", html, re.I)
            desc = desc_m.group(1).strip() if desc_m else ""

            img_m = re.search(r"<meta\s+property=[\"']og:image[\"']\s+content=[\"']([^\"']+)[\"']", html, re.I)
            img_url = img_m.group(1).strip() if img_m else None

            video_m = re.search(r"<meta\s+property=[\"']og:video[\"']\s+content=[\"']([^\"']+)[\"']", html, re.I)
            has_video = bool(video_m)

            site_m = re.search(r"<meta\s+property=[\"']og:site_name[\"']\s+content=[\"']([^\"']+)[\"']", html, re.I)
            author = site_m.group(1).strip() if site_m else platform.display_name

            imgs = [img_url] if img_url else []
            return PostMetadata(
                url=url,
                platform=platform,
                title=title[:120],
                author=author,
                description=desc,
                has_video=has_video,
                has_audio=has_video,
                has_images=bool(imgs),
                image_urls=deduplicate_image_urls(imgs),
            )
    except Exception:
        return None


class MediaEngine:
    """Handles metadata extraction and asset downloading across platforms."""

    def __init__(self, default_output_dir: Optional[Path] = None):
        self.output_dir = default_output_dir or (Path.home() / "Downloads" / "omniget")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_platform_subfolder(platform: Platform) -> str:
        return PLATFORM_SUBFOLDERS.get(platform, "other")

    @staticmethod
    def get_platform_prefix(platform: Platform) -> str:
        return PLATFORM_PREFIXES.get(platform, "media")

    def inspect_post(self, url: str) -> PostMetadata:
        """
        Fast inspection of post metadata with multi-tier fallback architecture.
        """
        platform = detect_platform(url)

        class QuietLogger:
            def debug(self, msg): pass
            def info(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): pass

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "skip_download": True,
            "extract_flat": False,
            "logger": QuietLogger(),
        }

        info = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            info = None

        if info:
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

            # Collect raw image URLs if present
            raw_image_urls = []
            if thumbnail:
                raw_image_urls.append(thumbnail)

            # For YouTube, video thumbnail is the only image (ignore storyboard seek frames)
            if platform != Platform.YOUTUBE:
                for t in info.get("thumbnails") or []:
                    tu = t.get("url")
                    if tu:
                        raw_image_urls.append(tu)

            # Check entries for carousels / multi-image posts
            for entry in info.get("entries") or []:
                if not entry:
                    continue
                entry_thumb = entry.get("thumbnail") or entry.get("url")
                if entry_thumb:
                    raw_image_urls.append(entry_thumb)
                for t in entry.get("thumbnails") or []:
                    tu = t.get("url")
                    if tu:
                        raw_image_urls.append(tu)

            # If Twitter/X, fetch full untruncated text, translation, and photos via FxTwitter
            tw_meta = None
            if platform == Platform.TWITTER:
                tw_meta = fetch_twitter_fallback(url)
                if tw_meta:
                    if tw_meta.description:
                        description = tw_meta.description
                    if tw_meta.title:
                        title = tw_meta.title
                    if tw_meta.author:
                        author = tw_meta.author
                    if tw_meta.image_urls:
                        raw_image_urls = tw_meta.image_urls

            deduped_images = deduplicate_image_urls(raw_image_urls)
            has_video = bool(formats and any(f.get("vcodec") not in (None, "none") for f in formats))
            has_audio = bool(formats and any(f.get("acodec") not in (None, "none") for f in formats))

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
                has_images=bool(deduped_images),
                image_urls=deduped_images,
                available_resolutions=resolutions[:5],
                translation=tw_meta.translation if tw_meta else None,
                source_language=tw_meta.source_language if tw_meta else None,
            )

        # Fallbacks when yt-dlp extraction fails
        if platform == Platform.TWITTER:
            tw_meta = fetch_twitter_fallback(url)
            if tw_meta:
                return tw_meta

        if platform == Platform.REDDIT:
            red_meta = fetch_reddit_fallback(url)
            if red_meta:
                return red_meta

        # Universal OpenGraph fallback
        og_meta = fetch_opengraph_fallback(url, platform)
        if og_meta:
            return og_meta

        # Minimal safe fallback
        return PostMetadata(
            url=url,
            platform=platform,
            title="Social Post",
            author=platform.display_name,
            description=f"Media link: {url}",
            has_video=False,
            has_audio=False,
            has_images=False,
        )

    def download(
        self,
        url: str,
        mode: DownloadMode,
        quality: Optional[str] = None,
        output_dir: Optional[Path] = None,
        resolve_platform_subfolder: bool = True,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> Path:
        """
        Download media asset according to mode (VIDEO, AUDIO, IMAGES, TEXT, BUNDLE).
        Organizes files into platform-specific subfolders (e.g. ~/Downloads/omniget/x/)
        and applies clean sequential naming (e.g. tweet 1, tweet 2) for folders and zips.
        """
        platform = detect_platform(url)
        subfolder = self.get_platform_subfolder(platform)
        if resolve_platform_subfolder:
            dest_dir = (output_dir or self.output_dir) / subfolder
        else:
            dest_dir = output_dir or self.output_dir

        dest_dir.mkdir(parents=True, exist_ok=True)
        cb = progress_callback or (lambda _: None)
        prefix = self.get_platform_prefix(platform)

        # Check ffmpeg before attempting video/audio downloads
        if mode in (DownloadMode.VIDEO, DownloadMode.AUDIO):
            if not is_ffmpeg_installed():
                cb(DownloadProgress(status="error", error_message="FFmpeg is not installed."))
                raise RuntimeError(
                    "FFmpeg is not installed on this system. "
                    "Please install FFmpeg (e.g. 'sudo apt install ffmpeg' or 'brew install ffmpeg') "
                    "to process video and audio."
                )

        # 1. Mode: TEXT Only
        if mode == DownloadMode.TEXT:
            cb(DownloadProgress(status="inspecting", percent=10.0))
            meta = self.inspect_post(url)
            seq_name = get_next_sequence_name(dest_dir, prefix)
            md_path = dest_dir / f"{seq_name}.md"

            content = (
                f"# {meta.title}\n\n"
                f"- **Platform**: {meta.platform.display_name}\n"
                f"- **Author**: {meta.author}\n"
                f"- **Source URL**: {meta.url}\n\n"
                f"## Original Post\n\n"
                f"{meta.description}\n"
            )
            if meta.translation:
                content += f"\n## English Translation\n\n{meta.translation}\n"

            md_path.write_text(content, encoding="utf-8")
            cb(DownloadProgress(status="finished", percent=100.0, filename=md_path.name))
            return md_path

        # 2. Mode: BUNDLE (Bundle Everything: Video + Audio + Images + Post Text -> .zip)
        if mode == DownloadMode.BUNDLE:
            cb(DownloadProgress(status="inspecting", percent=5.0))
            meta = self.inspect_post(url)
            seq_name = get_next_sequence_name(dest_dir, prefix)
            bundle_dir = dest_dir / seq_name
            bundle_dir.mkdir(parents=True, exist_ok=True)

            # 2a. Convert post to plain .txt (Original language text + English translation)
            txt_path = bundle_dir / "post.txt"
            txt_content = (
                f"Title: {meta.title}\n"
                f"Author: {meta.author}\n"
                f"Platform: {meta.platform.display_name}\n"
                f"Source URL: {meta.url}\n\n"
                f"--- Original Post ---\n"
                f"{meta.description}\n"
            )
            if meta.translation:
                txt_content += (
                    f"\n--- English Translation ---\n"
                    f"{meta.translation}\n"
                )
            txt_path.write_text(txt_content, encoding="utf-8")

            # 2b. Save Markdown caption
            md_path = bundle_dir / "caption.md"
            md_content = (
                f"# {meta.title}\n\n"
                f"- **Author**: {meta.author}\n"
                f"- **Platform**: {meta.platform.display_name}\n"
                f"- **Source URL**: {meta.url}\n\n"
                f"### Original Post\n\n{meta.description}\n"
            )
            if meta.translation:
                md_content += f"\n### English Translation\n\n{meta.translation}\n"
            md_path.write_text(md_content, encoding="utf-8")

            # 2c. Save Metadata JSON
            meta_path = bundle_dir / "metadata.json"
            meta_dict = {
                "title": meta.title,
                "author": meta.author,
                "platform": meta.platform.value,
                "url": meta.url,
                "duration_seconds": meta.duration_seconds,
                "view_count": meta.view_count,
                "like_count": meta.like_count,
                "available_resolutions": meta.available_resolutions,
                "image_urls": meta.image_urls,
                "description": meta.description,
                "translation": meta.translation,
                "source_language": meta.source_language,
            }
            meta_path.write_text(json.dumps(meta_dict, indent=2), encoding="utf-8")

            cb(DownloadProgress(status="downloading", percent=15.0, filename="saved post text & metadata"))

            # 2d. Download Video if post has video
            if meta.has_video:
                cb(DownloadProgress(status="downloading", percent=20.0, filename="downloading video..."))
                try:
                    self.download(url, DownloadMode.VIDEO, quality=quality, output_dir=bundle_dir, resolve_platform_subfolder=False, progress_callback=cb)
                except Exception:
                    pass

            # 2e. Download Audio (MP3) only if post actually has an audio track
            if meta.has_audio:
                cb(DownloadProgress(status="downloading", percent=50.0, filename="extracting audio (MP3)..."))
                try:
                    self.download(url, DownloadMode.AUDIO, output_dir=bundle_dir, resolve_platform_subfolder=False, progress_callback=cb)
                except Exception:
                    pass

            # 2f. Download ALL Images if present
            if meta.image_urls:
                cb(DownloadProgress(status="downloading", percent=70.0, filename="downloading all images..."))
                for idx, raw_url in enumerate(meta.image_urls):
                    img_url = upgrade_image_url(raw_url)
                    try:
                        ext = ".jpg"
                        if ".png" in img_url.lower():
                            ext = ".png"
                        elif ".webp" in img_url.lower():
                            ext = ".webp"
                        target_file = bundle_dir / f"image_{idx+1}{ext}"
                        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
                        with urllib.request.urlopen(req, timeout=20) as resp, open(target_file, "wb") as out_f:
                            out_f.write(resp.read())
                    except Exception:
                        pass

            # 2g. Bundle into ZIP archive
            cb(DownloadProgress(status="converting", percent=92.0, filename="zipping bundle archive..."))
            zip_path = dest_dir / f"{seq_name}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in bundle_dir.rglob("*"):
                    if file_path.is_file() and file_path != zip_path:
                        zf.write(file_path, arcname=f"{seq_name}/{file_path.relative_to(bundle_dir)}")

            cb(DownloadProgress(status="finished", percent=100.0, filename=zip_path.name))
            return zip_path

        # 3. Mode: IMAGES Only
        if mode == DownloadMode.IMAGES:
            cb(DownloadProgress(status="inspecting", percent=10.0))
            meta = self.inspect_post(url)
            seq_name = get_next_sequence_name(dest_dir, prefix)

            # Ensure we have target images, fallback to thumbnail if none
            images_to_download = list(meta.image_urls)
            if not images_to_download and meta.thumbnail_url:
                images_to_download.append(meta.thumbnail_url)

            # Dedicated folder if multiple images, otherwise dest_dir
            img_dir = dest_dir / seq_name if len(images_to_download) > 1 else dest_dir
            img_dir.mkdir(parents=True, exist_ok=True)

            downloaded = []
            total_imgs = max(1, len(images_to_download))
            for idx, raw_url in enumerate(images_to_download):
                img_url = upgrade_image_url(raw_url)
                try:
                    ext = ".jpg"
                    if ".png" in img_url.lower():
                        ext = ".png"
                    elif ".webp" in img_url.lower():
                        ext = ".webp"

                    target_file = img_dir / f"{seq_name}_{idx+1}{ext}" if len(images_to_download) == 1 else img_dir / f"image_{idx+1}{ext}"
                    req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
                    with urllib.request.urlopen(req, timeout=20) as resp, open(target_file, "wb") as out_f:
                        out_f.write(resp.read())
                    downloaded.append(target_file)
                    pct = 10.0 + (idx + 1) / total_imgs * 85.0
                    cb(DownloadProgress(status="downloading", percent=pct, filename=target_file.name))
                except Exception:
                    pass

            if downloaded:
                cb(DownloadProgress(status="finished", percent=100.0, filename=downloaded[0].name))
                return img_dir if len(downloaded) > 1 else downloaded[0]
            else:
                cb(DownloadProgress(status="finished", percent=100.0, filename="No images found"))
                return dest_dir

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

        if not resolve_platform_subfolder:
            item_prefix = "audio" if mode == DownloadMode.AUDIO else "video"
            out_template = str(dest_dir / f"{item_prefix}.%(ext)s")
        else:
            out_template = str(dest_dir / "%(title).100B-%(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
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
            if quality and quality.lower() != "best":
                h = quality.lower().replace("p", "").strip()
                if h.isdigit():
                    ydl_opts.update({
                        "format": f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/best[height<={h}]/best",
                        "merge_output_format": "mp4",
                    })
                else:
                    ydl_opts.update({
                        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                        "merge_output_format": "mp4",
                    })
            else:
                ydl_opts.update({
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                    "merge_output_format": "mp4",
                })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                requested = info.get("requested_downloads")
                if requested and requested[0].get("filepath"):
                    downloaded_file = Path(requested[0]["filepath"])
                else:
                    raw_fn = ydl.prepare_filename(info)
                    if mode == DownloadMode.AUDIO:
                        base, _ = os.path.splitext(raw_fn)
                        downloaded_file = Path(f"{base}.mp3")
                    else:
                        base, _ = os.path.splitext(raw_fn)
                        mp4_candidate = Path(f"{base}.mp4")
                        downloaded_file = mp4_candidate if mp4_candidate.exists() else Path(raw_fn)

        final_path = downloaded_file or (dest_dir / ("audio.mp3" if mode == DownloadMode.AUDIO else "media.mp4"))
        cb(DownloadProgress(
            status="finished",
            percent=100.0,
            filename=final_path.name,
        ))
        return final_path
