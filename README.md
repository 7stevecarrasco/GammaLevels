# GammaLevels

Build your own **dealer gamma-hedging levels** — the same thing paid Discord
services sell as **HP** (weekly hedge pressure) and **MHP** (monthly hedge
pressure) — from **free** options data.

No subscription, no black box. You feed in an options chain, it computes where
dealers have to hedge hardest, and those strikes become your levels.

---

## What HP and MHP actually are

Options **dealers delta-hedge** the contracts they're short, and their hedging
intensity at any price is proportional to **gamma × open interest**. The strike
where that product is greatest is the biggest **hedging magnet** — price tends
to pin to it or pivot there on heavy volume.

That single calculation, applied to two different expirations, is the whole
trick:

| Line | What it is | How it's computed |
|------|-----------|-------------------|
| **HP**  | Weekly hedge pressure  | Peak dealer gamma on the **nearest weekly expiry** |
| **MHP** | Monthly hedge pressure | Peak dealer gamma on the **3rd-Friday monthly expiry** |

The engine also gives you the rest of the standard gamma map:

- **Call wall** — largest positive-gamma strike (acts as resistance)
- **Put wall** — largest negative-gamma strike (acts as support)
- **Zero-gamma flip** — the price where net dealer gamma crosses zero. Above it
  dealers *dampen* volatility (mean-reversion); below it they *chase* price
  (trend / vol expansion).

This is the publicly documented **Gamma Exposure (GEX)** framework
(SqueezeMetrics / SpotGamma / MenthorQ). "HP / MHP / margin buffer limit line"
is branding on top of it.

## The math (no magic)

Black-Scholes gamma per option (identical for calls and puts):

```
gamma = N'(d1) / (S · σ · √T)
```

Dollar gamma exposure per strike, with the standard dealer sign assumption
(dealers **long call gamma**, **short put gamma**):

```
GEX(strike) = Σ_calls gamma·OI·100·S²·0.01  −  Σ_puts gamma·OI·100·S²·0.01
```

Find the peak / walls / zero-crossing of that profile → your levels. See
`gammalevels/gex.py`.

## Data

Uses **QQQ** options (the liquid Nasdaq-100 proxy) pulled free via `yfinance`.
Because `/NQ ≈ NDX` and `QQQ ≈ NDX / ~41`, QQQ-derived strikes scale straight
onto your NQ chart:

```
NQ_level = QQQ_level × (NQ_price / QQQ_price)
```

Enter your live `/NQ` price in the dashboard (or `--nq` on the CLI) and the
levels are projected onto NQ automatically.

> **Upgrading data later:** the engine only needs a list of `OptionRow`s, so
> swapping yfinance for a paid NDX feed (Polygon, Theta Data, tastytrade, IBKR)
> is one new function in `gammalevels/data.py` — nothing downstream changes.

## Quick start

```bash
pip install -r requirements.txt

# Dashboard (needs internet access to Yahoo Finance)
streamlit run app.py

# Or one-shot from the terminal, scaled onto NQ:
python scripts/print_levels.py --nq 29881.5
python scripts/print_levels.py --method centroid --json levels.json
```

`--method` picks how HP/MHP is defined: `peak` (default, biggest magnet),
`centroid` (gamma-weighted mean — gives smooth, non-round numbers like the
services post), `flip`, `callwall`, `putwall`.

## Verify the math

The gamma/GEX math is covered by synthetic-data tests that need **no network**:

```bash
python tests/test_gex.py       # or: python -m pytest tests/ -q
```

## Project layout

```
gammalevels/
  blackscholes.py   # gamma / d1 / normal pdf
  gex.py            # GEX-by-strike, walls, zero-gamma flip, centroid
  levels.py         # weekly/monthly bucketing -> HP / MHP
  data.py           # yfinance QQQ adapter + QQQ->NQ scaling
app.py              # Streamlit dashboard
scripts/print_levels.py   # CLI
tests/test_gex.py         # offline verification of the math
```

## A note on reliability

Free yfinance open interest is **end-of-day** and occasionally patchy — great
for learning and for levels that don't need tick precision, but for
production-grade intraday HP/MHP (matching a service that recomputes at the NY
open) you'll want a real-time NDX options feed. The framework is built to make
that swap trivial.

---

*Educational tool for understanding options market structure. Not financial
advice.*
