"""Data adapters: fetch a normalised options chain for the GEX engine.

The default adapter uses **yfinance** (free) to pull the QQQ options chain.
QQQ is used as the liquid proxy for the Nasdaq-100; its strikes are scaled onto
the /NQ future via the live QQQ->NQ ratio (see :func:`qqq_to_nq_factor`).

The engine itself only needs a list of :class:`~gammalevels.gex.OptionRow`, so
swapping in a paid feed (Polygon, Theta, tastytrade, IBKR) later means writing
one more function that returns the same shape -- nothing downstream changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional, Tuple

from .gex import OptionRow


@dataclass
class ChainSnapshot:
    """A point-in-time chain plus the spot it was taken at."""

    symbol: str
    spot: float
    asof: datetime
    rows: List[OptionRow]

    @property
    def num_expiries(self) -> int:
        return len({r.expiry for r in self.rows})


def _parse_expiry(exp_str: str) -> date:
    return datetime.strptime(exp_str, "%Y-%m-%d").date()


def fetch_yfinance_chain(
    symbol: str = "QQQ",
    max_expiries: Optional[int] = 8,
    min_open_interest: float = 0.0,
) -> ChainSnapshot:
    """Fetch and normalise an options chain via yfinance.

    Parameters
    ----------
    symbol          : underlying ticker (default "QQQ").
    max_expiries    : cap on how many nearest expirations to pull (None = all).
                      8 comfortably covers the nearest weekly + this month's
                      monthly while keeping the request light.
    min_open_interest : drop strikes with OI at/below this (noise reduction).

    Requires network access to Yahoo Finance -- run this on a machine whose
    egress reaches ``*.finance.yahoo.com`` (a locked-down CI/agent sandbox may
    block it).
    """
    import yfinance as yf  # imported lazily so the engine/tests need no network

    ticker = yf.Ticker(symbol)

    spot = _latest_spot(ticker)
    asof = datetime.now(timezone.utc)

    expiries = list(ticker.options)
    if max_expiries is not None:
        expiries = expiries[:max_expiries]

    rows: List[OptionRow] = []
    for exp_str in expiries:
        exp = _parse_expiry(exp_str)
        chain = ticker.option_chain(exp_str)
        rows.extend(_rows_from_frame(chain.calls, "C", exp, min_open_interest))
        rows.extend(_rows_from_frame(chain.puts, "P", exp, min_open_interest))

    return ChainSnapshot(symbol=symbol, spot=float(spot), asof=asof, rows=rows)


def _latest_spot(ticker) -> float:
    """Most recent traded price for the underlying."""
    hist = ticker.history(period="1d")
    if len(hist):
        return float(hist["Close"].iloc[-1])
    # fall back to fast_info if history is empty (e.g. pre-market)
    return float(ticker.fast_info["last_price"])


def _rows_from_frame(frame, opt_type: str, exp: date, min_oi: float) -> List[OptionRow]:
    """Convert a yfinance calls/puts DataFrame into OptionRow objects."""
    out: List[OptionRow] = []
    for _, row in frame.iterrows():
        oi = row.get("openInterest")
        iv = row.get("impliedVolatility")
        strike = row.get("strike")
        if oi is None or strike is None:
            continue
        try:
            oi = float(oi)
            iv = float(iv) if iv is not None else 0.0
            strike = float(strike)
        except (TypeError, ValueError):
            continue
        if oi <= min_oi or iv <= 0:
            continue
        out.append(OptionRow(strike=strike, type=opt_type, open_interest=oi, iv=iv, expiry=exp))
    return out


def qqq_to_nq_factor(qqq_spot: float, nq_price: float) -> float:
    """Scale factor to map QQQ strikes onto the /NQ future.

    Pass the current /NQ price from your platform; the factor is simply
    ``nq_price / qqq_spot``.  (QQQ tracks NDX/~41, and /NQ tracks NDX, so this
    ratio lands QQQ-derived levels right on your NQ chart.)"""
    if qqq_spot <= 0:
        raise ValueError("qqq_spot must be positive")
    return nq_price / qqq_spot


def scale_factor(underlying_spot: float, future_price: float) -> float:
    """Generic strike->future scale = future_price / underlying_spot.

    Works whether the underlying is the index itself (NDX/SPX -> factor ~1) or an
    ETF proxy (QQQ -> ~41, SPY -> ~10)."""
    if underlying_spot <= 0:
        raise ValueError("underlying_spot must be positive")
    return future_price / underlying_spot


# Which options underlying(s) back each future, best first. The engine tries
# the index (where his levels actually come from) and falls back to the free,
# reliable ETF proxy if index options aren't available via yfinance.
FUTURE_MAP = {
    "NQ": {"future": "NQ=F", "name": "Nasdaq-100", "underlyings": ["^NDX", "QQQ"]},
    "ES": {"future": "ES=F", "name": "S&P 500", "underlyings": ["^SPX", "^GSPC", "SPY"]},
}


@dataclass
class FutureLevelsInput:
    """Everything needed to compute + scale levels for one future."""

    future: str            # "NQ" / "ES"
    future_price: float    # live front-month future price
    underlying: str        # options symbol actually used (e.g. "^NDX" or "QQQ")
    snapshot: ChainSnapshot
    factor: float          # underlying-strike -> future-price scale


def fetch_future_price(future_symbol: str) -> float:
    """Live front-month future price via yfinance (e.g. 'NQ=F', 'ES=F')."""
    import yfinance as yf

    t = yf.Ticker(future_symbol)
    hist = t.history(period="1d")
    if len(hist):
        return float(hist["Close"].iloc[-1])
    return float(t.fast_info["last_price"])


def fetch_chain_for_future(
    future: str,
    max_expiries: Optional[int] = 8,
    min_open_interest: float = 0.0,
    prefer_underlying: Optional[str] = None,
) -> FutureLevelsInput:
    """Fetch options + live future price for a future symbol ('NQ' or 'ES').

    Tries the index options first (what his HP/MHP actually derive from), then
    the ETF proxy.  Also grabs the live future price so levels scale onto the
    future automatically -- no manual price entry, so this can run unattended.
    """
    future = future.upper()
    if future not in FUTURE_MAP:
        raise ValueError(f"unknown future {future!r}; known: {list(FUTURE_MAP)}")
    cfg = FUTURE_MAP[future]

    candidates = [prefer_underlying] if prefer_underlying else list(cfg["underlyings"])
    snap = None
    used = None
    errors = []
    for u in candidates:
        try:
            s = fetch_yfinance_chain(u, max_expiries=max_expiries, min_open_interest=min_open_interest)
            if s.rows:
                snap, used = s, u
                break
            errors.append(f"{u}: no option rows")
        except Exception as exc:  # try next underlying
            errors.append(f"{u}: {exc}")
    if snap is None:
        raise RuntimeError(f"could not load options for {future} from {candidates}: " + "; ".join(errors))

    future_price = fetch_future_price(cfg["future"])
    factor = scale_factor(snap.spot, future_price)
    return FutureLevelsInput(
        future=future, future_price=future_price, underlying=used, snapshot=snap, factor=factor
    )
