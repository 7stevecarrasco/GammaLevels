# Reverse-engineering the published HP / MHP levels — findings

**Question:** do the Rocket Scooter "Dynamic HP" levels (WHP/HP teal, MHP orange)
reduce to a deterministic price formula (pivots, Fibonacci, a fixed ± band), or
are they genuinely options/gamma-derived?

**Method:** collected published (date, symbol, price, HP, MHP) from chart
screenshots and ran `reverse_engineer.py` — a battery of symmetry, half-width,
round-number, and cross-symbol tests. See `observations.csv`.

## Dataset (7 clean observations)

| Date | Sym | Price | HP | MHP | center | half-width | width % |
|---|---|---|---|---|---|---|---|
| 3/3/26 | NQ | 24684.75 | 24791.09 | 24686.60 | 24738.85 | 52.25 | 0.42% |
| 3/3/26 | ES | 6807.75 | 6841.48 | 6821.84 | 6831.66 | 9.82 | 0.29% |
| 3/4/26 | NQ | 25138.00 | 25103.72 | 25084.60 | 25094.16 | 9.56 | 0.08% |
| 3/4/26 | ES | 6879.00 | 6881.64 | 6821.67 | 6851.66 | 29.99 | 0.87% |
| 3/11/26 | NQ | 24945.50 | 25068.71 | 24966.25 | 25017.48 | 51.23 | 0.41% |
| 3/11/26 | ES | 6769.75 | 6789.08 | 6764.43 | 6776.76 | 12.32 | 0.36% |
| 7/5/26 | NQ | 29881.50 | 29973.39 | 29812.61 | 29893.00 | 80.39 | 0.54% |

## Verdict: NOT a price formula — the levels are options-gamma-derived

1. **Half-width is not stable.** 9.56 → 80.39 pts (CV 0.72); 0.08% → 0.87% of
   price (CV 0.53). A mechanical band would be roughly constant. It isn't.
2. **Not centered on price.** center − price ranged −43.84 → +71.98 (stdev 38).
3. **NQ and ES spacings are independent.** Same-day NQ/ES half-width ratio was
   5.32, 0.32, 4.16 — while the *center* ratio held ~3.62–3.69 (the index
   ratio). Independent spacing ⇒ each market's own options book sets its band,
   which no shared formula can produce.
4. **Non-round decimals** (.09/.60/.72/.71/.25/.39/.61) ⇒ a computed/interpolated
   value, not a raw strike or clean formula.
5. The 7/5 "round center" (29893.00) was a **coincidence** — no other day
   centers on a round number.

This is consistent with the course PDF (`EventHorizon`, "Dynamic HP Stats"),
whose author *collects* the levels from Discord rather than computing them, and
with the streamer's own words ("maximum gamma exposure for dealer-hedged
options").

## Most likely underlying

- **NQ levels ← NDX options** (NDX ≈ NQ price).
- **ES levels ← SPX options** (SPX ≈ ES price; the deepest options in the world).
- **HP/WHP** = gamma level from the **nearest weekly** expiry;
  **MHP** = gamma level from the **monthly (3rd-Friday)** expiry.
- The precise definition (peak-gamma strike vs gamma-weighted centroid vs
  zero-gamma flip) is what we'd fit once we have the raw chains.

## What it would take to reproduce his exact numbers

Screenshots alone can't — we need the **historical options chain** (open
interest + implied vol by strike) for **NDX and SPX**, for the nearest weekly
and the monthly expiry, snapshotted at ~6pm ET on each date. Candidate sources:
Theta Data, ORATS, or CBOE DataShop (all paid; free feeds don't carry historical
per-strike OI).

Then: for each date, compute the weekly and monthly gamma profiles and check
which level definition reproduces the published HP/MHP to within a point. Once
one definition fits across many days, the black box is solved.

## What we CAN do for free right now

- Compute *today's* gamma levels from free QQQ options (the engine already does
  this) and confirm they land in the same neighborhood and behave the same way
  (magnet / support) per the stats study.
- Backtest the behavioral edge from the course PDF (P(touch), P(close-above))
  against our own levels.
