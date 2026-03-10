#!/usr/bin/env python3
"""
Process a single YouTube video:
  - Download subtitles (Whisper fallback)
  - Extract chapter screenshots
  - Generate bilingual summaries (zh-TW + en)

Usage:
  python src/process_video.py <video_url> [--channel-slug NAME] [--no-screenshots]

Examples:
  python src/process_video.py "https://www.youtube.com/watch?v=-bWfMUDbKdI"
  python src/process_video.py "https://youtu.be/abc123" --channel-slug inside6202
  python src/process_video.py "https://youtu.be/abc123" --no-screenshots
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from youtube_utils import process_video


def main():
    parser = argparse.ArgumentParser(description="Process a single YouTube video")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--channel-slug",
        default="default",
        help="Channel subfolder name (default: 'default')",
    )
    parser.add_argument(
        "--output",
        default="./output/youtube",
        help="Base output directory (default: ./output/youtube)",
    )
    parser.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Skip chapter screenshot extraction",
    )
    args = parser.parse_args()

    out_dir = process_video(
        video_url=args.url,
        output_base=args.output,
        channel_slug=args.channel_slug,
        with_screenshots=not args.no_screenshots,
    )
    print(f"\nAll files written to: {out_dir}")


if __name__ == "__main__":
    main()
