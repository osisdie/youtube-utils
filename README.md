# youtube-utils

YouTube video subtitle download, chapter screenshot extraction, and bilingual summary generation toolkit.

## Features

- **Subtitle Download**: Prioritizes creator-uploaded subtitles; falls back to YouTube auto-generated captions
- **Whisper Transcription**: Automatically transcribes via OpenAI Whisper or HuggingFace Whisper when no subtitles are available (supports Chinese and English)
- **Chapter Screenshots + Cover**: Extracts key frames at each chapter timestamp; downloads YouTube thumbnail as fallback when no chapters exist
- **Bilingual Summaries**: Generates Traditional Chinese (zh-TW) and English summaries via OpenAI GPT or HuggingFace (Qwen2.5-72B)
- **Quality Control**: Auto-verifies summaries (simplified/traditional Chinese check, screenshot embedding, structural integrity) with up to 3 retries
- **Whisper Concurrency Control**: Configurable max concurrent Whisper transcriptions (default: 1 to prevent resource exhaustion)
- **Channel Batch Processing**: Process all videos from a YouTube channel sequentially, with auto-resume support
- **402 Auto-Stop**: Automatically stops batch processing when API credits are exhausted; re-run to resume from where it left off
- **HTML/PDF Export**: Convert summaries to styled HTML (with embedded screenshots) and PDF; supports single video or entire channel

## Quick Start

### 1. Setup

```bash
bash scripts/setup.sh
```

### 2. Configure AI Backend

Set **one** of the following API keys in `.env`:

```bash
# Option A: OpenAI (preferred — GPT-4o-mini for summaries, Whisper for transcription)
OPENAI_API_KEY=sk-...

# Option B: HuggingFace (free tier available — Qwen2.5-72B + Whisper-large-v3-turbo)
HF_TOKEN=hf_...

# Optional: Whisper concurrency (default: 1)
WHISPER_MAX_CONCURRENT=1

# Optional: Summary QC max retries (default: 3)
SUMMARY_MAX_RETRIES=3
```

If both are set, OpenAI takes priority. If neither is set, HuggingFace will attempt to use the free Inference API.

**Dependencies:**

| Package | Purpose |
|---------|---------|
| `yt-dlp` | YouTube metadata, subtitle, video download |
| `openai` | (Optional) Whisper transcription + GPT summary |
| `huggingface_hub` | (Optional) HF Whisper + Qwen summary |
| `imageio-ffmpeg` | Bundled ffmpeg for screenshot extraction |
| `python-dotenv` | Auto-load .env configuration |
| `markdown` | Markdown → HTML conversion for export |

### 3. Process a Single Video

```bash
python src/process_video.py "https://www.youtube.com/watch?v=VIDEO_ID" \
  --channel-slug my_channel
```

**Options:**
```
--channel-slug NAME    Output subfolder name (default: 'default')
--output DIR           Base output directory (default: ./output/youtube)
--no-screenshots       Skip chapter screenshot extraction
```

### 4. Process an Entire Channel

```bash
python src/process_channel.py "https://www.youtube.com/@channel_handle" \
  --limit 5 --delay 10
```

The command is **idempotent** — re-running it will skip already-completed videos and resume from incomplete ones. If the API returns 402 (credits exhausted), processing stops automatically. Simply re-run the same command after replenishing credits to continue.

**Options:**
```
--channel-slug NAME    Override auto-detected channel name
--limit N              Process at most N videos (0 = all)
--skip N               Skip first N videos
--delay SECS           Wait between videos to avoid rate limits (default: 5)
--no-screenshots       Skip chapter screenshot extraction
```

### 5. Export Summaries to HTML / PDF

Convert markdown summaries into a self-contained styled HTML (images embedded as base64). Accepts either a **channel directory** (aggregates all videos with a table of contents) or a **single video directory**.

```bash
# Entire channel → HTML
python src/summaries_to_html.py output/youtube/my_channel --lang zh-tw

# Single video → HTML
python src/summaries_to_html.py output/youtube/my_channel/video-slug --lang en

# HTML → PDF (requires Chrome/Chromium)
python src/html_to_pdf.py output/youtube/my_channel/summary_zh-tw.html
```

**summaries_to_html.py options:**
```
target_dir             Channel dir (all videos) or single video dir
--lang LANG            Summary language suffix (default: zh-tw)
-o, --output PATH      Output HTML path (default: {target_dir}/summary_{lang}.html)
```

**html_to_pdf.py options:**
```
html_file              Input HTML file
-o, --output PATH      Output PDF path (default: same name with .pdf)
--paper-size SIZE      Paper size (default: A4)
```

## Pipeline

