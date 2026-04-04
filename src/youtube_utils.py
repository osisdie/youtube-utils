"""
Core utilities for YouTube video processing:
- Subtitle download (with Whisper fallback)
- Chapter screenshot extraction
- Summary generation via OpenAI or HuggingFace API
- Quality control with automatic retry
"""

import sys

if sys.version_info < (3, 12):
    sys.exit("Python 3.12+ is required. Current: " + sys.version)

import json
import os
import re
import subprocess
import threading
from pathlib import Path

from dotenv import load_dotenv
import imageio_ffmpeg

# Auto-load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Whisper concurrency: limit parallel transcriptions (default=1 for local resources)
_WHISPER_MAX_CONCURRENT = int(os.environ.get("WHISPER_MAX_CONCURRENT", "1"))
_whisper_semaphore = threading.Semaphore(_WHISPER_MAX_CONCURRENT)

# Summary QC: max retry attempts
SUMMARY_MAX_RETRIES = int(os.environ.get("SUMMARY_MAX_RETRIES", "3"))

# Simplified Chinese characters commonly seen in AI output that differ from Traditional
_SIMPLIFIED_CHARS = set(
    "这来为说对时没还开发关与动东车长门问间进远连"
    "运过让达选认议决设计边导组织华门关发变听结经"
    "称总飞战终给绝应该续买讲号实际练产业务联题点"
    "国际园场环节电击标准备单纯简双颗军队满条协调"
    "赛区创预从尤将丝备脸态势钱账际极种标临视预"
)


# ---------------------------------------------------------------------------
# AI backend detection
# ---------------------------------------------------------------------------


def _get_backend() -> str:
    """Detect which AI backend to use: 'openai' or 'huggingface'."""
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
        return "huggingface"
    try:
        from huggingface_hub import InferenceClient  # noqa: F401

        return "huggingface"
    except ImportError:
        pass
    raise RuntimeError(
        "No AI backend available. Set OPENAI_API_KEY or HF_TOKEN in .env"
    )


def _get_hf_client():
    from huggingface_hub import InferenceClient

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    return InferenceClient(token=token) if token else InferenceClient()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify(text: str, max_len: int = 60) -> str:
    """Turn a title into a filesystem-safe slug."""
    text = re.sub(r"[｜|：:；;，,。.！!？?【】\[\]()（）「」\s]+", "_", text)
    text = re.sub(r"[^\w\u4e00-\u9fff\-]", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_len]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command and return result."""
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ---------------------------------------------------------------------------
# Quality control
# ---------------------------------------------------------------------------


def _has_simplified_chinese(text: str, threshold: float = 0.005) -> bool:
    """Check if text contains too many simplified Chinese characters.

    Returns True if the ratio of known simplified-only chars exceeds threshold.
    """
    if not text:
        return False
    cjk_chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    if not cjk_chars:
        return False
    simplified_count = sum(1 for c in cjk_chars if c in _SIMPLIFIED_CHARS)
    ratio = simplified_count / len(cjk_chars)
    return ratio > threshold


def _has_screenshot_refs(text: str, expected_count: int) -> bool:
    """Check if summary contains embedded screenshot markdown refs."""
    if expected_count == 0:
        return True
    refs = re.findall(r"!\[.*?\]\(screenshots/.*?\)", text)
    # At least half of expected screenshots should be referenced
    return len(refs) >= max(1, expected_count // 2)


def verify_summary(
    summary: str,
    lang: str,
    screenshot_count: int = 0,
) -> tuple[bool, list[str]]:
    """Verify summary quality. Returns (passed, list_of_issues)."""
    issues = []

    # Check minimum length
    if len(summary) < 200:
        issues.append(f"Summary too short ({len(summary)} chars, need >= 200)")

    # Check for markdown structure
    if "##" not in summary:
        issues.append("Missing markdown headers (##)")

    # Check language quality for zh-TW
    if lang == "zh-TW" and _has_simplified_chinese(summary):
        issues.append("Contains simplified Chinese characters (should be Traditional)")

    # Check screenshot embedding
    if screenshot_count > 0 and not _has_screenshot_refs(summary, screenshot_count):
        pat = r"!\[.*?\]\(screenshots/.*?\)"
        found = len(re.findall(pat, summary))
        issues.append(
            f"Missing screenshot references (expected ~{screenshot_count}, "
            f"found {found})"
        )

    return (len(issues) == 0, issues)


# ---------------------------------------------------------------------------
# Video metadata
# ---------------------------------------------------------------------------


def get_video_info(video_url: str) -> dict:
    """Return dict with id, title, chapters, available subtitle langs."""
    r = run(["yt-dlp", "--dump-json", "--no-download", video_url])
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed: {r.stderr}")
    data = json.loads(r.stdout)
    return {
        "id": data["id"],
        "title": data.get("title", ""),
        "duration": data.get("duration", 0),
        "chapters": data.get("chapters") or [],
        "subtitles": list((data.get("subtitles") or {}).keys()),
        "auto_captions": list((data.get("automatic_captions") or {}).keys()),
        "channel": data.get("channel", ""),
        "thumbnail": data.get("thumbnail", ""),
        "upload_date": data.get("upload_date", ""),
        "modified_date": data.get("modified_date", ""),
        "release_date": data.get("release_date", ""),
    }


def get_channel_videos(channel_url: str) -> list[dict]:
    """Return list of {id, title} for every video on a channel."""
    r = run(
        [
            "yt-dlp",
            "--flat-playlist",
            "--print",
            "%(id)s\t%(title)s",
            f"{channel_url}/videos",
        ]
    )
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp channel listing failed: {r.stderr}")
    videos = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            videos.append({"id": parts[0], "title": parts[1]})
    return videos


# ---------------------------------------------------------------------------
# Subtitles
# ---------------------------------------------------------------------------


def download_subtitles(
    video_url: str, out_dir: Path, lang: str = "zh-TW"
) -> Path | None:
    """Download manual or auto-generated subtitles. Returns .srt path or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    srt_path = out_dir / f"video.{lang}.srt"

    # Try manual subs first
    run(
        [
            "yt-dlp",
            "--write-subs",
            "--sub-lang",
            lang,
            "--sub-format",
            "srt",
            "--skip-download",
            "-o",
            str(out_dir / "video"),
            video_url,
        ]
    )
    if srt_path.exists() and srt_path.stat().st_size > 0:
        return srt_path

    # Try auto-generated subs
    run(
        [
            "yt-dlp",
            "--write-auto-subs",
            "--sub-lang",
            lang,
            "--sub-format",
            "srt",
            "--skip-download",
            "-o",
            str(out_dir / "video"),
            video_url,
        ]
    )
    if srt_path.exists() and srt_path.stat().st_size > 0:
        return srt_path

    return None


