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
from .data import ChainSnapshot, fetch_yfinance_chain, qqq_to_nq_factor

__all__ = [
    "gamma",
    "OptionRow",
    "GexProfile",
    "compute_profile",
    "HedgeLevels",
    "compute_hedge_levels",
    "ChainSnapshot",
    "fetch_yfinance_chain",
    "qqq_to_nq_factor",
]

__version__ = "0.1.0"
