# How the HP / MHP levels are actually calculated

Source: the creator's own "Dynamic Overnight Hedge Pressure" class transcript.
This is the authoritative decode of where the levels come from — and, honestly,
which parts you can reproduce and which you can't.

## There are two different hedge pressures

### 1. The 9:30 AM "morning" hedge pressure — REPRODUCIBLE
Standard **dealer gamma exposure** (a "liquidity map"):
- Inputs: full **open interest**, each option's **price** and **Greeks** (delta,
  gamma, …), and the market-maker share of OI.
- OI is published by **OPRA** (Options Price Reporting Authority) once, in the
  middle of the night — that's when 100% of open interest is known.
- At the 9:30 open you have OI **and** live prices/Greeks together, so the calc
  runs **once** and the levels stay static all day (they rarely move > ~1 strike
  because intraday OI change is small).
- **This is exactly what `gammalevels` computes.** Anyone with OI + Greeks can
  reproduce it.

### 2. The overnight "dynamic" HP / MHP — his 5:30 PM posts / the screenshots — NOT exactly reproducible
- Posted ~**5:30 PM**, 30 min before the 6 PM Globex open.
- It is an **estimate of where the 9:30 gamma level will land**, computed at
  5:30 PM **assuming the underlying price doesn't move overnight**.
- After the 4:15 PM options close there is no fresh price/Greek data, and the OI
  from last night's OPRA publish is already stale — so he can't just run the
  normal calc.

## The secret sauce: a real-time open-interest *estimation* model

True OI is known only once per day (OPRA, overnight). Intraday and into the
evening, **nobody knows real-time OI** — it isn't published. So he estimates it:

- Watch the **options tape** and classify each trade as:
  - **Created** (OI ↑) — e.g. order prints and the bid/ask doesn't move ⇒ new
    contracts sold to a dealer.
  - **Destroyed** (OI ↓) — exercised; cross-checked against matching share trades.
  - **Changed hands** (OI flat) — e.g. order hits the bid and the bid drops.
- The exact classification rules are **explicitly proprietary** ("I don't tell
  how I do it").
- Early model output a **range**: `OI_max = OI + volume`, `OI_min = OI - volume`,
  compute HP at both, true level ~ in the middle. Later refined to a single
  number (one WHP + one MHP overnight).
- Then: estimated real-time OI + end-of-day option parameters, projected to 9:30
  assuming flat price ⇒ the dynamic level.
- Run on **his own local machine** at 5:30 PM, posted manually to Discord
  (channel `futures-hp-dyn`); intended to be automated in-platform later.

## Why you can't match his 5:30 PM number exactly

1. **Proprietary trade-classification heuristics** — deliberately not disclosed.
2. **Requires a real-time options order-flow feed** (every OPRA trade + quote) to
   run the OI estimate. That's paid, institutional data — yfinance has only
   end-of-day OI. No free tool can reproduce the estimate.

## Why the gap is small (his own words)

- The dynamic level just predicts the 9:30 gamma level (flat-price assumption).
- Intraday, hedge pressure and walls move **≤ ~1 strike** — that variance IS his
  stop loss: **~10 points on ES, ~40 points on NASDAQ (NQ)**.
- So the standard gamma level computed on the latest OI lands **within one
  strike** of his dynamic post — his own margin of error.

## Reproduction tiers

| Tier | Accuracy vs his post | Data needed | Status |
|------|----------------------|-------------|--------|
| **A — gamma level on EOD OPRA OI**, projected flat | within ~1 strike | free EOD OI (yfinance QQQ/SPY) or cheap EOD OPRA | **built** (`daily_levels.py`) |
| **B — replicate the estimate model** | ~exact | real-time OPRA trades+quotes (Databento / Polygon / dxFeed) + a create/destroy/transfer classifier | design only |

Tier B is the real replica of Matt's model: maintain a running per-contract OI
estimate by classifying each trade from bid/ask context (+ share cross-check),
then at 5:30 PM run the gamma calc on estimated OI and project to 9:30. The
classification rules he keeps secret would be re-derived (he argues everyone
converges on the same logic anyway — "convergent evolution").
