# TradingView indicators

## session_gap_maker.pine — Session / overnight gap marker

Shades the gap between one session's **close** and the next session's **open**,
and flags it when price trades back through (fills) it.

- **Green box** = gap up · **Red box** = gap down · **gray** = filled
- Default session **0930–1600 New York** = the US cash session, so the gap is
  **yesterday's 4pm close → today's 9:30 open** — the classic overnight gap for
  NQ/ES. Change the **Session** input for a different window (e.g. Globex).

### Install
1. TradingView → open a chart (use an **intraday** timeframe, e.g. 5m/15m/1h).
2. Bottom panel → **Pine Editor** → paste the contents of
   `session_gap_maker.pine` → **Save** → **Add to chart**.

### Inputs
- **Session** — the window whose close→open defines the gap.
- **Min gap size (points)** — ignore gaps smaller than this (noise filter).
- **Extend gap until filled** — keep drawing the zone to the right until price fills it.
- **Remove gap once filled** — delete the box on fill instead of graying it.
- **Show gap size label** — label each gap with its point size.
- **Max active (unfilled) gaps** — cap how many open gaps stay on the chart.
