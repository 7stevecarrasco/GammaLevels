#!/usr/bin/env python3
"""Compute the day's HP / MHP for NQ and ES automatically -- no manual input.

This is the "don't wait for his Discord post" script.  Run it before the 6pm ET
Globex open (and again after the 9:30am NY open if you want the RTH refresh) and
it will, for each future:

  * fetch the options chain (NDX for NQ / SPX for ES, ETF proxy as fallback),
  * fetch the live front-month future price,
  * compute HP (weekly gamma level) and MHP (monthly gamma level) + walls/flip,
  * scale everything onto the future price,

then write JSON and a ready-to-paste TradingView Pine script per future.

Schedule it (cron / Task Scheduler) -- see the README "Automating it" section.

Examples
--------
    python scripts/daily_levels.py
    python scripts/daily_levels.py --futures NQ ES --method centroid --outdir out
    python scripts/daily_levels.py --future NQ --proxy      # force free QQQ/SPY

Runs where Yahoo Finance is reachable (your own machine, not a locked sandbox).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gammalevels import FUTURE_MAP, compute_hedge_levels, fetch_chain_for_future
from gammalevels.pinegen import to_pine

TV_CHART = {"NQ": "CME_MINI:NQ1!", "ES": "CME_MINI:ES1!"}
PROXY = {"NQ": "QQQ", "ES": "SPY"}


def run_one(future: str, method: str, max_expiries: int, min_oi: float, force_proxy: bool,
            demo: bool = False):
    if demo:
        from gammalevels.demo import demo_input
        inp = demo_input(future)
    else:
        prefer = PROXY[future] if force_proxy else None
        inp = fetch_chain_for_future(
            future, max_expiries=max_expiries, min_open_interest=min_oi, prefer_underlying=prefer
        )
    levels = compute_hedge_levels(
        inp.snapshot.rows, inp.snapshot.spot, inp.snapshot.asof, method=method
    )
    scaled = levels.scaled(inp.factor)
    scaled.update({
        "future": future,
        "future_price": round(inp.future_price, 2),
        "options_underlying": inp.underlying,
        "scale_factor": round(inp.factor, 5),
        "method": method,
        "weekly_expiry": str(levels.weekly_expiry),
        "monthly_expiry": str(levels.monthly_expiry),
        "asof": inp.snapshot.asof.isoformat(),
        "is_proxy": inp.underlying in PROXY.values(),
    })
    pine = to_pine(levels, inp.factor, inp.snapshot.asof, symbol_note=TV_CHART.get(future, ""))
    return inp, levels, scaled, pine


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-compute HP/MHP for NQ and ES.")
    ap.add_argument("--futures", nargs="+", default=["NQ", "ES"], choices=list(FUTURE_MAP),
                    help="which futures to compute (default: NQ ES)")
    ap.add_argument("--future", dest="single", choices=list(FUTURE_MAP),
                    help="shortcut for a single future")
    ap.add_argument("--method", default="peak",
                    choices=["peak", "centroid", "flip", "callwall", "putwall"])
    ap.add_argument("--max-expiries", type=int, default=8)
    ap.add_argument("--min-oi", type=float, default=0.0)
    ap.add_argument("--proxy", action="store_true", help="force free ETF proxy (QQQ/SPY)")
    ap.add_argument("--demo", action="store_true",
                    help="run offline on synthetic data (no network; for previews/self-test)")
    ap.add_argument("--outdir", default=".", help="where to write JSON + .pine (default: cwd)")
    args = ap.parse_args()

    futures = [args.single] if args.single else args.futures
    os.makedirs(args.outdir, exist_ok=True)
    if args.demo:
        print("** DEMO MODE ** offline synthetic data — not real levels.\n")

    all_out = {}
    for fut in futures:
        print(f"\n=== {fut} ({FUTURE_MAP[fut]['name']}) ===")
        try:
            inp, levels, scaled, pine = run_one(
                fut, args.method, args.max_expiries, args.min_oi, args.proxy, demo=args.demo
            )
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        tag = "proxy" if scaled["is_proxy"] else "index"
        print(f"  options: {inp.underlying} ({tag}, spot {inp.snapshot.spot:.2f})  "
              f"future {inp.future_price:.2f}  x{inp.factor:.4f}")
        print(f"  weekly {levels.weekly_expiry} / monthly {levels.monthly_expiry}  method={args.method}")
        print(f"  HP  (weekly ) : {scaled['hp']}")
        print(f"  MHP (monthly) : {scaled['mhp']}")
        print(f"  weekly  call/put wall : {scaled['weekly_call_wall']} / {scaled['weekly_put_wall']}")
        print(f"  monthly call/put wall : {scaled['monthly_call_wall']} / {scaled['monthly_put_wall']}")
        if scaled["is_proxy"]:
            print("  NOTE: using ETF proxy -- levels are directionally right but won't")
            print("        exactly match his index-derived numbers.")

        json_path = os.path.join(args.outdir, f"levels_{fut}.json")
        pine_path = os.path.join(args.outdir, f"levels_{fut}.pine")
        with open(json_path, "w") as fh:
            json.dump(scaled, fh, indent=2)
        with open(pine_path, "w") as fh:
            fh.write(pine)
        print(f"  wrote {json_path} and {pine_path}")
        all_out[fut] = scaled

    combined = os.path.join(args.outdir, "levels_all.json")
    with open(combined, "w") as fh:
        json.dump(all_out, fh, indent=2)
    print(f"\nWrote combined {combined}")
    return 0 if all_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
