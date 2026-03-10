#!/usr/bin/env python3
"""
Process all videos from a YouTube channel sequentially.

Usage:
  python src/process_channel.py <channel_url> [--channel-slug NAME] [--limit N] [--skip N] [--no-screenshots]

Examples:
  python src/process_channel.py "https://www.youtube.com/@cfoooo8337"
  python src/process_channel.py "https://www.youtube.com/@cfoooo8337" --channel-slug cfoooo --limit 5
  python src/process_channel.py "https://www.youtube.com/@cfoooo8337" --skip 3 --limit 10
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from youtube_utils import get_channel_videos, process_video, slugify


def _is_video_complete(channel_dir: Path, video_title: str) -> bool:
    """Check if a video has already been fully processed (has both summaries)."""
    slug = slugify(video_title)
    video_dir = channel_dir / slug
    return (video_dir / "summary_zh-tw.md").exists() and (
        video_dir / "summary_en.md"
    ).exists()


def _cleanup_partial(channel_dir: Path, video_title: str) -> None:
    """Remove partial output directory for a video that failed mid-processing."""
    slug = slugify(video_title)
    video_dir = channel_dir / slug
    if video_dir.exists() and not (video_dir / "summary_en.md").exists():
        shutil.rmtree(video_dir)
        print(f"  [CLEANUP] Removed partial output: {video_dir.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Process all videos from a YouTube channel"
    )
    parser.add_argument("channel_url", help="YouTube channel URL")
    parser.add_argument(
        "--channel-slug",
        default=None,
        help="Channel subfolder name (auto-detected from URL if omitted)",
    )
    parser.add_argument(
        "--output",
        default="./output/youtube",
        help="Base output directory (default: ./output/youtube)",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Max videos to process (0=all)"
    )
    parser.add_argument("--skip", type=int, default=0, help="Skip first N videos")
    parser.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Skip chapter screenshot extraction",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="Seconds to wait between videos to avoid rate limiting (default: 5)",
    )
    args = parser.parse_args()

    # Auto-detect channel slug from URL
    channel_slug = args.channel_slug
    if not channel_slug:
        # Extract @handle or channel name from URL
        url = args.channel_url.rstrip("/")
        if "/@" in url:
            channel_slug = url.split("/@")[-1].split("/")[0]
        elif "/c/" in url:
            channel_slug = url.split("/c/")[-1].split("/")[0]
        elif "/channel/" in url:
            channel_slug = url.split("/channel/")[-1].split("/")[0]
        else:
            channel_slug = slugify(url.split("/")[-1])

    print(f"Channel slug: {channel_slug}")
    print(f"Fetching video list from: {args.channel_url}")

    videos = get_channel_videos(args.channel_url)
    total = len(videos)
    print(f"Found {total} videos")

    # Apply skip/limit
    videos = videos[args.skip :]
    if args.limit > 0:
        videos = videos[: args.limit]

    print(
        f"Processing {len(videos)} videos (skip={args.skip}, limit={args.limit or 'all'})\n"
    )

    # Save channel index
    output_base = Path(args.output)
    channel_dir = output_base / channel_slug
    channel_dir.mkdir(parents=True, exist_ok=True)
    (channel_dir / "channel_index.json").write_text(
        json.dumps(
            {"channel_url": args.channel_url, "videos": videos},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Process each video
    results = []
    skipped = 0
    for i, video in enumerate(videos):
        video_url = f"https://www.youtube.com/watch?v={video['id']}"

        # Skip already-completed videos
        if _is_video_complete(channel_dir, video["title"]):
            skipped += 1
            print(
                f"\n[{i + 1}/{len(videos)}] [SKIP] {video['title']} (already complete)"
            )
            results.append(
                {
                    "id": video["id"],
                    "title": video["title"],
                    "status": "skipped",
                }
            )
            continue

        print(f"\n[{i + 1}/{len(videos)}] {video['title']}")

        try:
            out_dir = process_video(
                video_url=video_url,
                output_base=args.output,
                channel_slug=channel_slug,
                with_screenshots=not args.no_screenshots,
            )
            results.append(
                {
                    "id": video["id"],
                    "title": video["title"],
                    "status": "ok",
                    "output": str(out_dir),
                }
            )
        except Exception as e:
            error_msg = str(e)
            print(f"  [ERROR] {error_msg}", file=sys.stderr)
            results.append(
                {
                    "id": video["id"],
                    "title": video["title"],
                    "status": "error",
                    "error": error_msg,
                }
            )

            # Stop immediately on 402 Payment Required (credits exhausted)
            if "402" in error_msg and "Payment Required" in error_msg:
                _cleanup_partial(channel_dir, video["title"])
                remaining = len(videos) - i - 1
                print(
                    f"\n[STOP] API credits exhausted (402). "
                    f"Stopped at video {i + 1}/{len(videos)} ({remaining} remaining). "
                    f"Re-run the same command to auto-resume from incomplete videos.",
                    file=sys.stderr,
                )
                break

        # Rate limiting delay between videos
        if i < len(videos) - 1:
            print(f"  Waiting {args.delay}s before next video...")
            time.sleep(args.delay)

    # Save results
    (channel_dir / "processing_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] == "error")
    skip = sum(1 for r in results if r["status"] == "skipped")
    print(f"\n{'=' * 60}")
    print(f"Channel processing complete: {ok} succeeded, {fail} failed, {skip} skipped")
    print(f"Results: {channel_dir / 'processing_results.json'}")


if __name__ == "__main__":
    main()
