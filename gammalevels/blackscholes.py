"""Black-Scholes greeks used for gamma-exposure calculations.

Only the pieces we actually need for dealer gamma levels live here: the
standard-normal pdf, ``d1``, and option ``gamma``.  Gamma is identical for a
call and a put at the same strike/expiry, which is why it is the single most
robust input for hedging-pressure levels -- it does not depend on the
long/short assumption we have to make about *delta*.
"""

from __future__ import annotations

import math

SQRT_2PI = math.sqrt(2.0 * math.pi)


def norm_pdf(x: float) -> float:
    """Standard-normal probability density function, N'(x)."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def d1(spot: float, strike: float, t: float, iv: float, r: float = 0.0, q: float = 0.0) -> float:
    """Black-Scholes ``d1`` term.

    Parameters
    ----------
    spot   : underlying price
    strike : option strike
    t      : time to expiry in years
    iv     : implied volatility (annualised, e.g. 0.18 for 18%)
    r      : risk-free rate (annualised)
    q      : dividend / carry yield (annualised)
    """
    if t <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return float("nan")
    return (math.log(spot / strike) + (r - q + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))


def gamma(spot: float, strike: float, t: float, iv: float, r: float = 0.0, q: float = 0.0) -> float:
    """Black-Scholes gamma (same for calls and puts).

    Gamma = N'(d1) / (S * sigma * sqrt(T)).  Returns 0.0 for degenerate inputs
    (expired options, missing IV) so it is safe to sum over a whole chain.
    """
    if t <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    _d1 = d1(spot, strike, t, iv, r, q)
    return math.exp(-q * t) * norm_pdf(_d1) / (spot * iv * math.sqrt(t))
