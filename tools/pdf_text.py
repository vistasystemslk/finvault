"""Extract text from statement PDFs so it can be inspected/imported.

Usage:
    python tools/pdf_text.py statements/inbox            # summary of every PDF
    python tools/pdf_text.py statements/inbox/sey.pdf    # full text of one PDF
    python tools/pdf_text.py statements/inbox --lengths  # page text lengths only
"""
from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader


def text_of(path: Path) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return ""
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    target = Path(sys.argv[1])
    lengths_only = "--lengths" in sys.argv

    if target.is_file():
        text = text_of(target)
        print(text)
        return 0

    for pdf in sorted(target.rglob("*.pdf")):
        try:
            text = text_of(pdf)
        except Exception as exc:
            print(f"{pdf.name}: ERROR {exc}")
            continue
        rel = pdf.relative_to(target)
        if lengths_only:
            print(f"{rel}: {len(text)} chars")
        else:
            print(f"{rel}: {len(text)} chars, {len(text.splitlines())} lines, first line: {text.strip().splitlines()[0][:70] if text.strip() else '<no text>'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
