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
