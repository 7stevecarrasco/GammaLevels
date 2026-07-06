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

Pulled free via `yfinance`. For each future it uses the **index options his
levels actually come from**, falling back to a liquid ETF proxy if the index
chain isn't available:

| Future | Index options (preferred) | Free proxy (fallback) |
|--------|---------------------------|-----------------------|
| **NQ** | `^NDX` (Nasdaq-100)       | `QQQ` (≈ NDX / 41)    |
| **ES** | `^SPX` (S&P 500)         | `SPY` (≈ SPX / 10)    |

The live front-month future price (`NQ=F` / `ES=F`) is fetched automatically, so
strikes scale onto the future with no manual input:

```
future_level = option_level × (future_price / underlying_spot)
```

With the index (NDX/SPX) the factor is ≈ 1; with an ETF proxy it's ≈ 41 (NQ) or
≈ 10 (ES). Either way the levels land on your NQ/ES chart.

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

# Generate a TradingView Pine script with the levels drawn on it:
python scripts/print_levels.py --nq 29881.5 --pine gammalevels.pine
```

`--method` picks how HP/MHP is defined: `peak` (default, biggest magnet),
`centroid` (gamma-weighted mean — gives smooth, non-round numbers like the
services post), `flip`, `callwall`, `putwall`.

## Automating it — compute tomorrow's levels yourself

The whole point: **don't wait for anyone's Discord post.** `daily_levels.py`
computes HP/MHP for NQ and ES with zero manual input — it fetches the index
options (NDX for NQ, SPX for ES; free QQQ/SPY proxy as fallback) *and* the live
front-month future price, then writes JSON + a TradingView Pine script per
future:

```bash
python scripts/daily_levels.py                 # NQ + ES, writes levels_*.json / .pine
python scripts/daily_levels.py --method centroid --outdir ~/gammalevels_out
python scripts/daily_levels.py --future NQ --proxy   # force free QQQ
python scripts/daily_levels.py --demo               # offline self-test, no network
```

`--demo` runs the whole pipeline on synthetic data (no Yahoo needed) so you can
see the output shape and test scheduling before trusting live numbers.

**Schedule it** so the levels are ready before the 6pm ET Globex open, and
again after the 9:30am ET NY open (when he says the platform recalculates on
fresh options data):

*macOS / Linux (`crontab -e`) — times are your local clock:*
```cron
# 5:45pm and 9:35am ET (adjust to your timezone)
45 17 * * 1-5  cd /path/to/GammaLevels && /usr/bin/python3 scripts/daily_levels.py --outdir out >> out/cron.log 2>&1
35  9 * * 1-5  cd /path/to/GammaLevels && /usr/bin/python3 scripts/daily_levels.py --outdir out >> out/cron.log 2>&1
```

*Windows (Task Scheduler):* create a Basic Task → Daily → trigger 5:45 PM →
action "Start a program" → `python` with arguments
`scripts\daily_levels.py --outdir out` and "Start in" set to the repo folder.

Each run drops `levels_NQ.pine` / `levels_ES.pine` — paste into TradingView once
and every rerun refreshes the same file, so you just reload the script.

> **Honest limit on free data:** yfinance open interest is **end-of-day**, so the
> pre-open run uses the most recent OI snapshot (same lag his overnight levels
> face). The 9:30am rerun won't have *live* intraday OI on the free feed — for
> that you'd need a paid real-time options feed (the data layer is built to swap
> one in). Free levels are directionally right and update daily.

## Drawing the levels on TradingView

Pine Script **can't fetch external data** (no HTTP requests), so it can't pull
gamma levels live. Instead this tool *generates* a Pine v5 indicator with the
current levels baked in:

1. In the dashboard, open **📤 Send to TradingView** and copy / download the
   script (or run `--pine gammalevels.pine` on the CLI).
2. In TradingView open **Pine Editor** → paste → **Add to chart**.
3. Use the `CME_MINI:NQ1!` chart (levels are absolute prices, so any NQ chart
   works).

It draws HP + weekly walls in **teal**, MHP + monthly walls in **orange**, with
right-edge price labels — and each level is an `input.price` you can drag to
nudge. Because open interest is end-of-day, regenerate the script once or twice
a day (e.g. at the NY open) to refresh.

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
  data.py           # yfinance adapters: NDX/SPX (+QQQ/SPY fallback), future price
  pinegen.py        # TradingView Pine v5 script generator
app.py              # Streamlit dashboard (pick NQ/ES, auto-scaled)
scripts/daily_levels.py   # automated: tomorrow's HP/MHP for NQ+ES, schedulable
scripts/print_levels.py   # single-underlying CLI
research/                 # reverse-engineering study of his published levels
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
