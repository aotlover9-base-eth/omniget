import pytest
from omniget.models import Platform, detect_platform


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", Platform.YOUTUBE),
        ("https://youtube.com/shorts/5xH_h38aH60", Platform.YOUTUBE),
        ("https://m.youtube.com/watch?v=abc12345", Platform.YOUTUBE),
        ("https://youtu.be/dQw4w9WgXcQ", Platform.YOUTUBE),
        ("https://twitter.com/elonmusk/status/1780000000000000000", Platform.TWITTER),
        ("https://x.com/karpathy/status/1760000000000000000", Platform.TWITTER),
        ("https://mobile.twitter.com/user/status/123", Platform.TWITTER),
        ("https://t.co/abcXYZ123", Platform.TWITTER),
        ("https://www.instagram.com/p/C3_sample/", Platform.INSTAGRAM),
        ("https://instagram.com/reel/C3_sample/", Platform.INSTAGRAM),
        ("https://instagr.am/p/C3_sample/", Platform.INSTAGRAM),
        ("https://www.reddit.com/r/technology/comments/xyz123/title/", Platform.REDDIT),
        ("https://reddit.com/r/linux/comments/xyz123/title/", Platform.REDDIT),
        ("https://redd.it/xyz123", Platform.REDDIT),
        ("https://www.facebook.com/watch/?v=123456789", Platform.FACEBOOK),
        ("https://fb.watch/sampleVideoId/", Platform.FACEBOOK),
        ("https://facebook.com/reel/123456789", Platform.FACEBOOK),
        ("https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4", Platform.GENERIC),
        ("https://example.com/some/article/path", Platform.GENERIC),
        ("", Platform.GENERIC),
    ],
)
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


def test_platform_display_names():
    assert "YouTube" in Platform.YOUTUBE.display_name
    assert "Twitter" in Platform.TWITTER.display_name or "X" in Platform.TWITTER.display_name
    assert "Instagram" in Platform.INSTAGRAM.display_name
    assert "Reddit" in Platform.REDDIT.display_name
    assert "Facebook" in Platform.FACEBOOK.display_name
