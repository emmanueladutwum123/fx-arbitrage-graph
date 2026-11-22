"""Export the deck to PDF with headless Chrome only (no extra downloads).

* slides/fx-arbitrage-slides.pdf: one 1280x720 page per slide (rendered screenshots, a
  projector backup).
* slides/fx-arbitrage-speaker-notes.pdf: the speaker script with timings, as printable text.

Usage: python scripts/export_slides_pdf.py [--chrome PATH]   (needs Pillow)
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "slides" / "index.html"
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def chrome(binary: str, *args: str) -> None:
    subprocess.run(
        [binary, "--headless=new", "--disable-gpu", "--hide-scrollbars", *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=MAC_CHROME)
    a = ap.parse_args()
    src = DECK.read_text(encoding="utf-8")
    n = len(re.findall(r"<section[\s>]", src))

    with tempfile.TemporaryDirectory() as tmp:
        shots = []
        for i in range(n):
            png = Path(tmp) / f"s{i:02d}.png"
            chrome(
                a.chrome,
                "--window-size=1280,720",
                "--virtual-time-budget=4000",
                f"--screenshot={png}",
                f"{DECK.as_uri()}#/{i}",
            )
            shots.append(Image.open(png).convert("RGB"))
        out = DECK.parent / "fx-arbitrage-slides.pdf"
        shots[0].save(out, save_all=True, append_images=shots[1:], resolution=96)
        print(f"wrote {out} ({n} pages)")

        # Speaker script: titles + notes, printed as a plain document.
        parts = []
        for k, sec in enumerate(re.findall(r"<section[^>]*>(.*?)</section>", src, re.S), 1):
            title = re.search(r"<h[12][^>]*>(.*?)</h[12]>", sec, re.S)
            notes = re.search(r'<aside class="notes">(.*?)</aside>', sec, re.S)
            t = re.sub(r"<[^>]+>", "", title[1]) if title else f"Slide {k}"
            t = re.sub(r"\\\(|\\\)", "", t)
            parts.append(f"<h2>{k}. {html.escape(html.unescape(t))}</h2>{notes[1] if notes else ''}")
        page = Path(tmp) / "notes.html"
        page.write_text(
            "<!DOCTYPE html><meta charset=utf-8><title>Speaker notes</title><style>"
            "body{font:12pt/1.45 Georgia,serif;max-width:42em;margin:2em auto}"
            "h1{font:bold 18pt system-ui}h2{font:bold 13pt system-ui;margin-top:1.4em}"
            ".timing{font:bold 10pt ui-monospace,monospace;color:#22628a}</style>"
            "<h1>Arbitrage as a Negative Cycle: speaker script (18:00 at ~130 wpm)</h1>" + "".join(parts),
            encoding="utf-8",
        )
        notes_pdf = DECK.parent / "fx-arbitrage-speaker-notes.pdf"
        chrome(a.chrome, "--no-pdf-header-footer", f"--print-to-pdf={notes_pdf}", page.as_uri())
        print(f"wrote {notes_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
