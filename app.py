"""GammaLevels dashboard -- a live HP / MHP gamma-hedging indicator.

Run locally (needs network access to Yahoo Finance):

    pip install -r requirements.txt
    streamlit run app.py

Then open the URL Streamlit prints.  Enter your current /NQ price to have the
QQQ-derived levels scaled straight onto the NQ chart.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from gammalevels import compute_hedge_levels, qqq_to_nq_factor
from gammalevels.data import fetch_yfinance_chain

st.set_page_config(page_title="GammaLevels — HP / MHP", page_icon="📈", layout="wide")

METHOD_HELP = {
    "peak": "Strike with the greatest absolute dealer gamma (the biggest hedging magnet).",
    "centroid": "Gamma-weighted mean strike — a smooth, non-round 'pressure' level.",
    "flip": "Zero-gamma flip: where net dealer gamma crosses zero.",
    "callwall": "Largest positive-gamma strike (tends to act as resistance).",
    "putwall": "Largest negative-gamma strike (tends to act as support).",
}


@st.cache_data(ttl=120, show_spinner=False)
def load_chain(symbol: str, max_expiries: int, min_oi: float):
    """Fetch + cache the chain for a couple of minutes so slider tweaks are snappy."""
    snap = fetch_yfinance_chain(symbol, max_expiries=max_expiries, min_open_interest=min_oi)
    return snap


# ---------------------------------------------------------------- sidebar
st.sidebar.title("GammaLevels")
st.sidebar.caption("Dealer gamma-hedging levels, built from free options data.")

symbol = st.sidebar.text_input("Options underlying", value="QQQ").upper().strip()
method = st.sidebar.selectbox(
    "HP / MHP definition", list(METHOD_HELP), index=0,
    format_func=lambda m: m.capitalize(),
)
st.sidebar.caption(METHOD_HELP[method])

nq_price = st.sidebar.number_input(
    "Current /NQ price (for scaling)", min_value=0.0, value=0.0, step=0.25,
    help="Enter your live /NQ price to project QQQ levels onto the NQ chart. "
         "Leave 0 to show levels in the underlying's own price.",
)
max_expiries = st.sidebar.slider("Expirations to load", 2, 16, 8)
min_oi = st.sidebar.number_input("Min open interest per strike", min_value=0.0, value=0.0, step=50.0)

if st.sidebar.button("↻ Refresh data", use_container_width=True):
    load_chain.clear()

# ---------------------------------------------------------------- main
st.title("📈 Gamma Hedge Levels — HP / MHP")

try:
    snap = load_chain(symbol, max_expiries, min_oi)
except Exception as exc:  # network / symbol errors surface here
    st.error(
        f"Couldn't load options for **{symbol}**: {exc}\n\n"
        "This dashboard needs outbound access to Yahoo Finance. If you're on a "
        "restricted network (or a sandbox), run it on your own machine."
    )
    st.stop()

levels = compute_hedge_levels(snap.rows, snap.spot, snap.asof, method=method)

factor = 1.0
unit = symbol
if nq_price and nq_price > 0:
    factor = qqq_to_nq_factor(snap.spot, nq_price)
    unit = "/NQ"

scaled = levels.scaled(factor)

# headline metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"HP · Weekly ({unit})", scaled["hp"], help=f"Weekly expiry {levels.weekly_expiry}")
c2.metric(f"MHP · Monthly ({unit})", scaled["mhp"], help=f"Monthly expiry {levels.monthly_expiry}")
c3.metric(f"Spot ({unit})", scaled["spot"])
regime = "🟢 long-gamma (mean-revert)" if (levels.monthly and levels.monthly.net_gex_at_spot > 0) else "🔴 short-gamma (trend)"
c4.metric("Dealer regime (monthly)", regime)

st.caption(
    f"Underlying **{symbol}** spot {snap.spot:.2f} · {snap.num_expiries} expiries · "
    f"{len(snap.rows):,} contracts · as of {snap.asof:%Y-%m-%d %H:%M UTC}"
    + (f" · scaling QQQ→NQ ×{factor:.3f}" if factor != 1.0 else "")
)


def level_table(profile, title):
    if profile is None:
        st.info(f"No {title} expiry available.")
        return
    st.subheader(title + f" — {profile.label}")
    rows = {
        "Peak gamma strike": profile.peak_gamma_strike,
        "Gamma centroid": profile.gamma_centroid,
        "Zero-gamma flip": profile.zero_gamma,
        "Call wall": profile.call_wall,
        "Put wall": profile.put_wall,
    }
    disp = pd.DataFrame(
        {"level (native)": rows.values(),
         f"level ({unit})": [None if v is None else round(v * factor, 2) for v in rows.values()]},
        index=list(rows),
    )
    st.dataframe(disp, use_container_width=True)


def gex_chart(profile, title):
    if profile is None or profile.per_strike.empty:
        return
    df = profile.per_strike.reset_index()
    # scale strikes for display so the x-axis matches the chosen unit
    df["strike_disp"] = df["strike"] * factor
    df["net_gex_millions"] = df["net_gex"] / 1e6
    st.markdown(f"**{title} — net GEX by strike** (millions $/1% move)")
    chart_df = df.set_index("strike_disp")[["net_gex_millions"]]
    st.bar_chart(chart_df, color="#4c9be8", height=260)


left, right = st.columns(2)
with left:
    level_table(levels.weekly, "Weekly (HP)")
    gex_chart(levels.weekly, "Weekly")
with right:
    level_table(levels.monthly, "Monthly (MHP)")
    gex_chart(levels.monthly, "Monthly")

with st.expander("What am I looking at? (HP / MHP explained)"):
    st.markdown(
        """
**HP (weekly hedge pressure)** and **MHP (monthly hedge pressure)** are the
same calculation applied to two different expirations:

* Options **dealers delta-hedge** the contracts they're short, and their
  hedging intensity is proportional to **gamma × open interest**.
* The strike where that is greatest is the biggest **hedging magnet** — price
  tends to pin to it or pivot there on high volume.
* Compute it on the **nearest weekly expiry → HP**; on the **3rd-Friday
  monthly expiry → MHP**.

The other rows are the standard gamma structure: **call wall** (resistance),
**put wall** (support), and the **zero-gamma flip** (above it dealers dampen
volatility, below it they amplify it).

Levels are derived from **QQQ** options (the liquid Nasdaq-100 proxy) and, if
you enter your /NQ price, scaled onto the NQ future. Data via yfinance —
educational use, not financial advice.
        """
    )
