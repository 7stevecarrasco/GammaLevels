"""Generate a TradingView **Pine Script** that draws the computed levels.

Pine Script runs *inside* TradingView and cannot make network requests, so it
can't fetch options data itself.  The workflow instead is:

    1. This tool computes HP / MHP / walls / flip from QQQ options.
    2. :func:`to_pine` bakes those prices into a Pine v5 indicator.
    3. You paste it into TradingView's Pine editor on your ``CME_MINI:NQ1!``
       chart and "Add to chart".

Because open interest is end-of-day, refreshing the script once (or twice, at
the NY open) per session keeps the lines current.  Every level is exposed as an
``input.price`` so you can also nudge a line by dragging it in TradingView.

The generated script draws each level as a horizontal ray with a right-edge
label -- teal for the weekly bucket (HP), orange for the monthly (MHP), matching
the streamer's colour scheme.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .levels import HedgeLevels

# Colours picked to match the typical stream: teal weekly, orange monthly.
TEAL = "color.rgb(38, 198, 218)"
TEAL_DIM = "color.rgb(38, 198, 218, 40)"
ORANGE = "color.rgb(255, 152, 0)"
ORANGE_DIM = "color.rgb(255, 152, 0, 40)"
GRAY = "color.rgb(150, 150, 150)"


@dataclass
class _Level:
    var: str          # Pine identifier (unique)
    title: str        # input title / label text
    price: float
    color: str        # Pine colour expression
    width: int
    style: str        # "solid" | "dashed" | "dotted"
    group: str


def _collect_levels(levels: HedgeLevels, factor: float) -> List[_Level]:
    """Flatten a HedgeLevels result into drawable, non-null Pine levels."""
    out: List[_Level] = []
    wk = "Weekly (HP)"
    mo = "Monthly (MHP)"

    def add(var, title, price, color, width, style, group):
        if price is not None:
            out.append(_Level(var, title, round(price * factor, 2), color, width, style, group))

    if levels.weekly is not None:
        add("hp", "HP · Weekly", levels.hp, TEAL, 3, "solid", wk)
        add("wcw", "Weekly call wall", levels.weekly.call_wall, TEAL_DIM, 1, "dotted", wk)
        add("wpw", "Weekly put wall", levels.weekly.put_wall, TEAL_DIM, 1, "dotted", wk)
        add("wzg", "Weekly zero-gamma", levels.weekly.zero_gamma, TEAL, 1, "dashed", wk)

    if levels.monthly is not None:
        add("mhp", "MHP · Monthly", levels.mhp, ORANGE, 3, "solid", mo)
        add("mcw", "Monthly call wall", levels.monthly.call_wall, ORANGE_DIM, 1, "dotted", mo)
        add("mpw", "Monthly put wall", levels.monthly.put_wall, ORANGE_DIM, 1, "dotted", mo)
        add("mzg", "Monthly zero-gamma", levels.monthly.zero_gamma, ORANGE, 1, "dashed", mo)

    return out


def to_pine(
    levels: HedgeLevels,
    factor: float = 1.0,
    asof: Optional[datetime] = None,
    symbol_note: str = "CME_MINI:NQ1!",
    lookback_bars: int = 300,
) -> str:
    """Return Pine v5 source that draws ``levels`` (scaled by ``factor``).

    factor       : price scale (e.g. QQQ->NQ ratio). 1.0 leaves native prices.
    symbol_note  : just a comment reminding you which chart to use.
    lookback_bars: how far left the level rays are drawn from the last bar.
    """
    asof = asof or levels.asof
    items = _collect_levels(levels, factor)

    header = f"""//@version=5
// GammaLevels — HP / MHP dealer gamma-hedging levels
// Generated {asof:%Y-%m-%d %H:%M UTC} from QQQ options{'' if factor == 1.0 else f', scaled x{factor:.4f} onto /NQ'}
// Intended chart: {symbol_note}  (levels are absolute prices; any NQ chart works)
// Options OI is end-of-day — regenerate once or twice a day to stay current.
indicator("GammaLevels HP/MHP", overlay=true, max_lines_count=32, max_labels_count=32)

showWeekly  = input.bool(true,  "Show weekly (HP)",  group="Display")
showMonthly = input.bool(true,  "Show monthly (MHP)", group="Display")
showLabels  = input.bool(true,  "Show labels",        group="Display")
lookback    = input.int({lookback_bars}, "Ray lookback (bars)", minval=10, group="Display")
"""

    # input.price declarations
    inputs = ["\n// --- Level values (drag on chart to nudge) ---"]
    for lv in items:
        inputs.append(
            f'{lv.var} = input.price({lv.price}, "{lv.title}", group="{lv.group}")'
        )

    # drawing helper + persistent handles
    helper = """
// --- drawing helper: one persistent ray + label per level ---
draw_level(line _ln, label _lb, float _price, color _col, int _w, string _style, string _txt, bool _show) =>
    line.delete(_ln)
    label.delete(_lb)
    line rl = na
    label rb = na
    if _show and barstate.islast and not na(_price) and _price > 0
        rl := line.new(bar_index - lookback, _price, bar_index, _price, color=_col, width=_w, style=_style, extend=extend.right)
        if showLabels
            rb := label.new(bar_index, _price, _txt + "  " + str.tostring(_price, format.mintick), style=label.style_label_left, color=color.new(_col, 85), textcolor=_col, size=size.small)
    [rl, rb]
"""

    style_map = {"solid": "line.style_solid", "dashed": "line.style_dashed", "dotted": "line.style_dotted"}

    # persistent var handles + per-bar redraw
    decls = ["\n// --- persistent handles ---"]
    calls = ["\n// --- redraw every bar (helper only paints on the last bar) ---"]
    for lv in items:
        decls.append(f"var line {lv.var}_ln = na")
        decls.append(f"var label {lv.var}_lb = na")
        show_flag = "showWeekly" if lv.group.startswith("Weekly") else "showMonthly"
        calls.append(
            f"[{lv.var}_l, {lv.var}_b] = draw_level({lv.var}_ln, {lv.var}_lb, {lv.var}, "
            f"{lv.color}, {lv.width}, {style_map[lv.style]}, \"{lv.title}\", {show_flag})"
        )
        calls.append(f"{lv.var}_ln := {lv.var}_l")
        calls.append(f"{lv.var}_lb := {lv.var}_b")

    return "\n".join([header, *inputs, helper, *decls, *calls, ""])
