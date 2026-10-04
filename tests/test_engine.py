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
