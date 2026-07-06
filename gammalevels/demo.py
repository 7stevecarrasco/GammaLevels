"""Offline demo data so the pipeline runs with no network (self-test / previews).

Real runs pull live options via yfinance; a locked-down sandbox (or a plane)
blocks that.  This module fabricates a *plausible* options chain and future
price so ``daily_levels.py --demo`` exercises the whole path end-to-end and you
can see the real output shape before trusting live numbers.

The chain is deterministic (no RNG): OI is concentrated on round strikes with a
couple of deliberate gamma "walls", and the weekly vs monthly peaks are placed
at slightly different strikes so HP and MHP come out distinct -- exactly like a
real day.  Numbers are anchored to the 2026-03-11 screenshot so the demo lands
in a familiar range.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from .data import FutureLevelsInput, ChainSnapshot, scale_factor
from .gex import OptionRow

# Anchored to the 2026-03-11 screenshots (NDX~NQ, SPX~ES).
_DEMO = {
    "NQ": {"underlying": "^NDX", "spot": 24950.0, "future_price": 24945.50,
           "step": 25.0, "weekly_wall": 25100.0, "monthly_wall": 24975.0},
    "ES": {"underlying": "^SPX", "spot": 6772.0, "future_price": 6769.75,
           "step": 5.0, "weekly_wall": 6790.0, "monthly_wall": 6765.0},
}

_ASOF = datetime(2026, 3, 11, 22, 55, tzinfo=timezone.utc)  # ~5:55pm ET
_WEEKLY = date(2026, 3, 13)    # nearest Friday
_MONTHLY = date(2026, 3, 20)   # 3rd Friday


def _build_chain(cfg) -> list[OptionRow]:
    spot = cfg["spot"]
    step = cfg["step"]
    rows: list[OptionRow] = []
    lo = spot - 40 * step
    hi = spot + 40 * step
    for exp, wall in ((_WEEKLY, cfg["weekly_wall"]), (_MONTHLY, cfg["monthly_wall"])):
        k = lo
        while k <= hi:
            moneyness = abs(k - spot) / spot
            iv = 0.14 + 4.0 * moneyness            # simple smile
            # base OI: heavier on round strikes, tapering away from spot
            base = 1500.0 if (k % (step * 4) == 0) else 400.0
            base *= max(0.15, 1.0 - 6.0 * moneyness)
            # a deliberate gamma wall for this expiry
            wall_boost = 9000.0 if abs(k - wall) < step / 2 else 0.0
            call_oi = base + wall_boost + max(0.0, (k - spot) / step) * 60
            put_oi = base + max(0.0, (spot - k) / step) * 60
            rows.append(OptionRow(round(k, 2), "C", round(call_oi), iv, exp))
            rows.append(OptionRow(round(k, 2), "P", round(put_oi), iv, exp))
            k += step
    return rows


def demo_input(future: str) -> FutureLevelsInput:
    """A FutureLevelsInput for 'NQ' or 'ES', built entirely offline."""
    future = future.upper()
    if future not in _DEMO:
        raise ValueError(f"no demo for {future!r}; have {list(_DEMO)}")
    cfg = _DEMO[future]
    snap = ChainSnapshot(cfg["underlying"], cfg["spot"], _ASOF, _build_chain(cfg))
    factor = scale_factor(cfg["spot"], cfg["future_price"])
    return FutureLevelsInput(
        future=future, future_price=cfg["future_price"],
        underlying=cfg["underlying"], snapshot=snap, factor=factor,
    )
