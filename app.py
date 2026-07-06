"""GammaLevels dashboard -- a live HP / MHP gamma-hedging indicator.

Run locally (needs network access to Yahoo Finance):

    pip install -r requirements.txt
    streamlit run app.py

Pick NQ or ES in the sidebar — it auto-fetches the index options (NDX/SPX, ETF
proxy as fallback) and the live future price, computes HP/MHP, and scales the
levels straight onto the future. No manual price entry.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from gammalevels import FUTURE_MAP, compute_hedge_levels, fetch_chain_for_future
from gammalevels.pinegen import to_pine

TV_CHART = {"NQ": "CME_MINI:NQ1!", "ES": "CME_MINI:ES1!"}
PROXY = {"NQ": "QQQ", "ES": "SPY"}

st.set_page_config(page_title="GammaLevels — HP / MHP", page_icon="📈", layout="wide")

METHOD_HELP = {
    "peak": "Strike with the greatest absolute dealer gamma (the biggest hedging magnet).",
    "centroid": "Gamma-weighted mean strike — a smooth, non-round 'pressure' level.",
    "flip": "Zero-gamma flip: where net dealer gamma crosses zero.",
    "callwall": "Largest positive-gamma strike (tends to act as resistance).",
    "putwall": "Largest negative-gamma strike (tends to act as support).",
}


@st.cache_data(ttl=120, show_spinner=False)
def load_future(future: str, max_expiries: int, min_oi: float, force_proxy: bool):
    """Fetch options + live future price for NQ/ES, cached for snappy tweaks."""
    prefer = PROXY[future] if force_proxy else None
    return fetch_chain_for_future(
        future, max_expiries=max_expiries, min_open_interest=min_oi, prefer_underlying=prefer
    )


# ---------------------------------------------------------------- sidebar
st.sidebar.title("GammaLevels")
st.sidebar.caption("Automated HP/MHP — you don't need his Discord post.")

future = st.sidebar.selectbox(
    "Future", list(FUTURE_MAP), index=0,
    format_func=lambda f: f"{f} · {FUTURE_MAP[f]['name']}",
)
method = st.sidebar.selectbox(
    "HP / MHP definition", list(METHOD_HELP), index=0,
    format_func=lambda m: m.capitalize(),
)
st.sidebar.caption(METHOD_HELP[method])

force_proxy = st.sidebar.checkbox(
    "Force free ETF proxy (QQQ/SPY)", value=False,
    help="Off = use the index options his levels actually come from (NDX/SPX) "
         "when available. On = always use the free ETF proxy.",
)
max_expiries = st.sidebar.slider("Expirations to load", 2, 16, 8)
min_oi = st.sidebar.number_input("Min open interest per strike", min_value=0.0, value=0.0, step=50.0)

if st.sidebar.button("↻ Refresh data", use_container_width=True):
    load_future.clear()

# ---------------------------------------------------------------- main
st.title("📈 Gamma Hedge Levels — HP / MHP")

try:
    inp = load_future(future, max_expiries, min_oi, force_proxy)
except Exception as exc:  # network / symbol errors surface here
    st.error(
        f"Couldn't load options for **{future}**: {exc}\n\n"
        "This dashboard needs outbound access to Yahoo Finance. If you're on a "
        "restricted network (or a sandbox), run it on your own machine."
    )
    st.stop()

snap = inp.snapshot
factor = inp.factor
unit = f"/{future}"
levels = compute_hedge_levels(snap.rows, snap.spot, snap.asof, method=method)
scaled = levels.scaled(factor)
is_proxy = inp.underlying in PROXY.values()

# headline metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"HP · Weekly ({unit})", scaled["hp"], help=f"Weekly expiry {levels.weekly_expiry}")
c2.metric(f"MHP · Monthly ({unit})", scaled["mhp"], help=f"Monthly expiry {levels.monthly_expiry}")
c3.metric(f"{future} price", round(inp.future_price, 2))
regime = "🟢 long-gamma (mean-revert)" if (levels.monthly and levels.monthly.net_gex_at_spot > 0) else "🔴 short-gamma (trend)"
c4.metric("Dealer regime (monthly)", regime)

src = f"{inp.underlying} ({'ETF proxy' if is_proxy else 'index'})"
st.caption(
    f"Options from **{src}** spot {snap.spot:.2f} · {snap.num_expiries} expiries · "
    f"{len(snap.rows):,} contracts · scaled ×{factor:.4f} onto {future} · "
    f"as of {snap.asof:%Y-%m-%d %H:%M UTC}"
)
if is_proxy:
    st.warning(
        "Using the ETF proxy — levels are directionally right but won't exactly "
        "match his index-derived numbers. Uncheck 'Force free ETF proxy' to try "
        "NDX/SPX index options.", icon="⚠️",
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

st.divider()
st.subheader("📤 Send to TradingView")
st.caption(
    "Pine Script can't fetch data itself, so this bakes the current levels into a "
    "ready-to-paste indicator. Copy it → TradingView → **Pine Editor** → paste → "
    f"**Add to chart** (use the `{TV_CHART[future]}` chart). Regenerate once or "
    "twice a day since open interest is end-of-day."
)
pine_src = to_pine(levels, factor, snap.asof, symbol_note=TV_CHART[future])
st.download_button(
    "⬇ Download gammalevels.pine", data=pine_src,
    file_name="gammalevels.pine", mime="text/plain", use_container_width=True,
)
st.code(pine_src, language="javascript")

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
