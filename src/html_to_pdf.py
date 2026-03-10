#!/usr/bin/env python3
"""
Convert an HTML file to PDF using headless Chrome.

Usage:
  python src/html_to_pdf.py output/youtube/cfoooo8337/summaries_zh-tw.html
  python src/html_to_pdf.py summaries.html -o book.pdf
  python src/html_to_pdf.py summaries.html --paper-size Letter
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Chrome binary candidates (in priority order)
_CHROME_CANDIDATES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def _find_chrome() -> str | None:
    for candidate in _CHROME_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return None


def html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    paper_size: str = "A4",
) -> Path:
    """Convert HTML to PDF via headless Chrome --print-to-pdf."""
    chrome = _find_chrome()
    if not chrome:
        print(
            "Error: Chrome/Chromium not found. Install google-chrome or chromium.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Chrome needs a file:// URI
    file_uri = html_path.resolve().as_uri()

    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-software-rasterizer",
        f"--print-to-pdf={pdf_path.resolve()}",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        file_uri,
    ]

    print(f"Running: {chrome} --headless --print-to-pdf ...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if not pdf_path.exists():
        print("Error: PDF generation failed.", file=sys.stderr)
        if result.stderr:
            print(result.stderr[:500], file=sys.stderr)
        sys.exit(1)

    return pdf_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert HTML to PDF using headless Chrome"
    )
    parser.add_argument("html_file", help="Input HTML file path")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output PDF path (default: same name with .pdf extension)",
    )
    parser.add_argument(
        "--paper-size",
        default="A4",
        help="Paper size (default: A4)",
    )
    args = parser.parse_args()

    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"Error: {html_path} not found", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(args.output) if args.output else html_path.with_suffix(".pdf")

    html_to_pdf(html_path, pdf_path, args.paper_size)
    print(f"PDF written to: {pdf_path} ({pdf_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
