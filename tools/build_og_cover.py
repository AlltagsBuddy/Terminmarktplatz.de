#!/usr/bin/env python3
"""
Erzeugt static/og-cover.jpg (1200×630, kompakt) für Link-Vorschauen (Facebook/Meta).

Quelle: Produktlogo per URL – bei Logo-Änderung Skript neu ausführen und Committen.

  python tools/build_og_cover.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "static" / "og-cover.jpg"

# Produktlogo (hochauflösendes PNG)
LOGO_URL = "https://terminmarktplatz.de/static/terminmarktplatz-logo.png"

W, H = 1200, 630
TOP = (111, 83, 255)
BOTTOM = (11, 16, 32)


def _gradient_rgb() -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        u = y / max(H - 1, 1)
        r = int(TOP[0] * (1 - u) + BOTTOM[0] * u)
        g = int(TOP[1] * (1 - u) + BOTTOM[1] * u)
        b = int(TOP[2] * (1 - u) + BOTTOM[2] * u)
        for x in range(W):
            px[x, y] = (r, g, b)
    return img


def main() -> int:
    print("Fetching logo:", LOGO_URL, flush=True)
    data = urllib.request.urlopen(LOGO_URL, timeout=60).read()
    logo = Image.open(io.BytesIO(data)).convert("RGBA")

    base = _gradient_rgb().convert("RGBA")
    lw, lh = logo.size
    target_max = min(560, lw, lh)
    scale = target_max / max(lw, lh)
    new_w = max(1, int(lw * scale))
    new_h = max(1, int(lh * scale))
    logo_r = logo.resize((new_w, new_h), Image.Resampling.LANCZOS)

    ox = (W - new_w) // 2
    oy = (H - new_h) // 2
    base.paste(logo_r, (ox, oy), logo_r)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rgb = base.convert("RGB")
    rgb.save(OUTPUT, format="JPEG", quality=88, optimize=True, progressive=True)
    print("Wrote", OUTPUT, OUTPUT.stat().st_size // 1024, "KiB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
