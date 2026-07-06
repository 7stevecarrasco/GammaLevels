#!/usr/bin/env python3
"""CLI: fetch QQQ options, compute HP / MHP, print (and optionally export).

Examples
--------
    python scripts/print_levels.py
    python scripts/print_levels.py --nq 29881.5 --method centroid
    python scripts/print_levels.py --json levels.json

Run this on a machine with network access to Yahoo Finance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gammalevels import compute_hedge_levels, fetch_yfinance_chain, qqq_to_nq_factor
from gammalevels.pinegen import to_pine


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute HP/MHP gamma-hedge levels.")
    ap.add_argument("--symbol", default="QQQ", help="options underlying (default QQQ)")
    ap.add_argument("--nq", type=float, default=None,
                    help="current /NQ price; if given, levels are scaled onto NQ")
    ap.add_argument("--method", default="peak",
                    choices=["peak", "centroid", "flip", "callwall", "putwall"],
                    help="how HP/MHP is defined (default peak gamma strike)")
    ap.add_argument("--max-expiries", type=int, default=8)
    ap.add_argument("--min-oi", type=float, default=0.0, help="drop strikes at/below this OI")
    ap.add_argument("--json", metavar="PATH", default=None, help="also write result as JSON")
    ap.add_argument("--pine", metavar="PATH", default=None,
                    help="also write a TradingView Pine v5 script drawing the levels")
    args = ap.parse_args()

    print(f"Fetching {args.symbol} options chain...")
    snap = fetch_yfinance_chain(args.symbol, max_expiries=args.max_expiries, min_open_interest=args.min_oi)
    print(f"  spot={snap.spot:.2f}  expiries={snap.num_expiries}  contracts={len(snap.rows)}\n")

    levels = compute_hedge_levels(snap.rows, snap.spot, snap.asof, method=args.method)

    factor = 1.0
    unit = args.symbol
    if args.nq is not None:
        factor = qqq_to_nq_factor(snap.spot, args.nq)
        unit = f"NQ (x{factor:.3f})"

    out = levels.scaled(factor)
    out["symbol"] = args.symbol
    out["method"] = args.method
    out["asof"] = snap.asof.isoformat()

    print(f"=== Gamma hedge levels [{unit}] ===")
    print(f"  Weekly expiry : {levels.weekly_expiry}")
    print(f"  Monthly expiry: {levels.monthly_expiry}")
    print(f"  HP  (weekly ) : {out['hp']}")
    print(f"  MHP (monthly) : {out['mhp']}")
    print(f"  spot          : {out['spot']}")
    print(f"  weekly  call/put wall : {out['weekly_call_wall']} / {out['weekly_put_wall']}")
    print(f"  weekly  zero-gamma    : {out['weekly_zero_gamma']}")
    print(f"  monthly call/put wall : {out['monthly_call_wall']} / {out['monthly_put_wall']}")
    print(f"  monthly zero-gamma    : {out['monthly_zero_gamma']}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"\nWrote {args.json}")

    if args.pine:
        pine = to_pine(levels, factor, snap.asof)
        with open(args.pine, "w") as fh:
            fh.write(pine)
        print(f"Wrote {args.pine}  — paste it into TradingView's Pine editor on CME_MINI:NQ1!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
