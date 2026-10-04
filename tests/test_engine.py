from pathlib import Path
from unittest.mock import MagicMock, patch
from omniget.engine import MediaEngine, sanitize_filename
from omniget.models import DownloadMode, Platform, PostMetadata


def test_sanitize_filename():
    assert sanitize_filename("hello/world:test*cool?.mp4") == "helloworldtestcool.mp4"
    assert sanitize_filename("   Multiple    Spaces   ") == "Multiple Spaces"
    assert sanitize_filename("") == "download"


def test_download_mode_labels():
    assert "Video" in DownloadMode.VIDEO.label
    assert "Audio" in DownloadMode.AUDIO.label
    assert "Images" in DownloadMode.IMAGES.label
    assert "Caption" in DownloadMode.TEXT.label
    assert "Bundle" in DownloadMode.BUNDLE.label


def test_download_text_mode(tmp_path):
    engine = MediaEngine(default_output_dir=tmp_path)

    mock_meta = PostMetadata(
        url="https://x.com/example/status/123",
        platform=Platform.TWITTER,
        title="Insightful Tweet",
        author="@researcher",
        description="This is the post content text that should be saved into markdown.",
    )

    with patch.object(engine, "inspect_post", return_value=mock_meta):
        saved_file = engine.download(
            url="https://x.com/example/status/123",
            mode=DownloadMode.TEXT,
            output_dir=tmp_path,
        )

        assert saved_file.exists()
        assert saved_file.suffix == ".md"
        content = saved_file.read_text(encoding="utf-8")
        assert "Insightful Tweet" in content
        assert "@researcher" in content
        assert "This is the post content text" in content


def test_download_bundle_everything(tmp_path):
    import zipfile
    engine = MediaEngine(default_output_dir=tmp_path)

    mock_meta = PostMetadata(
        url="https://x.com/researcher/status/987654",
        platform=Platform.TWITTER,
        title="Complete AI Announcement",
        author="@researcher",
        description="Here is the full text of our new model release with attached benchmark.",
        has_video=False,
        has_audio=False,
        has_images=False,
    )

    with patch.object(engine, "inspect_post", return_value=mock_meta):
        zip_path = engine.download(
            url="https://x.com/researcher/status/987654",
            mode=DownloadMode.BUNDLE,
            output_dir=tmp_path,
        )

        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        assert zip_path.name == "Complete AI Announcement.zip"

        # Check bundle directory was created and contains files
        bundle_dir = tmp_path / "Complete AI Announcement"
        assert bundle_dir.exists()
        assert (bundle_dir / "post.txt").exists()
        assert (bundle_dir / "caption.md").exists()
        assert (bundle_dir / "metadata.json").exists()

        # Check post.txt content
        txt_content = (bundle_dir / "post.txt").read_text(encoding="utf-8")
        assert "Title: Complete AI Announcement" in txt_content
        assert "Here is the full text of our new model release" in txt_content

        # Verify ZIP contains the files
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert any("post.txt" in n for n in names)
            assert any("caption.md" in n for n in names)
            assert any("metadata.json" in n for n in names)


def test_upgrade_image_url():
    from omniget.engine import upgrade_image_url
    assert "name=orig" in upgrade_image_url("https://pbs.twimg.com/media/abc.jpg?name=small")
    assert "name=orig" in upgrade_image_url("https://pbs.twimg.com/media/xyz.jpg")
    assert upgrade_image_url("https://i.ytimg.com/vi/123/hqdefault.jpg") == "https://i.ytimg.com/vi/123/maxresdefault.jpg"
    assert upgrade_image_url("https://preview.redd.it/post123.jpg?width=640") == "https://i.redd.it/post123.jpg"


def test_deduplicate_image_urls():
    from omniget.engine import deduplicate_image_urls
    raw = [
        "https://pbs.twimg.com/media/123.jpg?name=thumb",
        "https://pbs.twimg.com/media/123.jpg?name=small",
        "https://pbs.twimg.com/media/123.jpg?name=large",
        "https://pbs.twimg.com/media/123.jpg?name=orig",
        "https://pbs.twimg.com/profile_images/avatar.jpg", # should filter avatar
        "https://pbs.twimg.com/media/456.jpg?name=medium",
    ]
    deduped = deduplicate_image_urls(raw)
    assert len(deduped) == 2
    assert "name=orig" in deduped[0]
    assert "name=orig" in deduped[1]


def test_download_images_mode(tmp_path):
    engine = MediaEngine(default_output_dir=tmp_path)
    mock_meta = PostMetadata(
        url="https://x.com/example/status/images",
        platform=Platform.TWITTER,
        title="Photo Gallery Post",
        author="@photographer",
        description="Check out this photo",
        has_images=True,
        image_urls=[],
        thumbnail_url=None,
    )
    with patch.object(engine, "inspect_post", return_value=mock_meta):
        out = engine.download(
            url="https://x.com/example/status/images",
            mode=DownloadMode.IMAGES,
            output_dir=tmp_path,
        )
        assert out.exists()