```
Video URL
  │
  ├─[1] Fetch metadata (title, chapters, subtitle langs)
  │
  ├─[2] Download subtitles
  │     ├─ Try manual subs (zh-TW)
  │     ├─ Try auto-generated subs
  │     └─ Fallback: Whisper transcription (with concurrency control)
  │
  ├─[3] Convert SRT → plain text transcript
  │
  ├─[4] Screenshots
  │     ├─ Has chapters → extract frame at each chapter timestamp
  │     └─ No chapters → download YouTube thumbnail as cover.jpg
  │
  ├─[5] Generate zh-TW summary → QC verify → retry if needed (max 3x)
  │
  └─[6] Generate English summary → QC verify → retry if needed (max 3x)
```

## Quality Control

Each summary is automatically verified against the following checks:

| Check | zh-TW | English |
|-------|-------|---------|
| Minimum length (≥200 chars) | ✓ | ✓ |
| Markdown structure (contains `##` headers) | ✓ | ✓ |
| Traditional Chinese check (detects simplified chars >0.5%) | ✓ | — |
| Screenshot embedding (references at least half of available screenshots) | ✓ | ✓ |

When a check fails, the QC report is injected as a correction hint into the next prompt, guiding the LLM to fix the issues.

## Output Structure

```
output/youtube/
└── {channel_slug}/
    ├── channel_index.json          # (channel mode) video list
    ├── processing_results.json     # (channel mode) success/fail/skip log
    ├── summary_zh-tw.html          # (export) aggregated HTML for all videos
    ├── summary_en.html             # (export) aggregated HTML for all videos
    │
    └── {video_title_slug}/
        ├── metadata.json           # Video metadata + chapters
        ├── video.zh-TW.srt         # Original SRT subtitle file
        ├── transcript.txt          # Plain text transcript
        ├── summary_zh-tw.md        # Traditional Chinese summary (with embedded screenshots)
        ├── summary_en.md           # English summary (with embedded screenshots)
        ├── summary_zh-tw.html      # (export) single video HTML
        ├── summary_zh-tw.pdf       # (export) single video PDF
        └── screenshots/
            ├── ch01_chapter_title.jpg   # Chapter screenshots (if chapters exist)
            ├── ch02_chapter_title.jpg
            └── cover.jpg               # Thumbnail fallback (if no chapters)
```

## Examples

### Process a single video with screenshots

```bash
python src/process_video.py \
  "https://www.youtube.com/watch?v=13QYLAVh-z4" \
  --channel-slug creatorinsider
```

### Process an entire channel

```bash
python src/process_channel.py \
  "https://www.youtube.com/@creatorinsider" \
  --delay 10
```

### Fast mode: no screenshots

```bash
python src/process_channel.py \
  "https://www.youtube.com/@creatorinsider" \
  --no-screenshots --limit 5
```

### Export a single video summary to PDF

```bash
python src/summaries_to_html.py \
  output/youtube/creatorinsider/some-video-slug \
  --lang zh-tw
python src/html_to_pdf.py \
  output/youtube/creatorinsider/some-video-slug/summary_zh-tw.html
```

### Export all channel summaries to PDF

```bash
python src/summaries_to_html.py \
  output/youtube/creatorinsider --lang en
python src/html_to_pdf.py \
  output/youtube/creatorinsider/summary_en.html
```

### Resume after API credit exhaustion

```bash
# Same command — completed videos are automatically skipped
python src/process_channel.py \
  "https://www.youtube.com/@creatorinsider" \
  --delay 10
```

## Notes

- **Rate Limiting**: YouTube may return HTTP 429. Use `--delay` (default 5s) between videos.
- **Whisper Fallback**: Used only when no subtitles are available. Audio >25MB is auto-chunked into 10-min segments.
- **Screenshots**: Chapter screenshots when available; YouTube thumbnail (cover.jpg) as fallback.
- **QC Retries**: If a summary fails QC, it retries with feedback up to 3 times (configurable via `SUMMARY_MAX_RETRIES`).
- **Concurrency**: `WHISPER_MAX_CONCURRENT=1` by default to prevent resource exhaustion on local machines.
- **Auto-Resume**: Channel processing is idempotent. Re-running skips completed videos (checks for both `summary_zh-tw.md` and `summary_en.md`).
- **402 Auto-Stop**: When API credits are exhausted, batch processing stops immediately and cleans up partial output. Re-run to resume.
- **HTML/PDF Export**: HTML is self-contained (images embedded as base64). PDF conversion requires Chrome or Chromium installed.
- **Cost**: With OpenAI, ~2-6 API calls per video (depending on retries). HuggingFace free tier = $0.
