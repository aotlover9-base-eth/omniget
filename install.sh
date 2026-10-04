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

# 1. Install CLI tool using uv if available, or pip
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
