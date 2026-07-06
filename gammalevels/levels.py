"""High-level orchestration: pick expirations, compute HP / MHP and friends.

``compute_hedge_levels`` is the one function the dashboard and CLI call.  It
takes a normalised chain (all expirations), splits it into a *weekly* bucket
and a *monthly* bucket, runs the GEX engine on each, and returns a tidy
:class:`HedgeLevels` result with HP (weekly) and MHP (monthly) plus the walls
and flips that back them up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from .gex import GexProfile, OptionRow, compute_profile


def third_friday(year: int, month: int) -> date:
    """Date of the standard monthly options expiry (3rd Friday) for a month."""
    d = date(year, month, 1)
    # weekday(): Mon=0 .. Sun=6 ; Friday == 4
    first_friday = d + timedelta(days=(4 - d.weekday()) % 7)
    return first_friday + timedelta(weeks=2)


def is_monthly_expiry(exp: date) -> bool:
    """True if ``exp`` is a 3rd-Friday monthly expiration."""
    return exp == third_friday(exp.year, exp.month)


def pick_weekly_expiry(expiries: Sequence[date], asof: date) -> Optional[date]:
    """Nearest upcoming expiration on/after ``asof`` -- the weekly bucket."""
    future = sorted(e for e in expiries if e >= asof)
    return future[0] if future else None


def pick_monthly_expiry(expiries: Sequence[date], asof: date) -> Optional[date]:
    """Nearest upcoming 3rd-Friday monthly expiration on/after ``asof``.

    Falls back to the nearest monthly among all available if none is in the
    future (rare)."""
    monthlies = sorted(e for e in expiries if is_monthly_expiry(e))
    future = [e for e in monthlies if e >= asof]
    if future:
        return future[0]
    return monthlies[-1] if monthlies else None


@dataclass
class HedgeLevels:
    """The full result: HP, MHP, and the supporting structure for each."""

    spot: float
    asof: datetime
    weekly_expiry: Optional[date]
    monthly_expiry: Optional[date]
    weekly: Optional[GexProfile]
    monthly: Optional[GexProfile]
    method: str

    @property
    def hp(self) -> Optional[float]:
        """Weekly hedge pressure."""
        return self.weekly.key_level(self.method) if self.weekly else None

    @property
    def mhp(self) -> Optional[float]:
        """Monthly hedge pressure."""
        return self.monthly.key_level(self.method) if self.monthly else None

    def scaled(self, factor: float) -> dict:
        """Return the headline levels multiplied by ``factor`` (e.g. QQQ->NQ).

        Returns a plain dict so it is easy to serialise / draw on a chart."""
        def s(v):
            return None if v is None else round(v * factor, 2)

        return {
            "hp": s(self.hp),
            "mhp": s(self.mhp),
            "spot": s(self.spot),
            "weekly_call_wall": s(self.weekly.call_wall) if self.weekly else None,
            "weekly_put_wall": s(self.weekly.put_wall) if self.weekly else None,
            "weekly_zero_gamma": s(self.weekly.zero_gamma) if self.weekly else None,
            "monthly_call_wall": s(self.monthly.call_wall) if self.monthly else None,
            "monthly_put_wall": s(self.monthly.put_wall) if self.monthly else None,
            "monthly_zero_gamma": s(self.monthly.zero_gamma) if self.monthly else None,
        }


def compute_hedge_levels(
    rows: Sequence[OptionRow],
    spot: float,
    asof: Optional[datetime] = None,
    method: str = "peak",
    r: float = 0.0,
    q: float = 0.0,
) -> HedgeLevels:
    """Split the chain into weekly / monthly buckets and compute HP & MHP.

    method: which level definition to use for HP/MHP -- see
    :meth:`GexProfile.key_level` ("peak", "centroid", "flip", ...).
    """
    if asof is None:
        asof = datetime.now()

    expiries = sorted({row.expiry for row in rows})
    weekly_exp = pick_weekly_expiry(expiries, asof.date())
    monthly_exp = pick_monthly_expiry(expiries, asof.date())

    weekly_profile = None
    if weekly_exp is not None:
        weekly_rows = [row for row in rows if row.expiry == weekly_exp]
        weekly_profile = compute_profile(
            weekly_rows, spot, asof, r, q, label=f"Weekly {weekly_exp:%Y-%m-%d}"
        )

    monthly_profile = None
    if monthly_exp is not None:
        monthly_rows = [row for row in rows if row.expiry == monthly_exp]
        monthly_profile = compute_profile(
            monthly_rows, spot, asof, r, q, label=f"Monthly {monthly_exp:%Y-%m-%d}"
        )

    return HedgeLevels(
        spot=spot,
        asof=asof,
        weekly_expiry=weekly_exp,
        monthly_expiry=monthly_exp,
        weekly=weekly_profile,
        monthly=monthly_profile,
        method=method,
    )