def srt_to_text(srt_path: Path) -> str:
    """Convert SRT file to plain text (no timestamps)."""
    content = srt_path.read_text(encoding="utf-8")
    lines = []
    for line in content.splitlines():
        line = line.strip()
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):
            continue
        if not line:
            continue
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Whisper / HF transcription fallback
# ---------------------------------------------------------------------------


def _download_audio(video_url: str, out_dir: Path) -> Path | None:
    """Download audio from video. Returns path or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / "audio.m4a"
    if audio_path.exists():
        return audio_path

    run(
        [
            "yt-dlp",
            "--ffmpeg-location",
            str(Path(FFMPEG).parent),
            "-f",
            "worstaudio[ext=m4a]/worstaudio",
            "--extract-audio",
            "--audio-format",
            "m4a",
            "-o",
            str(audio_path),
            video_url,
        ]
    )
    if not audio_path.exists():
        candidates = list(out_dir.glob("audio*"))
        if candidates:
            candidates[0].rename(audio_path)
    return audio_path if audio_path.exists() else None


def whisper_transcribe(video_url: str, out_dir: Path) -> str | None:
    """Download audio and transcribe with concurrency control."""
    audio_path = _download_audio(video_url, out_dir)
    if not audio_path:
        print("  [WARN] Audio download failed", file=sys.stderr)
        return None

    backend = _get_backend()
    print(
        f"  [3/6] Transcribing with {backend} backend "
        f"(max concurrent: {_WHISPER_MAX_CONCURRENT})..."
    )

    with _whisper_semaphore:
        try:
            if backend == "openai":
                return _whisper_openai(audio_path, out_dir)
            else:
                return _whisper_hf(audio_path, out_dir)
        finally:
            audio_path.unlink(missing_ok=True)


def _whisper_openai(audio_path: Path, out_dir: Path) -> str:
    """Transcribe using OpenAI Whisper API."""
    from openai import OpenAI

    client = OpenAI()
    file_size = audio_path.stat().st_size
    if file_size > 24 * 1024 * 1024:
        return _whisper_openai_chunked(client, audio_path, out_dir)

    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(model="whisper-1", file=f)
    return resp.text


def _whisper_openai_chunked(client, audio_path: Path, out_dir: Path) -> str:
    """Split audio into <24MB chunks and transcribe each."""
    chunk_pattern = str(out_dir / "chunk_%03d.m4a")
    run(
        [
            FFMPEG,
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            "600",
            "-c",
            "copy",
            chunk_pattern,
        ]
    )
    chunks = sorted(out_dir.glob("chunk_*.m4a"))
    texts = []
    for chunk in chunks:
        with open(chunk, "rb") as f:
            resp = client.audio.transcriptions.create(model="whisper-1", file=f)
        texts.append(resp.text)
        chunk.unlink()
    return "\n".join(texts)


def _whisper_hf(audio_path: Path, out_dir: Path) -> str:
    """Transcribe using HuggingFace Inference API."""
    client = _get_hf_client()

    wav_path = out_dir / "audio_for_asr.wav"
    run(
        [FFMPEG, "-i", str(audio_path), "-ar", "16000", "-ac", "1", "-y", str(wav_path)]
    )
    if not wav_path.exists():
        raise RuntimeError("Failed to convert audio to wav")

    file_size = wav_path.stat().st_size
    if file_size > 24 * 1024 * 1024:
        result = _whisper_hf_chunked(client, audio_path, out_dir)
    else:
        result = client.automatic_speech_recognition(
            str(wav_path),
            model="openai/whisper-large-v3-turbo",
        )
        result = result.text
    wav_path.unlink(missing_ok=True)
    return result


def _whisper_hf_chunked(client, audio_path: Path, out_dir: Path) -> str:
    """Split audio into 10-min wav chunks and transcribe each via HF."""
    chunk_pattern = str(out_dir / "chunk_%03d.wav")
    run(
        [
            FFMPEG,
            "-i",
            str(audio_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "segment",
            "-segment_time",
            "600",
            chunk_pattern,
        ]
    )
    chunks = sorted(out_dir.glob("chunk_*.wav"))
    texts = []
    for chunk in chunks:
        result = client.automatic_speech_recognition(
            str(chunk),
            model="openai/whisper-large-v3-turbo",
        )
        texts.append(result.text)
        chunk.unlink()
    return "\n".join(texts)


# ---------------------------------------------------------------------------
# Screenshots at chapter timestamps
# ---------------------------------------------------------------------------


def download_video_low_quality(video_url: str, out_dir: Path) -> Path | None:
    """Download video at lowest quality for screenshot extraction."""
    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "video_low.mp4"
    if video_path.exists():
        return video_path

    run(
        [
            "yt-dlp",
            "--ffmpeg-location",
            str(Path(FFMPEG).parent),
            "-f",
            "worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst",
            "--merge-output-format",
            "mp4",
            "-o",
            str(video_path),
            video_url,
        ]
    )
    if video_path.exists():
        return video_path
    run(
        [
            "yt-dlp",
            "--ffmpeg-location",
            str(Path(FFMPEG).parent),
            "-f",
            "worst",
            "-o",
            str(video_path),
            video_url,
        ]
    )
    return video_path if video_path.exists() else None


def extract_screenshots(
    video_path: Path, chapters: list[dict], out_dir: Path
) -> list[dict]:
    """Extract a screenshot for each chapter."""
    ss_dir = out_dir / "screenshots"
    ss_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for i, ch in enumerate(chapters):
        start = ch["start_time"]
        end = ch.get("end_time", start + 10)
        offset = min(5, (end - start) / 2)
        timestamp = start + offset

        img_name = f"ch{i + 1:02d}_{slugify(ch['title'], 30)}.jpg"
        img_path = ss_dir / img_name

        if img_path.exists():
            results.append(
                {"title": ch["title"], "time": start, "image": str(img_path)}
            )
            continue

        run(
            [
                FFMPEG,
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-q:v",
                "2",
                "-y",
                str(img_path),
            ]
        )
        if img_path.exists():
            results.append(
                {"title": ch["title"], "time": start, "image": str(img_path)}
            )
        else:
            print(
                f"  [WARN] Screenshot failed for chapter {i + 1}: {ch['title']}",
                file=sys.stderr,
            )

    return results


def download_thumbnail(video_url: str, out_dir: Path) -> dict | None:
    """Download the video thumbnail as a fallback cover image."""
    ss_dir = out_dir / "screenshots"
    ss_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = ss_dir / "cover.jpg"

    if thumb_path.exists():
        return {"title": "Cover", "time": 0, "image": str(thumb_path)}

    run(
        [
            "yt-dlp",
            "--ffmpeg-location",
            str(Path(FFMPEG).parent),
            "--write-thumbnail",
            "--skip-download",
            "--convert-thumbnails",
            "jpg",
            "-o",
            str(ss_dir / "cover"),
            video_url,
        ]
    )
    candidates = sorted(ss_dir.glob("cover*"))
    for c in candidates:
        if c.suffix in (".jpg", ".jpeg", ".png", ".webp"):
            if c.name != "cover.jpg":
                c.rename(thumb_path)
            return {"title": "Cover", "time": 0, "image": str(thumb_path)}

    return None


# ---------------------------------------------------------------------------
# Summary generation (OpenAI or HuggingFace) with QC
# ---------------------------------------------------------------------------


def _format_date(raw: str) -> str:
    """Convert yt-dlp date string 'YYYYMMDD' to 'YYYY-MM-DD'. Returns '' on bad input."""
    if raw and len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw or ""


def _build_summary_prompt(
    transcript: str,
    video_title: str,
    video_url: str,
    chapters: list[dict] | None,
    screenshots: list[dict] | None,
    lang: str,
    retry_hint: str = "",
    upload_date: str = "",
    modified_date: str = "",
) -> str:
    """Build the summary prompt for either backend."""
    if lang == "zh-TW":
        lang_instruction = (
            "請用繁體中文撰寫摘要。\n"
            "【重要】你必須全程使用繁體中文（Traditional Chinese），"
            "嚴禁使用任何簡體中文字。"
            "例如：用「這」不用「这」、用「來」不用「来」、"
            "用「為」不用「为」、用「說」不用「说」、"
            "用「對」不用「对」、用「時」不用「时」、"
            "用「還」不用「还」、用「開」不用「开」、"
            "用「國」不用「国」、用「發」不用「发」。"
        )
    else:
        lang_instruction = "Write the summary in English."

    chapter_info = ""
    if chapters:
        chapter_lines = []
        for i, ch in enumerate(chapters):
            m, s = divmod(int(ch["start_time"]), 60)
            h, m = divmod(m, 60)
            ts = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            chapter_lines.append(f"- [{ts}] {ch['title']}")
        chapter_info = "\n章節列表:\n" + "\n".join(chapter_lines)

    screenshot_instruction = ""
    if screenshots:
        ss_lines = []
        for ss in screenshots:
            rel_path = f"screenshots/{Path(ss['image']).name}"
            ss_lines.append(f"- `{rel_path}` → {ss['title']}")
        if lang == "zh-TW":
            screenshot_instruction = (
                "\n\n請在摘要的對應章節中嵌入截圖，使用 Markdown 圖片語法:\n"
                "![章節標題](screenshots/filename.jpg)\n\n"
                "可用截圖:\n" + "\n".join(ss_lines)
            )
        else:
            screenshot_instruction = (
                "\n\nEmbed chapter screenshots in the summary using Markdown image syntax:\n"
                "![Chapter Title](screenshots/filename.jpg)\n\n"
                "Available screenshots:\n" + "\n".join(ss_lines)
            )

    # Truncate transcript if too long
    max_chars = 80_000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n...(truncated)"

    retry_section = ""
    if retry_hint:
        retry_section = (
            f"\n\n【修正提示】上次產出有以下問題，請務必修正：\n{retry_hint}\n"
        )

    date_info = ""
    if upload_date:
        date_info += f"\n發布日期: {upload_date}"
    if modified_date and modified_date != upload_date:
        date_info += f"\n更新日期: {modified_date}"

    return (
        f"""你是一個專業的影片內容摘要助手。

