"""Generate the FinVault application icon (assets/FinVault.ico) with Pillow."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "FinVault.ico"


def gradient(size: int) -> Image.Image:
    """Diagonal indigo -> cyan gradient, matching the in-app brand mark."""
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    start = (129, 140, 248)   # #818cf8
    mid = (99, 102, 241)      # #6366f1
    end = (6, 182, 212)       # #06b6d4
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1)) if size > 1 else 0.0
            if t < 0.55:
                k = t / 0.55
                color = tuple(round(start[i] + (mid[i] - start[i]) * k) for i in range(3))
            else:
                k = (t - 0.55) / 0.45
                color = tuple(round(mid[i] + (end[i] - mid[i]) * k) for i in range(3))
            pixels[x, y] = (*color, 255)
    return image


def render(size: int) -> Image.Image:
    scale = 8
    canvas = size * scale
    base = gradient(canvas)

    mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, canvas - 1, canvas - 1), radius=int(canvas * 0.27), fill=255
    )
    icon = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    icon.paste(base, (0, 0), mask)

    draw = ImageDraw.Draw(icon)
    # White "F" glyph drawn as geometry so no font is required.
    left = canvas * 0.30
    top = canvas * 0.26
    stem_w = canvas * 0.115
    height = canvas * 0.48
    draw.rounded_rectangle(
        (left, top, left + stem_w, top + height), radius=canvas * 0.02, fill=(255, 255, 255, 235)
    )
    arm_h = canvas * 0.098
    draw.rounded_rectangle(
        (left, top, left + canvas * 0.38, top + arm_h), radius=canvas * 0.02, fill=(255, 255, 255, 235)
    )
    draw.rounded_rectangle(
        (left, top + canvas * 0.185, left + canvas * 0.30, top + canvas * 0.185 + arm_h),
        radius=canvas * 0.02, fill=(255, 255, 255, 235)
    )
    # Accent dot, like the brand mark.
    dot_r = canvas * 0.052
    cx, cy = canvas * 0.735, canvas * 0.735
    draw.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=(255, 255, 255, 190))

    return icon.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [render(size) for size in sizes]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    # Also keep a high-resolution PNG for docs and shortcuts.
    frames[-1].save(OUT.with_suffix(".png"))
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
