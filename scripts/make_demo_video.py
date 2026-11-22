"""Build a captioned 1080p walkthrough video of the web demo (a backup for the live demo).

Each scene is the real demo page rendered by headless Chrome in a given state (URL
parameters), held for a few seconds with a caption, then encoded with ffmpeg.

Usage: python scripts/make_demo_video.py [--chrome PATH] [--out docs/video/demo-walkthrough.mp4]
Needs Pillow and ffmpeg.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "web" / "index.html").as_uri()
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H, BAR = 1920, 1080, 110
FPS = 30

# (query string, seconds, caption)
SCENES: list[tuple[str, float, str]] = [
    (
        "scen=fair&step=0&focus=graph",
        5,
        "Five currencies, 20 directed quotes. Every distance starts at 0 (virtual source).",
    ),
    (
        "scen=fair&step=1&focus=graph",
        4,
        "Fair market, round 1: relax every edge once. Several distances drop.",
    ),
    (
        "scen=fair&step=2&focus=graph",
        5,
        "Round 2 changes nothing, so the distances are final: no negative cycle, no arbitrage.",
    ),
    (
        "scen=bad&step=0&focus=graph",
        4,
        "Now mispriced: EUR→JPY quoted 0.8% too high (highlighted in the matrix below).",
    ),
    ("scen=bad&step=1&focus=graph", 3, "Round 1: distances drop."),
    ("scen=bad&step=2&focus=graph", 3, "Round 2: still dropping."),
    ("scen=bad&step=3&focus=graph", 3, "Round 3: still dropping."),
    (
        "scen=bad&step=4&focus=graph",
        4,
        "Round 4 = n−1: a shortest path has at most 4 edges, so this should be the end...",
    ),
    (
        "scen=bad&step=5&focus=graph",
        6,
        "Round 5 (the check) still improves JPY: a negative cycle exists. Predecessors give GHS → EUR → JPY → GHS.",
    ),
    (
        "scen=bad&step=5&focus=trade",
        7,
        "The trade: rates multiply to 1.0065 > 1, weights sum to −0.0065 < 0. Same fact, two ways.",
    ),
    (
        "mode=live&focus=live",
        7,
        "Live snapshot: real Kraken + Binance.US best bid/ask, ~700 assets, ~3,000 edges, taker fees.",
    ),
    (
        "mode=live&fees=zero&focus=live",
        7,
        "Same snapshot with zero fees: 8 small cycles appear; most are worth under a cent, the largest about $1.77.",
    ),
    (
        "mode=live&fees=zero&cyc=1&focus=live",
        5,
        "Each cycle shows its legs, the tightest leg, and the fee per leg that would erase it.",
    ),
    (
        "mode=live&focus=live",
        6,
        "Back to real taker fees: Bellman–Ford stops after a few rounds. No arbitrage. Fees close the gaps.",
    ),
]


def render(chrome: str, query: str, out: Path) -> None:
    """Screenshot the page in one state. Each call gets a fresh profile; Chrome occasionally
    can exit non-zero after a successful capture, or fail outright; retry a couple of times."""
    for attempt in range(3):
        with tempfile.TemporaryDirectory() as profile:
            r = subprocess.run(
                [
                    chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--user-data-dir={profile}", f"--window-size={W * 4 // 5},{(H - BAR) * 4 // 5}",
                    "--force-device-scale-factor=1.25",
                    "--virtual-time-budget=4000", f"--screenshot={out}", f"{PAGE}?{query}",
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
            )  # fmt: skip
        # Chrome sometimes crashes during teardown *after* writing the screenshot (non-zero
        # exit), so success means "the image exists and opens".
        if out.exists() and out.stat().st_size > 0:
            try:
                Image.open(out).verify()
                return
            except OSError:
                pass
        print(f"  chrome exited {r.returncode} on {query!r} (attempt {attempt + 1})")
    raise RuntimeError(f"could not render {query!r}")


def caption(img: Path, text: str, k: int, n: int) -> Image.Image:
    page = Image.open(img).convert("RGB").resize((W, H - BAR), Image.LANCZOS)
    frame = Image.new("RGB", (W, H), (20, 33, 46))
    frame.paste(page, (0, 0))
    d = ImageDraw.Draw(frame)
    font = None
    for f in (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            font = ImageFont.truetype(f, 36)
            small = ImageFont.truetype(f, 22)
            break
        except OSError:
            continue
    if font is None:
        font = small = ImageFont.load_default()
    d.text((40, H - BAR + 22), text, fill=(240, 244, 248), font=font)
    d.text(
        (W - 40, H - BAR + 72), f"fx-arbitrage-graph · {k}/{n}", fill=(150, 170, 190), font=small, anchor="ra"
    )
    return frame


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=MAC_CHROME)
    ap.add_argument("--out", default=str(ROOT / "docs" / "video" / "demo-walkthrough.mp4"))
    a = ap.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        lst = Path(tmp) / "list.txt"
        lines = []
        for k, (q, secs, text) in enumerate(SCENES, 1):
            raw = Path(tmp) / f"raw{k:02d}.png"
            render(a.chrome, q, raw)
            fr = Path(tmp) / f"f{k:02d}.png"
            caption(raw, text, k, len(SCENES)).save(fr)
            lines += [f"file '{fr}'", f"duration {secs}"]
            print(f"scene {k}/{len(SCENES)}: {q}")
        lines.append(f"file '{Path(tmp) / f'f{len(SCENES):02d}.png'}'")  # concat demuxer quirk
        lst.write_text("\n".join(lines) + "\n")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
             "-movflags", "+faststart", str(out)],
            check=True,
        )  # fmt: skip
    total = sum(s for _, s, _ in SCENES)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {total:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
