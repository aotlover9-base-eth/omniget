#!/usr/bin/env bash
set -e

# ==============================================================================
# OmniGet - Universal Social Media Post & Media Downloader Installer
# ==============================================================================

echo "================================================="
echo "  📥 OmniGet - Installing Universal Media Downloader"
echo "================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR"

# 1. Check and install system dependencies (ffmpeg and yt-dlp)
echo "-> Checking system dependencies..."

if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg is not installed! FFmpeg is required for video and audio processing."
    echo "-> Attempting to auto-install FFmpeg..."
    if command -v apt-get &> /dev/null; then
        echo "-> Detected Debian/Ubuntu (apt-get). Installing ffmpeg..."
        sudo apt-get update -qq && sudo apt-get install -y ffmpeg
    elif command -v pacman &> /dev/null; then
        echo "-> Detected Arch Linux (pacman). Installing ffmpeg..."
        sudo pacman -S --noconfirm ffmpeg
    elif command -v dnf &> /dev/null; then
        echo "-> Detected Fedora/RHEL (dnf). Installing ffmpeg..."
        sudo dnf install -y ffmpeg
    elif command -v zypper &> /dev/null; then
        echo "-> Detected openSUSE (zypper). Installing ffmpeg..."
        sudo zypper install -y ffmpeg
    elif command -v apk &> /dev/null; then
        echo "-> Detected Alpine Linux (apk). Installing ffmpeg..."
        sudo apk add ffmpeg
    elif command -v brew &> /dev/null; then
        echo "-> Detected Homebrew. Installing ffmpeg..."
        brew install ffmpeg
    else
        echo "⚠️  Could not detect supported package manager. Please install FFmpeg manually for your system."
    fi
else
    echo "✔ FFmpeg is installed."
fi

if ! command -v yt-dlp &> /dev/null; then
    echo "-> Checking yt-dlp CLI..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get install -y yt-dlp 2>/dev/null || python3 -m pip install --user yt-dlp 2>/dev/null || true
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm yt-dlp 2>/dev/null || true
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y yt-dlp 2>/dev/null || true
    elif command -v brew &> /dev/null; then
        brew install yt-dlp 2>/dev/null || true
    fi
else
    echo "✔ yt-dlp CLI is installed."
fi

# 2. Install CLI tool using uv if available, or pip
if command -v uv &> /dev/null; then
    echo "-> Installing omniget executable using uv..."
    uv tool install "$SCRIPT_DIR" --force
else
    echo "-> Installing omniget executable using pip..."
    python3 -m pip install -e "$SCRIPT_DIR" --break-system-packages 2>/dev/null || python3 -m pip install -e "$SCRIPT_DIR"
fi

echo ""
echo "================================================="
echo "  ✔ Installation Complete!"
echo "================================================="
echo "Commands available:"
echo "  • omniget                         -> Launch interactive Terminal TUI"
echo "  • omniget <URL>                   -> Inspect and download via TUI"
echo "  • omniget <URL> --video           -> Download best MP4 video"
echo "  • omniget <URL> --audio           -> Download high-quality MP3"
echo "  • omniget <URL> --images          -> Download gallery photos"
echo "  • omniget <URL> --bundle          -> Download full archive (media + caption)"
echo "  • omniget <URL> --text            -> Save post caption as Markdown"
echo "  • omniget --history               -> View recent download library"
echo "================================================="
