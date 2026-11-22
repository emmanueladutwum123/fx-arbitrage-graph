"""Wrap web/data/snapshot.json as a <script> so the demo also works from file:// (offline)."""

from __future__ import annotations

import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else "web/data/snapshot.json")
dst = src.with_suffix(".js")
dst.write_text("window.FXARB_SNAPSHOT = " + src.read_text().strip() + ";\n", encoding="utf-8")
print(f"wrote {dst} ({dst.stat().st_size:,} bytes)")
