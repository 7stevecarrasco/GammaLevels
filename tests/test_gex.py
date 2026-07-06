"""Synthetic-data verification of the gamma-exposure math (no network needed).

Run with:  python -m pytest tests/  -q     (or)     python tests/test_gex.py
"""

from __future__ import annotations

import math
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gammalevels.blackscholes import gamma
from gammalevels.gex import OptionRow, compute_profile
from gammalevels.levels import (
    compute_hedge_levels,
    is_monthly_expiry,
    pick_monthly_expiry,
    pick_weekly_expiry,
    third_friday,
)


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_gamma_peaks_at_the_money():
    """Gamma should be largest for the at-the-money strike."""
    spot, t, iv = 100.0, 30 / 365, 0.20
    g_atm = gamma(spot, 100, t, iv)
    g_otm = gamma(spot, 115, t, iv)
    g_itm = gamma(spot, 85, t, iv)
    assert g_atm > g_otm and g_atm > g_itm, "ATM gamma must dominate"
    print(f"  ATM gamma {g_atm:.5f} > OTM {g_otm:.5f}, ITM {g_itm:.5f}  OK")


def test_gamma_zero_when_expired():
    assert gamma(100, 100, 0, 0.2) == 0.0
    assert gamma(100, 100, 0.1, 0) == 0.0
    print("  degenerate inputs -> gamma 0  OK")


def _synthetic_chain(exp: date):
    """A chain with a big call-OI wall above spot and a big put-OI wall below."""
    rows = []
    # ATM-ish cluster
    for k in range(90, 111, 5):
        rows.append(OptionRow(k, "C", open_interest=500, iv=0.20, expiry=exp))
        rows.append(OptionRow(k, "P", open_interest=500, iv=0.20, expiry=exp))
    # dominant call wall at 110, dominant put wall at 90
    rows.append(OptionRow(110, "C", open_interest=20000, iv=0.20, expiry=exp))
    rows.append(OptionRow(90, "P", open_interest=20000, iv=0.20, expiry=exp))
    return rows


def test_profile_walls_and_peak():
    exp = date(2026, 8, 21)  # a 3rd Friday
    asof = datetime(2026, 7, 6, 12, 0, 0)
    rows = _synthetic_chain(exp)
    prof = compute_profile(rows, spot=100.0, asof=asof)

    assert prof.call_wall == 110.0, f"call wall {prof.call_wall}"
    assert prof.put_wall == 90.0, f"put wall {prof.put_wall}"
    # peak absolute gamma sits at one of the loaded walls
    assert prof.peak_gamma_strike in (90.0, 110.0), prof.peak_gamma_strike
    # centroid is pulled between the two big walls, near spot
    assert 95.0 < prof.gamma_centroid < 105.0, prof.gamma_centroid
    print(
        f"  call_wall={prof.call_wall} put_wall={prof.put_wall} "
        f"peak={prof.peak_gamma_strike} centroid={prof.gamma_centroid:.2f}  OK"
    )


def test_zero_gamma_between_walls():
    """With a call wall above and put wall below, net gamma flips sign between
    them, so the flip point should land near the middle."""
    exp = date(2026, 8, 21)
    asof = datetime(2026, 7, 6, 12, 0, 0)
    rows = _synthetic_chain(exp)
    prof = compute_profile(rows, spot=100.0, asof=asof)
    assert prof.zero_gamma is not None, "expected a flip point"
    assert 90.0 < prof.zero_gamma < 110.0, prof.zero_gamma
    print(f"  zero_gamma flip = {prof.zero_gamma:.2f}  OK")


def test_dealer_sign_convention():
    """Above the put wall / below the call wall net gamma should be positive
    (dealers long calls dominate); a pure short-put book is negative gamma."""
    exp = date(2026, 8, 21)
    asof = datetime(2026, 7, 6, 12, 0, 0)
    puts_only = [OptionRow(100, "P", 1000, 0.2, exp)]
    prof = compute_profile(puts_only, spot=100.0, asof=asof)
    assert prof.net_gex_at_spot < 0, "short puts => negative dealer gamma"
    calls_only = [OptionRow(100, "C", 1000, 0.2, exp)]
    prof2 = compute_profile(calls_only, spot=100.0, asof=asof)
    assert prof2.net_gex_at_spot > 0, "long calls => positive dealer gamma"
    print("  sign convention: calls(+) puts(-)  OK")


def test_expiry_classification():
    assert third_friday(2026, 8) == date(2026, 8, 21)
    assert is_monthly_expiry(date(2026, 8, 21))
    assert not is_monthly_expiry(date(2026, 8, 14))
    print("  third_friday / monthly classification  OK")


def test_weekly_vs_monthly_bucketing():
    """HP must come from the nearest weekly, MHP from the 3rd-Friday monthly."""
    asof = datetime(2026, 7, 6, 12, 0, 0)  # a Monday
    weekly_exp = date(2026, 7, 10)          # nearest Friday weekly
    monthly_exp = date(2026, 7, 17)         # 3rd Friday monthly
    assert is_monthly_expiry(monthly_exp)

    rows = []
    # weekly: put-heavy -> peak gamma near 95
    for k in (95, 100, 105):
        rows.append(OptionRow(k, "C", 100, 0.2, weekly_exp))
        rows.append(OptionRow(k, "P", 100, 0.2, weekly_exp))
    rows.append(OptionRow(95, "P", 50000, 0.2, weekly_exp))
    # monthly: call-heavy -> peak gamma near 105
    for k in (95, 100, 105):
        rows.append(OptionRow(k, "C", 100, 0.2, monthly_exp))
        rows.append(OptionRow(k, "P", 100, 0.2, monthly_exp))
    rows.append(OptionRow(105, "C", 50000, 0.2, monthly_exp))

    levels = compute_hedge_levels(rows, spot=100.0, asof=asof, method="peak")
    assert levels.weekly_expiry == weekly_exp, levels.weekly_expiry
    assert levels.monthly_expiry == monthly_exp, levels.monthly_expiry
    assert levels.hp == 95.0, f"HP {levels.hp}"
    assert levels.mhp == 105.0, f"MHP {levels.mhp}"
    print(f"  HP(weekly)={levels.hp}  MHP(monthly)={levels.mhp}  OK")


def test_scaling_to_nq():
    asof = datetime(2026, 7, 6, 12, 0, 0)
    exp = date(2026, 7, 17)
    rows = [OptionRow(600, "C", 1000, 0.2, exp), OptionRow(600, "P", 1000, 0.2, exp)]
    levels = compute_hedge_levels(rows, spot=600.0, asof=asof, method="peak")
    scaled = levels.scaled(factor=50.0)  # pretend NQ/QQQ ~ 50
    assert approx(scaled["mhp"], 30000.0), scaled
    print(f"  scaled MHP 600 -> {scaled['mhp']} (x50)  OK")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"Running {len(tests)} checks...\n")
    for fn in tests:
        print(f"- {fn.__name__}")
        fn()
    print("\nAll checks passed.")
