"""Dump extracted PDF text to statements/extracted/*.txt mirroring inbox structure."""
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
    out = []
    for i, page in enumerate(reader.pages, 1):
        out.append(f"\n===== PAGE {i} =====\n")
        try:
            out.append(page.extract_text() or "")
        except Exception as exc:
            out.append(f"<page error: {exc}>")
    return "".join(out)


def main() -> int:
    root = Path("statements/inbox")
    dest = Path("statements/extracted")
    for pdf in sorted(root.rglob("*.pdf")):
        rel = pdf.relative_to(root)
        target = dest / rel.with_suffix(".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_mtime >= pdf.stat().st_mtime:
            continue
        try:
            target.write_text(text_of(pdf), encoding="utf-8")
        except Exception as exc:
            print(f"FAIL {rel}: {exc}")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
