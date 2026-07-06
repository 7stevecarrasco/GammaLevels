"""GammaLevels -- reproduce dealer gamma-hedging levels (HP / MHP) yourself.

Public API:

    from gammalevels import compute_hedge_levels, fetch_yfinance_chain

    snap = fetch_yfinance_chain("QQQ")
    levels = compute_hedge_levels(snap.rows, snap.spot, snap.asof, method="peak")
    print("HP :", levels.hp)    # weekly hedge pressure
    print("MHP:", levels.mhp)   # monthly hedge pressure
"""

from .blackscholes import gamma
from .gex import GexProfile, OptionRow, compute_profile
from .levels import HedgeLevels, compute_hedge_levels
from .data import (
    ChainSnapshot,
    FutureLevelsInput,
    fetch_chain_for_future,
    fetch_future_price,
    fetch_yfinance_chain,
    qqq_to_nq_factor,
    scale_factor,
    FUTURE_MAP,
)

__all__ = [
    "gamma",
    "OptionRow",
    "GexProfile",
    "compute_profile",
    "HedgeLevels",
    "compute_hedge_levels",
    "ChainSnapshot",
    "FutureLevelsInput",
    "fetch_yfinance_chain",
    "fetch_chain_for_future",
    "fetch_future_price",
    "qqq_to_nq_factor",
    "scale_factor",
    "FUTURE_MAP",
]

__version__ = "0.1.0"
