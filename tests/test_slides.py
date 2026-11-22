"""Speaker notes: timings add to exactly 18:00, running totals are right, and each slide's
script is long enough for its time at ~130 words per minute."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

DECK = Path(__file__).resolve().parents[1] / "slides" / "index.html"
WPM = 130
TOLERANCE = 0.06  # each slide within ±6% of its word budget


class Notes(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.cur: list[str] | None = None
        self.timing = False
        self.slides: list[tuple[str, str]] = []  # (timing line, script)
        self._t = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "aside" and "notes" in (a.get("class") or ""):
            self.cur, self._t = [], ""
        elif self.cur is not None and tag == "p" and a.get("class") == "timing":
            self.timing = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "aside" and self.cur is not None:
            self.slides.append((self._t, " ".join(self.cur)))
            self.cur = None
        elif tag == "p":
            self.timing = False

    def handle_data(self, data: str) -> None:
        if self.cur is None:
            return
        if self.timing:
            self._t += data
        else:
            self.cur.append(data)


def parse() -> list[tuple[int, int, int]]:
    p = Notes()
    p.feed(DECK.read_text(encoding="utf-8"))
    out = []
    for timing, script in p.slides:
        m = re.search(r"Time (\d+):(\d\d) · running total (\d+):(\d\d)", timing)
        assert m, f"missing timing line: {timing!r}"
        secs = int(m[1]) * 60 + int(m[2])
        total = int(m[3]) * 60 + int(m[4])
        words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.,–-]*", script))
        out.append((secs, total, words))
    return out


def test_deck_has_no_placeholders() -> None:
    assert "REAL_DATA_" not in DECK.read_text(encoding="utf-8")


def test_timings_sum_to_18_minutes_with_correct_running_totals() -> None:
    slides = parse()
    running = 0
    for secs, total, _ in slides:
        running += secs
        assert total == running
    assert running == 18 * 60


@pytest.mark.parametrize("i", range(len(parse())))
def test_script_length_matches_time(i: int) -> None:
    secs, _, words = parse()[i]
    target = WPM * secs / 60
    assert abs(words - target) <= TOLERANCE * target, f"slide {i + 1}: {words} words, target {target:.0f}"
