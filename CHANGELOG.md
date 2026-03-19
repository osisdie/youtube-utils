# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-03-19

### Added
- Subtitle download with creator-uploaded and auto-generated fallback
- Whisper transcription fallback (OpenAI and HuggingFace backends)
- Chapter screenshot extraction and YouTube thumbnail fallback
- Bilingual summary generation (zh-TW + English) via GPT or Qwen2.5-72B
- Quality control with auto-retry (simplified/traditional Chinese check, structure, screenshots)
- Whisper concurrency control (`WHISPER_MAX_CONCURRENT`)
- Channel batch processing with auto-resume and 402 auto-stop
- HTML/PDF export with embedded base64 images
- Claude Code agents for single video and channel processing
- CI pipelines for GitHub Actions and GitLab CI
- Pre-commit hooks (ruff, trailing whitespace, YAML check)
- README badges, CONTRIBUTING.md, GitHub Topics
