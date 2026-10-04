"""
Clipboard helper for OmniGet supporting Wayland and X11 natively.
"""

from __future__ import annotations
import shutil
import subprocess


def get_clipboard_text() -> str:
    """Retrieve text from system clipboard."""
    if shutil.which("wl-paste"):
        try:
            res = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass

    if shutil.which("xclip"):
        try:
            res = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass

    if shutil.which("xsel"):
        try:
            res = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass

    return ""


def copy_clipboard_text(text: str) -> bool:
    """Copy text to system clipboard."""
    if not text:
        return False

    if shutil.which("wl-copy"):
        try:
            subprocess.run(
                ["wl-copy"],
                input=text,
                text=True,
                timeout=1,
                check=True,
            )
            return True
        except Exception:
            pass

    if shutil.which("xclip"):
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text,
                text=True,
                timeout=1,
                check=True,
            )
            return True
        except Exception:
            pass

    return False
