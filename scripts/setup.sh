#!/usr/bin/env bash
# Setup script for youtube-utils
# Installs all required Python dependencies

set -euo pipefail

echo "=== youtube-utils setup ==="

# Check Python 3.12+
python3 -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ required'" 2>/dev/null || {
    echo "ERROR: Python 3.12+ is required"
    exit 1
}

echo "Installing Python dependencies..."
pip install --quiet yt-dlp openai huggingface_hub imageio-ffmpeg imageio python-dotenv markdown

echo ""
echo "Verifying installations..."
python3 -c "import yt_dlp; print(f'  yt-dlp: {yt_dlp.version.__version__}')"
python3 -c "import openai; print(f'  openai: {openai.__version__}')"
python3 -c "import huggingface_hub; print(f'  huggingface_hub: {huggingface_hub.__version__}')"
python3 -c "import imageio_ffmpeg; print(f'  ffmpeg: {imageio_ffmpeg.get_ffmpeg_exe()}')"

echo ""
echo "Setup complete!"
echo ""
echo "Configure your AI backend in .env:"
echo "  OPENAI_API_KEY=sk-...    # Option A: OpenAI (preferred)"
echo "  HF_TOKEN=hf_...          # Option B: HuggingFace (free tier)"
echo ""
echo "Usage:"
echo "  python src/process_video.py <video_url>"
echo "  python src/process_channel.py <channel_url>"