影片標題: {video_title}
影片連結: {video_url}{date_info}
{chapter_info}
"""
        + screenshot_instruction
        + f"""
{lang_instruction}
{retry_section}
請根據以下逐字稿，產生一份結構化的 Markdown 摘要，包含:
1. 影片標題與來源連結
2. 來賓/主持人資訊（如果有的話）
3. 整體摘要（2-3 句話）
4. 依照章節或主題分段的重點整理（每段 3-5 個要點）
5. 關鍵洞見或金句
6. 如果有推薦的書籍/資源，也列出來

逐字稿:
{transcript}"""
    )


def generate_summary_with_qc(
    transcript: str,
    video_title: str,
    video_url: str,
    chapters: list[dict] | None = None,
    screenshots: list[dict] | None = None,
    lang: str = "zh-TW",
    max_retries: int = SUMMARY_MAX_RETRIES,
    upload_date: str = "",
    modified_date: str = "",
) -> str:
    """Generate summary with quality control — verify and retry up to max_retries."""
    backend = _get_backend()
    screenshot_count = len(screenshots) if screenshots else 0
    retry_hint = ""

    for attempt in range(1, max_retries + 1):
        prompt = _build_summary_prompt(
            transcript,
            video_title,
            video_url,
            chapters,
            screenshots,
            lang,
            retry_hint,
            upload_date=upload_date,
            modified_date=modified_date,
        )

        if backend == "openai":
            summary = _summarize_openai(prompt)
        else:
            summary = _summarize_hf(prompt)

        passed, issues = verify_summary(summary, lang, screenshot_count)

        if passed:
            if attempt > 1:
                print(f"    QC passed on attempt {attempt}")
            return summary

        issue_str = "; ".join(issues)
        print(f"    QC failed (attempt {attempt}/{max_retries}): {issue_str}")

        if attempt < max_retries:
            # Build retry hint for next attempt
            retry_hint = "\n".join(f"- {issue}" for issue in issues)

    # Return last attempt even if QC failed
    print(
        f"    [WARN] QC still failing after {max_retries} attempts, using last result"
    )
    return summary


def _summarize_openai(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000,
    )
    return resp.choices[0].message.content


def _summarize_hf(prompt: str) -> str:
    client = _get_hf_client()
    resp = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model="Qwen/Qwen2.5-72B-Instruct",
        max_tokens=4000,
        temperature=0.3,
    )
    return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def process_video(
    video_url: str,
    output_base: str = "./output/youtube",
    channel_slug: str = "default",
    with_screenshots: bool = True,
) -> Path:
    """
    Full pipeline: metadata → subtitles → transcript → screenshots → summaries.
    Returns the output directory path.
    """
    backend = _get_backend()
    print(f"\n{'=' * 60}")
    print(f"Processing: {video_url}")
    print(f"AI backend: {backend}")
    print(f"{'=' * 60}")

    # 1. Metadata
    print("  [1/6] Fetching metadata...")
    info = get_video_info(video_url)
    if channel_slug == "default" and info.get("channel"):
        channel_slug = slugify(info["channel"])
    title_slug = slugify(info["title"])
    out_dir = Path(output_base) / channel_slug / title_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "metadata.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 2. Subtitles
    print("  [2/6] Downloading subtitles...")
    srt_path = download_subtitles(video_url, out_dir)

    # 3. Transcript
    print("  [3/6] Generating transcript...")
    if srt_path:
        transcript = srt_to_text(srt_path)
    else:
        print("  [3/6] No subtitles found, falling back to Whisper...")
        transcript = whisper_transcribe(video_url, out_dir)
        if not transcript:
            print("  [ERROR] Could not obtain transcript.", file=sys.stderr)
            return out_dir

    transcript_path = out_dir / "transcript.txt"
    transcript_path.write_text(transcript, encoding="utf-8")
    print(f"  [3/6] Transcript: {len(transcript.splitlines())} lines")

    # 4. Screenshots (chapters → thumbnail fallback — always try to get at least one)
    screenshots = []
    if with_screenshots:
        if info["chapters"]:
            print(f"  [4/6] Extracting {len(info['chapters'])} chapter screenshots...")
            video_path = download_video_low_quality(video_url, out_dir)
            if video_path:
                screenshots = extract_screenshots(video_path, info["chapters"], out_dir)
                video_path.unlink(missing_ok=True)
                for frag in out_dir.glob("video_low.f*"):
                    frag.unlink(missing_ok=True)
                print(f"  [4/6] Extracted {len(screenshots)} screenshots")
            else:
                print("  [4/6] Video download failed, falling back to thumbnail")
        if not screenshots:
            print("  [4/6] No chapters — downloading thumbnail as cover...")
            thumb = download_thumbnail(video_url, out_dir)
            if thumb:
                screenshots = [thumb]
                print("  [4/6] Thumbnail cover downloaded")
            else:
                print("  [4/6] Thumbnail download also failed")
    else:
        print("  [4/6] Screenshots disabled")

    # Formatted dates for summaries
    pub_date = _format_date(info.get("upload_date", ""))
    mod_date = _format_date(info.get("modified_date", ""))

    # 5. Chinese summary (with QC)
    print("  [5/6] Generating zh-TW summary...")
    summary_zh = generate_summary_with_qc(
        transcript,
        info["title"],
        video_url,
        info["chapters"],
        screenshots,
        lang="zh-TW",
        upload_date=pub_date,
        modified_date=mod_date,
    )
    (out_dir / "summary_zh-tw.md").write_text(summary_zh, encoding="utf-8")

    # 6. English summary (with QC)
    print("  [6/6] Generating English summary...")
    summary_en = generate_summary_with_qc(
        transcript,
        info["title"],
        video_url,
        info["chapters"],
        screenshots,
        lang="en",
        upload_date=pub_date,
        modified_date=mod_date,
    )
    (out_dir / "summary_en.md").write_text(summary_en, encoding="utf-8")

    print(f"\n  Done! Output: {out_dir}")
    return out_dir
