#!/usr/bin/env python3
"""Reverse-engineer the published HP/MHP levels from a table of observations.

Feed it ``observations.csv`` (each row: a day's published HP/MHP for a symbol).
It runs a battery of pattern tests to see whether the levels reduce to a
deterministic price formula -- and if so, which one:

  1. Symmetry     : is (HP+MHP)/2 a stable "center"? What is it anchored to?
  2. Half-width   : is (HP-MHP)/2 constant, a % of price, or driven by something?
  3. Round-number : do HP/MHP / center snap to 5 / 10 / 25 / 50 / 100 grids?
  4. Cross-symbol : for days with both NQ and ES, is there a fixed ratio?

The verdict we're hunting:
  * A tight, stable pattern  -> the "proprietary" levels are a formula; we crack it.
  * No stable pattern        -> they're genuinely options/gamma-derived; we then
                                need historical options data, not a spreadsheet.

Usage:  python research/reverse_engineer.py [observations.csv]
No network needed.
"""

from __future__ import annotations

import csv
import os
import statistics
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Obs:
    date: str
    symbol: str
    price: Optional[float]
    whp: float
    mhp: float
    notes: str = ""

    @property
    def center(self) -> float:
        return (self.whp + self.mhp) / 2.0

    @property
    def half_width(self) -> float:
        return abs(self.whp - self.mhp) / 2.0

    @property
    def width(self) -> float:
        return abs(self.whp - self.mhp)


def load(path: str) -> List[Obs]:
    rows: List[Obs] = []
    with open(path) as fh:
        # skip leading comment lines starting with '#'
        lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    for r in reader:
        try:
            whp = float(r["whp"]); mhp = float(r["mhp"])
        except (KeyError, ValueError):
            continue
        price = None
        try:
            price = float(r["price_at_post"]) if r.get("price_at_post") else None
        except ValueError:
            price = None
        rows.append(Obs(r.get("date", ""), r.get("symbol", "").upper(), price, whp, mhp, r.get("notes", "")))
    return rows


def _grid_hits(value: float, grids=(100, 50, 25, 10, 5, 1)) -> Optional[float]:
    """Return the coarsest grid the value lands on (within 0.01), else None."""
    for g in grids:
        if abs(value / g - round(value / g)) * g <= 0.01:
            return g
    return None


def _cv(xs: List[float]) -> Optional[float]:
    """Coefficient of variation (std/mean) -- low means 'basically constant'."""
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = statistics.mean(xs)
    if m == 0:
        return None
    return statistics.pstdev(xs) / m


def analyze(rows: List[Obs]) -> None:
    print(f"Loaded {len(rows)} observation(s).\n")
    if not rows:
        print("No data yet -- add rows to observations.csv.")
        return

    # ---- per-observation decomposition
    print("Per-observation decomposition (HP = center + half, MHP = center - half):")
    print(f"  {'date':11s} {'sym':4s} {'price':>10s} {'HP':>10s} {'MHP':>10s} "
          f"{'center':>10s} {'half':>8s} {'width%':>7s} {'grid':>5s}")
    for o in rows:
        gh = _grid_hits(o.half_width)
        wpct = (o.width / o.price * 100) if o.price else float("nan")
        cdisp = f"{o.center:.2f}"
        print(f"  {o.date:11s} {o.symbol:4s} "
              f"{('%.2f'%o.price) if o.price else '?':>10s} "
              f"{o.whp:>10.2f} {o.mhp:>10.2f} {cdisp:>10s} {o.half_width:>8.2f} "
              f"{wpct:>6.2f}% {('%g'%gh) if gh else '-':>5s}")
    print()

    if len(rows) < 3:
        print("Need at least ~3-5 observations before aggregate patterns mean anything.")
        print("Send more screenshots; every added day sharpens the tests below.\n")

    # ---- 1. symmetry / center anchor
    print("== Test 1: symmetry & center anchor ==")
    centered_offsets = [o.center - o.price for o in rows if o.price is not None]
    if centered_offsets:
        cv = _cv([abs(x) for x in centered_offsets]) if len(centered_offsets) > 1 else None
        print(f"  center - price : {[round(x,2) for x in centered_offsets]}")
        if len(centered_offsets) > 1:
            print(f"    mean={statistics.mean(centered_offsets):+.2f}  "
                  f"stdev={statistics.pstdev(centered_offsets):.2f}")
        print("    -> if center-price is ~constant, the levels are centered on price "
              "(or a fixed offset from it).")
    else:
        print("  (no price_at_post values yet -- fill those in to test the anchor.)")
    print()

    # ---- 2. half-width behaviour
    print("== Test 2: half-width (the +/- offset) ==")
    halves = [o.half_width for o in rows]
    print(f"  half-widths: {[round(h,2) for h in halves]}")
    cv_abs = _cv(halves)
    if cv_abs is not None:
        print(f"    absolute: mean={statistics.mean(halves):.2f}  CV={cv_abs:.3f} "
              f"({'~CONSTANT' if cv_abs < 0.10 else 'varies'})")
    pcts = [o.half_width / o.price for o in rows if o.price]
    cv_pct = _cv(pcts)
    if cv_pct is not None:
        print(f"    as % of price: mean={statistics.mean(pcts)*100:.3f}%  CV={cv_pct:.3f} "
              f"({'~CONSTANT %' if cv_pct < 0.10 else 'varies'})")
    print("    -> low CV on either line means we've found the offset rule.")
    print()

    # ---- 3. round-number grid
    print("== Test 3: round-number snapping ==")
    for label, vals in (("HP", [o.whp for o in rows]),
                        ("MHP", [o.mhp for o in rows]),
                        ("center", [o.center for o in rows])):
        grids = [_grid_hits(v) for v in vals]
        named = [f"{g:g}" if g else "-" for g in grids]
        print(f"  {label:6s}: {named}")
    print("    -> if 'center' consistently snaps to a coarse grid, that's the anchor.")
    print()

    # ---- 4. cross-symbol ratio (needs same-day NQ & ES)
    print("== Test 4: NQ vs ES relationship (same-day) ==")
    by_date: dict[str, dict[str, Obs]] = {}
    for o in rows:
        by_date.setdefault(o.date, {})[o.symbol] = o
    pairs = [(d, m) for d, m in by_date.items() if "NQ" in m and "ES" in m]
    if not pairs:
        print("  (no day yet with BOTH NQ and ES -- send a matched pair to unlock this.)")
    else:
        for d, m in pairs:
            r_center = m["NQ"].center / m["ES"].center
            r_half = m["NQ"].half_width / m["ES"].half_width
            print(f"  {d}: NQ/ES center ratio={r_center:.4f}  half-width ratio={r_half:.4f}")
        print("    -> a stable center ratio ~ the NQ/ES index ratio; a matching "
              "half-width ratio would mean one shared % offset drives both.")
    print()

    print("Verdict guidance:")
    print("  * Any test above going ~CONSTANT across many days  => formula found, we reproduce it.")
    print("  * All tests keep varying with no driver             => truly options-derived;")
    print("    next step is historical NDX/QQQ options data, not more screenshots.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "observations.csv")
    analyze(load(path))
