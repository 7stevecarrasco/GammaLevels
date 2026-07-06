# TradingView indicators

## session_gap_maker.pine — Session / overnight gap marker

Shades the gap between one session's **close** and the next session's **open**,
and flags it when price trades back through (fills) it.

- **Green box** = gap up · **Red box** = gap down · **gray** = filled
- **Dashed yellow line = the 50% midpoint** of the gap, with its price labeled
  (the "half-gap" level price tends to magnet toward).
- Default session **0930–1600 New York** = the US cash / **Regular Trading
  Hours** session, so the gap is **yesterday's 4pm close → today's 9:30 open** —
  the RTH overnight gap for NQ/ES. Change the **Session** input for a different
  window (e.g. Globex).

### Install
1. TradingView → open a chart (use an **intraday** timeframe, e.g. 5m/15m/1h).
2. Bottom panel → **Pine Editor** → paste the contents of
   `session_gap_maker.pine` → **Save** → **Add to chart**.

### Inputs
- **Session** — the window whose close→open defines the gap (default = RTH).
- **Min gap size (points)** — ignore gaps smaller than this (noise filter).
- **Show 50% midpoint line** — draw the dashed half-gap level + its price.
- **Count gap 'filled' at 50%** — gray the gap when price reaches the midpoint
  instead of the full prior close (some traders call 50% a fill).
- **Extend gap until filled** — keep drawing the zone right until price fills it.
- **Remove gap once filled** — delete the box on fill instead of graying it.
- **Show gap size label** — label each gap with its point size.
- **Max active (unfilled) gaps** — cap how many open gaps stay on the chart.
