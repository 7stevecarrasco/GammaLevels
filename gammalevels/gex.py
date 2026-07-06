"""Gamma-exposure (GEX) engine: turn an options chain into dealer hedging levels.

This module is data-source agnostic.  It operates on a normalised chain (a list
of :class:`OptionRow` or an equivalent pandas DataFrame) and produces:

* a GEX-by-strike profile,
* the **zero-gamma flip** (where net dealer gamma crosses zero),
* the **call wall / put wall** (largest positive / negative gamma strikes),
* the **peak absolute-gamma strike** (the biggest hedging magnet),
* a **gamma-weighted centroid** (a smooth, non-round "pressure" level).

Applying these to the *nearest weekly expiry* gives **HP** (weekly hedge
pressure); applying them to the *monthly (3rd-Friday) expiry* gives **MHP**
(monthly hedge pressure).  That single distinction -- which expirations you
feed in -- is the entire difference between the two lines a service like
"Rocket Scooter" posts.

Dealer sign convention (the standard SqueezeMetrics / SpotGamma "naive" model):
dealers are assumed **long call gamma** and **short put gamma**.  Net GEX > 0 ->
dealers dampen volatility (mean-reversion regime); net GEX < 0 -> dealers chase
price (trend/vol-expansion regime).  This assumption only affects *signed*
quantities (net GEX, flip, walls); the absolute-gamma magnet does not depend on
it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Literal, Optional

import numpy as np
import pandas as pd

from .blackscholes import gamma as bs_gamma

# One equity/ETF option contract controls 100 shares.
CONTRACT_MULTIPLIER = 100

OptionType = Literal["C", "P"]


@dataclass(frozen=True)
class OptionRow:
    """A single normalised option line."""

    strike: float
    type: OptionType          # "C" or "P"
    open_interest: float
    iv: float                 # implied volatility as a decimal (0.18 == 18%)
    expiry: date              # expiration date


@dataclass
class GexProfile:
    """The GEX-by-strike profile plus the levels derived from it.

    ``per_strike`` is a DataFrame indexed by strike with columns
    ``call_gex``, ``put_gex``, ``net_gex`` and ``abs_gamma`` (all in dollar
    gamma per 1% move, dealer sign convention applied to the ``*_gex`` cols).
    """

    spot: float
    per_strike: pd.DataFrame
    zero_gamma: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    peak_gamma_strike: Optional[float]
    gamma_centroid: Optional[float]
    net_gex_at_spot: float
    total_gamma_notional: float
    label: str = ""

    def key_level(self, method: str = "peak") -> Optional[float]:
        """Pick the single "hedge-pressure" level for this profile.

        method:
          * ``"peak"``     -> strike with the greatest absolute gamma (magnet)
          * ``"centroid"`` -> gamma-weighted mean strike (smooth, non-round)
          * ``"flip"``     -> zero-gamma flip level
          * ``"callwall"`` / ``"putwall"``
        """
        return {
            "peak": self.peak_gamma_strike,
            "centroid": self.gamma_centroid,
            "flip": self.zero_gamma,
            "callwall": self.call_wall,
            "putwall": self.put_wall,
        }.get(method, self.peak_gamma_strike)


def _year_fraction(expiry: date, asof: datetime) -> float:
    """Time to expiry in years. Options are assumed to expire at 16:00 ET; we
    keep it simple and use calendar days / 365, flooring at a small positive
    value so same-day (0DTE) gamma stays finite rather than exploding."""
    if isinstance(expiry, datetime):
        exp_dt = expiry
    else:
        exp_dt = datetime(expiry.year, expiry.month, expiry.day, 16, 0, 0)
    # Match tz-awareness to asof so tz-aware (e.g. yfinance UTC) and naive
    # callers both work.  Options nominally expire 16:00 ET; treating that
    # clock time as being in asof's frame is close enough for time-to-expiry.
    if asof.tzinfo is not None and exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=asof.tzinfo)
    elif asof.tzinfo is None and exp_dt.tzinfo is not None:
        exp_dt = exp_dt.replace(tzinfo=None)
    seconds = (exp_dt - asof).total_seconds()
    years = seconds / (365.0 * 24 * 3600)
    return max(years, 0.5 / 365.0)  # floor at ~half a day


def _dollar_gamma(g: float, oi: float, spot: float) -> float:
    """Dollar gamma exposure for one strike/side: dealer delta change per 1%
    move.  = gamma * OI * 100 * spot^2 * 0.01."""
    return g * oi * CONTRACT_MULTIPLIER * spot * spot * 0.01


def compute_profile(
    rows: Iterable[OptionRow],
    spot: float,
    asof: Optional[datetime] = None,
    r: float = 0.0,
    q: float = 0.0,
    label: str = "",
) -> GexProfile:
    """Build a :class:`GexProfile` from a normalised chain at a given spot."""
    if asof is None:
        # Callers should pass asof explicitly; fall back to naive "now" only
        # when running interactively.
        asof = datetime.now()

    rows = list(rows)
    strikes: dict[float, dict[str, float]] = {}

    for row in rows:
        if row.open_interest is None or row.iv is None or row.iv <= 0:
            continue
        t = _year_fraction(row.expiry, asof)
        g = bs_gamma(spot, row.strike, t, row.iv, r, q)
        if g <= 0:
            continue
        dollar_g = _dollar_gamma(g, row.open_interest, spot)
        bucket = strikes.setdefault(
            row.strike, {"call_gex": 0.0, "put_gex": 0.0, "abs_gamma": 0.0}
        )
        if row.type == "C":
            bucket["call_gex"] += dollar_g          # dealers long call gamma (+)
        else:
            bucket["put_gex"] -= dollar_g           # dealers short put gamma (-)
        bucket["abs_gamma"] += dollar_g             # unsigned magnet size

    if not strikes:
        return GexProfile(spot, pd.DataFrame(), None, None, None, None, None, 0.0, 0.0, label)

    df = (
        pd.DataFrame.from_dict(strikes, orient="index")
        .sort_index()
        .rename_axis("strike")
    )
    df["net_gex"] = df["call_gex"] + df["put_gex"]

    call_wall = df["call_gex"].idxmax() if df["call_gex"].max() > 0 else None
    put_wall = df["put_gex"].idxmin() if df["put_gex"].min() < 0 else None
    peak_gamma_strike = df["abs_gamma"].idxmax()
    gamma_centroid = float((df.index.to_numpy() * df["abs_gamma"]).sum() / df["abs_gamma"].sum())
    net_gex_at_spot = float(df["net_gex"].sum())
    total_gamma_notional = float(df["abs_gamma"].sum())
    zero_gamma = _zero_gamma_flip(rows, spot, asof, r, q)

    return GexProfile(
        spot=spot,
        per_strike=df,
        zero_gamma=zero_gamma,
        call_wall=None if call_wall is None else float(call_wall),
        put_wall=None if put_wall is None else float(put_wall),
        peak_gamma_strike=float(peak_gamma_strike),
        gamma_centroid=gamma_centroid,
        net_gex_at_spot=net_gex_at_spot,
        total_gamma_notional=total_gamma_notional,
        label=label,
    )


def _net_gex_at(rows: list[OptionRow], test_spot: float, asof: datetime, r: float, q: float) -> float:
    """Net signed dollar-gamma if the underlying were at ``test_spot``.

    Gamma is recomputed at the hypothetical spot; IV/OI are held fixed (the
    standard flip-point approximation)."""
    total = 0.0
    for row in rows:
        if row.iv is None or row.iv <= 0 or row.open_interest is None:
            continue
        t = _year_fraction(row.expiry, asof)
        g = bs_gamma(test_spot, row.strike, t, row.iv, r, q)
        dollar_g = _dollar_gamma(g, row.open_interest, test_spot)
        total += dollar_g if row.type == "C" else -dollar_g
    return total


def _zero_gamma_flip(
    rows: list[OptionRow], spot: float, asof: datetime, r: float, q: float,
    lo_mult: float = 0.85, hi_mult: float = 1.15, steps: int = 240,
) -> Optional[float]:
    """Find the spot at which net dealer gamma crosses zero (the "gamma flip").

    We scan a grid of hypothetical spots around the current price and locate a
    sign change in net GEX, then linearly interpolate the crossing.  Returns the
    crossing nearest the current spot, or ``None`` if net gamma keeps one sign
    across the whole range."""
    grid = np.linspace(spot * lo_mult, spot * hi_mult, steps)
    vals = np.array([_net_gex_at(rows, s, asof, r, q) for s in grid])

    crossings: list[float] = []
    for i in range(len(grid) - 1):
        a, b = vals[i], vals[i + 1]
        if a == 0:
            crossings.append(grid[i])
        elif a * b < 0:  # sign change between grid[i] and grid[i+1]
            frac = a / (a - b)
            crossings.append(grid[i] + frac * (grid[i + 1] - grid[i]))
    if not crossings:
        return None
    return float(min(crossings, key=lambda x: abs(x - spot)))
