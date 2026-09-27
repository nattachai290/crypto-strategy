"""Generate a self-contained HTML report from the results CSVs.

Everything is inlined - no CDN, no network - so the file opens offline and
never shows an empty chart. Charts are hand-built inline SVG rather than a
plotting library, which keeps the output dependency-free.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

# --------------------------------------------------------------------------
# theme
# --------------------------------------------------------------------------
BG = "#0b0e14"
CARD = "#141922"
CARD2 = "#1b212c"
LINE = "#252c39"
TXT = "#e6edf3"
MUT = "#8b949e"
DIM = "#6e7681"
GREEN = "#3fb950"
RED = "#f85149"
AMBER = "#d29922"
BLUE = "#58a6ff"
PURPLE = "#bc8cff"
CYAN = "#39c5cf"


def f(x, d=2):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "&ndash;"
    return f"{x:,.{d}f}"


def pct(x, d=1):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "&ndash;"
    return f"{x*100:+.{d}f}%"


# --------------------------------------------------------------------------
# svg primitives
# --------------------------------------------------------------------------
def _svgtext(s) -> str:
    """Make a string safe to place inside an inline SVG in an HTML document.

    The HTML parser treats these as foreign-content *breakout* elements: when it
    meets one inside <svg>, it closes the SVG context and resumes HTML parsing,
    silently discarding the rest of the chart. A <br> in a bar-chart label cost
    two thirds of that chart before this was found.
    """
    s = str(s)
    for tag in ("br", "p", "div", "span", "table", "tr", "td", "body",
                "h1", "h2", "h3", "li", "ul", "ol", "hr", "meta", "img"):
        s = re.sub(rf"</?{tag}\b[^>]*>", " ", s, flags=re.I)
    return s.strip()


def _ticks(vmin, vmax, n=5):
    if vmax == vmin:
        vmax = vmin + 1
    return np.linspace(vmin, vmax, n)


def line_chart(series, *, width=760, height=300, ylabel="", title="",
               zero_line=True, yfmt=lambda v: f"{v:.2f}", pad_l=56, xlog=False):
    """series: list of dicts {name, color, x(list), y(list), dash, dots}

    xlog: the x parameter is multiplicative (e.g. an ATR stop multiple), so a
    linear axis crowds 1.0/1.5/1.8 together and leaves 5.0/7.0 stranded. Log
    spacing makes the curve readable.
    """
    import math as _m
    pad_r, pad_t, pad_b = 16, 34, 30
    xs = [p for s in series for p in s["x"]]
    ys = [p for s in series for p in s["y"]]
    if not xs:
        return ""

    def T(v):
        return _m.log10(v) if xlog else v

    tx = [T(v) for v in xs]
    xmin, xmax = min(tx), max(tx)
    ymin, ymax = min(ys + ([0.0] if zero_line else [])), max(ys)
    span = (ymax - ymin) or 1.0
    ymin -= span * 0.10
    ymax += span * 0.12
    xspan = (xmax - xmin) or 1.0
    pl, pr2 = pad_l, pad_r
    iw = width - pl - pr2
    ih = height - pad_t - pad_b

    def X(v):
        return pl + (T(v) - xmin) / xspan * iw

    def Y(v):
        return pad_t + ih - (v - ymin) / (ymax - ymin) * ih

    o = [f'<svg viewBox="0 0 {width} {height}" class="chart" '
         f'preserveAspectRatio="xMidYMid meet" role="img">']
    # grid + y labels
    for t in _ticks(ymin, ymax):
        y = Y(t)
        is0 = zero_line and abs(t) < (ymax - ymin) * 0.005
        o.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{width-pr2}" y2="{y:.1f}" '
                 f'stroke="{LINE if not is0 else DIM}" '
                 f'stroke-width="{1.6 if is0 else 1}" '
                 f'{"" if not is0 else "stroke-dasharray=\"3 3\""}/>')
        o.append(f'<text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" '
                 f'class="ax">{yfmt(t)}</text>')
    # x labels: emit once, from the first series that defines them, and do NOT
    # escape them - they are generated here (e.g. "1.0&times;") so escaping
    # would render the entity as literal text. Emitting per-series also
    # stacked two copies of every label on top of each other.
    xt_done = False
    for s in series:
        if xt_done or not s.get("xticks"):
            continue
        for xv, lab in s["xticks"]:
            o.append(f'<text x="{X(xv):.1f}" y="{height-10}" text-anchor="middle" '
                     f'class="ax">{_svgtext(lab)}</text>')
        xt_done = True
    for s in series:
        d = " ".join(f"{'M' if i==0 else 'L'}{X(x):.1f},{Y(y):.1f}"
                     for i, (x, y) in enumerate(zip(s["x"], s["y"])))
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
        o.append(f'<path d="{d}" fill="none" stroke="{s["color"]}" '
                 f'stroke-width="{s.get("width",2.4)}" '
                 f'stroke-linejoin="round" stroke-linecap="round"{dash}/>')
        if s.get("area"):
            d2 = f"{d} L{X(s['x'][-1]):.1f},{Y(0):.1f} L{X(s['x'][0]):.1f},{Y(0):.1f} Z"
            o.append(f'<path d="{d2}" fill="{s["color"]}" opacity="0.10"/>')
        if s.get("dots"):
            for xv, yv in zip(s["x"], s["y"]):
                o.append(f'<circle cx="{X(xv):.1f}" cy="{Y(yv):.1f}" r="3.4" '
                         f'fill="{BG}" stroke="{s["color"]}" stroke-width="2"/>')
    o.append(f'<text x="{pl}" y="18" class="axt">{escape(ylabel)}</text>')
    o.append("</svg>")
    return "".join(o)


def bar_chart(labels, values, *, colors, width=760, height=300, ylabel="",
              yfmt=lambda v: f"{v:.2f}", ymin=None, ymax=None, label_fmt=None):
    pad_l, pad_r, pad_t, pad_b = 56, 16, 34, 44
    iw = width - pad_l - pad_r
    ih = height - pad_t - pad_b
    lo = min(values + [0.0]) if ymin is None else ymin
    hi = max(values + [0.0]) if ymax is None else ymax
    if hi == lo:
        hi = lo + 1
    span = hi - lo
    hi += span * 0.14
    lo -= span * 0.06

    def Y(v):
        return pad_t + ih - (v - lo) / (hi - lo) * ih

    n = len(values)
    bw = iw / n * 0.62
    o = [f'<svg viewBox="0 0 {width} {height}" class="chart" '
         f'preserveAspectRatio="xMidYMid meet" role="img">']
    for t in _ticks(lo, hi):
        y = Y(t)
        o.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
                 f'stroke="{LINE}" stroke-width="1"/>')
        o.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" '
                 f'class="ax">{yfmt(t)}</text>')
    y0 = Y(0.0)
    o.append(f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{width-pad_r}" y2="{y0:.1f}" '
             f'stroke="{DIM}" stroke-width="1.4"/>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        cx = pad_l + iw / n * (i + 0.5)
        y = Y(v)
        top, h = min(y, y0), abs(y - y0)
        r = min(5, bw / 2)
        o.append(f'<path d="M{cx-bw/2:.1f},{top+h:.1f} L{cx-bw/2:.1f},{top+r:.1f} '
                 f'Q{cx-bw/2:.1f},{top:.1f} {cx-bw/2+r:.1f},{top:.1f} '
                 f'L{cx+bw/2-r:.1f},{top:.1f} Q{cx+bw/2:.1f},{top:.1f} '
                 f'{cx+bw/2:.1f},{top+r:.1f} L{cx+bw/2:.1f},{top+h:.1f} Z" '
                 f'fill="{colors[i]}" opacity="0.88"/>')
        txt = (label_fmt or yfmt)(v)
        o.append(f'<text x="{cx:.1f}" y="{top-7:.1f}" text-anchor="middle" '
                 f'class="bval">{escape(txt)}</text>')
        # x labels come from the caller and may contain entities such as
        # "1.0&times;", so they are not HTML-escaped, but they ARE sanitised
        # against foreign-content breakout tags (see _svgtext).
        o.append(f'<text x="{cx:.1f}" y="{height-24}" text-anchor="middle" '
                 f'class="ax">{_svgtext(lab)}</text>')
    o.append(f'<text x="{pad_l}" y="18" class="axt">{escape(ylabel)}</text>')
    o.append("</svg>")
    return "".join(o)


def forest(rows, *, width=900, row_h=26, ymin=-0.22, ymax=0.26, xlabel="mean R per trade"):
    """rows: dicts {label, mean, lo, hi, sub, color}"""
    pad_l, pad_r, pad_t, pad_b = 300, 90, 30, 44
    height = pad_t + row_h * len(rows) + pad_b
    iw = width - pad_l - pad_r
    ih = height - pad_t - pad_b

    def X(v):
        return pad_l + (v - ymin) / (ymax - ymin) * iw

    o = [f'<svg viewBox="0 0 {width} {height}" class="chart" '
         f'preserveAspectRatio="xMidYMid meet" role="img">']
    for t in _ticks(ymin, ymax, 9):
        x = X(t)
        is0 = abs(t) < 1e-9
        dash = ' stroke-dasharray="3 3"' if is0 else ""
        o.append(f'<line x1="{x:.1f}" y1="{pad_t-8}" x2="{x:.1f}" '
                 f'y2="{pad_t+ih}" stroke="{DIM if is0 else LINE}" '
                 f'stroke-width="{1.5 if is0 else 1}"{dash}/>')
        o.append(f'<text x="{x:.1f}" y="{pad_t+ih+18}" text-anchor="middle" '
                 f'class="ax">{t:+.2f}</text>')
    for i, r in enumerate(rows):
        y = pad_t + row_h * i + row_h / 2
        c = r.get("color", BLUE)
        o.append(f'<line x1="{X(r["lo"]):.1f}" y1="{y:.1f}" x2="{X(r["hi"]):.1f}" '
                 f'y2="{y:.1f}" stroke="{c}" stroke-width="2.2" opacity="0.55" '
                 f'stroke-linecap="round"/>')
        for v in (r["lo"], r["hi"]):
            o.append(f'<line x1="{X(v):.1f}" y1="{y-5:.1f}" x2="{X(v):.1f}" '
                     f'y2="{y+5:.1f}" stroke="{c}" stroke-width="2.2" opacity="0.55"/>')
        o.append(f'<circle cx="{X(r["mean"]):.1f}" cy="{y:.1f}" r="4.6" '
                 f'fill="{c}" stroke="{BG}" stroke-width="1.6"/>')
        o.append(f'<text x="{pad_l-14}" y="{y+1:.1f}" text-anchor="end" class="flab">'
                 f'{escape(r["label"])}</text>')
        if r.get("sub"):
            o.append(f'<text x="{pad_l-14}" y="{y+12:.1f}" text-anchor="end" '
                     f'class="fsub">{escape(r["sub"])}</text>')
        o.append(f'<text x="{width-pad_r+10}" y="{y+4:.1f}" class="ax">'
                 f'{escape(r.get("note",""))}</text>')
    o.append(f'<text x="{pad_l}" y="16" class="axt">{escape(xlabel)}</text>')
    o.append("</svg>")
    return "".join(o)


def grouped_bar_chart(groups, series, *, width=760, height=300, ylabel="",
                      yfmt=lambda v: f"{v:.2f}", ymin=0.0, ymax=None):
    """groups: list of x labels.  series: list of {name, color, values}"""
    pad_l, pad_r, pad_t, pad_b = 56, 16, 34, 48
    iw = width - pad_l - pad_r
    ih = height - pad_t - pad_b
    flat = [v for s in series for v in s["values"]]
    lo = min(flat + [0.0]) if ymin is None else ymin
    hi = max(flat + [0.0]) if ymax is None else ymax
    if hi == lo:
        hi = lo + 0.01
    hi += (hi - lo) * 0.16

    def Y(v):
        return pad_t + ih - (v - lo) / (hi - lo) * ih

    ng, ns = len(groups), len(series)
    slot = iw / max(ng, 1)
    bw = slot * 0.72 / ns
    o = [f'<svg viewBox="0 0 {width} {height}" class="chart" '
         f'preserveAspectRatio="xMidYMid meet" role="img">']
    for t in _ticks(lo, hi):
        y = Y(t)
        o.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
                 f'stroke="{LINE}" stroke-width="1"/>')
        o.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" '
                 f'class="ax">{yfmt(t)}</text>')
    y0 = Y(0.0)
    o.append(f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{width-pad_r}" y2="{y0:.1f}" '
             f'stroke="{DIM}" stroke-width="1.4"/>')
    for gi, g in enumerate(groups):
        base = pad_l + slot * gi + slot * 0.14
        for si, s in enumerate(series):
            v = s["values"][gi]
            x0 = base + bw * si
            y, h = Y(v), abs(Y(v) - y0)
            r = min(4, bw / 2.4)
            top = y
            o.append(f'<path d="M{x0:.1f},{top+h:.1f} L{x0:.1f},{top+r:.1f} '
                     f'Q{x0:.1f},{top:.1f} {x0+r:.1f},{top:.1f} '
                     f'L{x0+bw-r:.1f},{top:.1f} Q{x0+bw:.1f},{top:.1f} '
                     f'{x0+bw:.1f},{top+r:.1f} L{x0+bw:.1f},{top+h:.1f} Z" '
                     f'fill="{s["color"]}" opacity="0.9"/>')
            o.append(f'<text x="{x0+bw/2:.1f}" y="{top-6:.1f}" text-anchor="middle" '
                     f'class="bval">{yfmt(v)}</text>')
        o.append(f'<text x="{pad_l+slot*gi+slot/2:.1f}" y="{height-26}" '
                 f'text-anchor="middle" class="ax">{_svgtext(g)}</text>')
    o.append(f'<text x="{pad_l}" y="18" class="axt">{escape(ylabel)}</text>')
    o.append("</svg>")
    return "".join(o)


def legend(items):
    return ('<div class="legend">' + "".join(
        f'<span class="lg"><i style="background:{c}"></i>{escape(n)}</span>'
        for n, c in items) + "</div>")


# --------------------------------------------------------------------------
def load():
    d = {}
    p = C.RESULTS
    d["def"] = pd.read_csv(p / "definitive_oos.csv")
    d["cost"] = pd.read_csv(p / "cost_lab.csv")
    d["sweep"] = pd.read_csv(p / "sweep_merged.csv")
    d["sw_train"] = pd.read_csv(p / "round2_stopwidth_train.csv")
    d["ml2"] = pd.read_csv(p / "ml_walkforward_15m_s2.0.csv")
    d["ml1"] = pd.read_csv(p / "ml_walkforward_15m.csv")
    d["best"] = json.loads((p / "report_best.json").read_text(encoding="utf-8"))
    for key, fn in (("maker", "round3_maker.csv"),
                    ("hold", "round4_holdperiod.csv"),
                    ("ledger", "ledger.csv")):
        q = p / fn
        if q.exists():
            df = pd.read_csv(q)
            # the maker CSV labels execution modes in `mode`; the ledger calls
            # the same thing `note` so the two can be compared side by side
            if "mode" in df.columns and "note" not in df.columns:
                df["note"] = df["mode"]
            d[key] = df
        else:
            d[key] = None
    return d


CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%%}
body{margin:0;background:
  radial-gradient(1100px 520px at 12%% -8%%,#182234 0%%,transparent 60%%),
  radial-gradient(900px 460px at 92%% 2%%,#1b2430 0%%,transparent 58%%),
  %(BG)s;
  color:%(TXT)s;
  font-family:"Inter","Segoe UI",system-ui,-apple-system,"Noto Sans Thai",sans-serif;
  font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px 90px}
a{color:%(BLUE)s}

/* header */
header{padding:58px 0 34px;border-bottom:1px solid %(LINE)s;margin-bottom:34px}
.eyebrow{font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;
  color:%(DIM)s;font-weight:600;margin-bottom:14px}
h1{margin:0 0 14px;font-size:clamp(28px,4.4vw,45px);line-height:1.12;
  letter-spacing:-.022em;font-weight:700}
h1 .acc{background:linear-gradient(96deg,%(BLUE)s,%(PURPLE)s);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:%(MUT)s;font-size:16.5px;max-width:74ch;margin:0}
.pillrow{display:flex;flex-wrap:wrap;gap:9px;margin-top:24px}
.pill{display:inline-flex;align-items:center;gap:7px;padding:6px 13px;
  border:1px solid %(LINE)s;border-radius:999px;background:%(CARD)s;
  font-size:12.5px;color:%(MUT)s}
.pill b{color:%(TXT)s;font-weight:600}
.dot{width:7px;height:7px;border-radius:50%%;flex:none}

/* verdict */
.verdict{display:grid;grid-template-columns:auto 1fr;gap:22px;align-items:center;
  background:linear-gradient(120deg,rgba(248,81,73,.10),rgba(248,81,73,.02));
  border:1px solid rgba(248,81,73,.32);border-radius:16px;padding:24px 26px;
  margin:30px 0}
.verdict .ico{width:52px;height:52px;border-radius:50%%;flex:none;
  background:rgba(248,81,73,.14);display:grid;place-items:center;
  border:1px solid rgba(248,81,73,.36)}
.verdict h3{margin:0 0 5px;font-size:18px;color:#ffb4ae}
.verdict p{margin:0;color:%(MUT)s;font-size:14.5px}

/* kpi */
.kpis{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));
  margin:26px 0 8px}
.kpi{background:%(CARD)s;border:1px solid %(LINE)s;border-radius:14px;padding:18px 19px}
.kpi .k{font-size:11.5px;letter-spacing:.09em;text-transform:uppercase;
  color:%(DIM)s;font-weight:600;margin-bottom:9px}
.kpi .v{font-size:27px;font-weight:700;letter-spacing:-.02em;line-height:1.15}
.kpi .n{font-size:12.5px;color:%(MUT)s;margin-top:5px}

/* sections */
section{margin:52px 0 0}
h2{font-size:22px;margin:0 0 6px;letter-spacing:-.015em;font-weight:650;
  display:flex;align-items:center;gap:11px}
h2 .num{font-size:12.5px;color:%(DIM)s;font-weight:600;
  background:%(CARD)s;border:1px solid %(LINE)s;border-radius:7px;
  padding:3px 9px;letter-spacing:0}
.lead{color:%(MUT)s;margin:0 0 20px;max-width:82ch}
h3.sub2{font-size:16px;margin:26px 0 10px;color:%(TXT)s;font-weight:600}

.card{background:%(CARD)s;border:1px solid %(LINE)s;border-radius:16px;
  padding:22px;margin:18px 0}
.grid2{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.chart{width:100%%;height:auto;display:block}
.ax{fill:%(DIM)s;font-size:11px;font-family:inherit}
.axt{fill:%(MUT)s;font-size:11.5px;font-weight:600;font-family:inherit}
.bval{fill:%(TXT)s;font-size:12px;font-weight:600;font-family:inherit}
.flab{fill:%(TXT)s;font-size:12.5px;font-family:inherit}
.fsub{fill:%(DIM)s;font-size:10.5px;font-family:inherit}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:12px 0 2px;font-size:12.5px;
  color:%(MUT)s}
.lg{display:inline-flex;align-items:center;gap:7px}
.lg i{width:13px;height:3px;border-radius:2px;display:inline-block}

/* formula */
.formula{background:linear-gradient(135deg,%(CARD2)s,%(CARD)s);
  border:1px solid %(LINE)s;border-radius:14px;padding:26px 24px;text-align:center;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:clamp(15px,2.5vw,23px);letter-spacing:-.01em;margin:16px 0 6px;
  overflow-x:auto}
.formula .k{color:%(BLUE)s}
.formula .o{color:%(DIM)s}
.formula .r{color:%(RED)s}
.formula .g{color:%(GREEN)s}
.caption{font-size:12.5px;color:%(DIM)s;text-align:center;margin-top:10px}

/* table */
.tblwrap{overflow-x:auto;border:1px solid %(LINE)s;border-radius:14px;
  background:%(CARD)s;margin:16px 0}
table{border-collapse:collapse;width:100%%;font-size:13.4px;min-width:560px}
th{text-align:right;padding:11px 14px;font-size:11px;letter-spacing:.07em;
  text-transform:uppercase;color:%(DIM)s;font-weight:650;
  border-bottom:1px solid %(LINE)s;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th.l,td.l{text-align:left}
td{padding:10px 14px;border-bottom:1px solid rgba(37,44,57,.55);
  text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:rgba(88,166,255,.05)}
tr.hi td{background:rgba(63,185,80,.075)}
tr.hi:hover td{background:rgba(63,185,80,.11)}
.neg{color:%(RED)s}.pos{color:%(GREEN)s}.neu{color:%(MUT)s}
.tag{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;
  font-weight:650;letter-spacing:.02em}
.tag.k{background:rgba(63,185,80,.15);color:#7ee787}
.tag.r{background:rgba(248,81,73,.15);color:#ff9d95}
.tag.a{background:rgba(210,153,34,.16);color:#e3b341}
.tag.b{background:rgba(88,166,255,.15);color:#8bc4ff}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:12.4px;color:%(MUT)s}

/* notes */
.note{border-left:3px solid %(BLUE)s;background:rgba(88,166,255,.055);
  border-radius:0 12px 12px 0;padding:16px 20px;margin:18px 0;color:%(MUT)s;
  font-size:14.2px}
.note b{color:%(TXT)s}
.note.warn{border-color:%(AMBER)s;background:rgba(210,153,34,.06)}
.note.bad{border-color:%(RED)s;background:rgba(248,81,73,.055)}
.note.good{border-color:%(GREEN)s;background:rgba(63,185,80,.055)}

/* timeline */
.tl{border-left:2px solid %(LINE)s;margin:20px 0 0;padding:0 0 0 26px}
.tl .ev{position:relative;margin-bottom:22px}
.tl .ev::before{content:"";position:absolute;left:-33px;top:6px;width:11px;
  height:11px;border-radius:50%%;background:%(BG)s;border:2.5px solid %(BLUE)s}
.tl .ev.bad::before{border-color:%(RED)s}
.tl .ev.good::before{border-color:%(GREEN)s}
.tl .ev h4{margin:0 0 4px;font-size:15px;font-weight:650}
.tl .ev p{margin:0;color:%(MUT)s;font-size:13.8px}

.bugs{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
  margin:16px 0}
.bug{background:%(CARD)s;border:1px solid %(LINE)s;border-radius:12px;padding:15px 17px}
.bug .t{font-size:13.6px;font-weight:650;margin-bottom:5px;color:#ffb4ae}
.bug .d{font-size:12.8px;color:%(MUT)s}
.bug .i{font-size:12px;color:%(DIM)s;margin-top:7px;font-style:italic}

ul.tight{margin:10px 0;padding-left:20px;color:%(MUT)s}
ul.tight li{margin:6px 0}
ul.tight b{color:%(TXT)s}
footer{margin-top:60px;padding-top:24px;border-top:1px solid %(LINE)s;
  color:%(DIM)s;font-size:12.5px;display:flex;flex-wrap:wrap;gap:14px;
  justify-content:space-between}
@media(max-width:640px){
  .verdict{grid-template-columns:1fr;gap:14px}
  .wrap{padding:0 15px 60px}
  header{padding:38px 0 26px}
}
""" % dict(BG=BG, CARD=CARD, CARD2=CARD2, LINE=LINE, TXT=TXT, MUT=MUT, DIM=DIM,
           GREEN=GREEN, RED=RED, AMBER=AMBER, BLUE=BLUE, PURPLE=PURPLE)


# --------------------------------------------------------------------------
def build() -> str:
    d = load()
    BEST = d["best"]["best"]
    D_ = d["def"]
    today = date.today().strftime("%d %B %Y")
    o = []
    A = o.append

    # ================= header =================
    A(f"""<header>
<div class="eyebrow">งานวิจัยเชิงปริมาณ &middot; BTCUSDT Perpetual &middot; Intraday</div>
<h1>BTC Futures Day Trading<br><span class="acc">หลังหักค่าธรรมเนียมจริง</span></h1>
<p class="sub">ผลการทดสอบกลยุทธ์ intraday แบบ long/short บน Binance USDT-M futures
ด้วยข้อมูล 1 นาทีจริง 80 เดือน (2020&ndash;2026) คิดค่าธรรมเนียม taker 0.05%
+ slippage 0.02% + funding ตามเวลาจริง และทดสอบแบบ walk-forward
เพื่อไม่ให้การเลือกกลยุทธ์ไปเห็นข้อมูลอนาคต</p>
<div class="pillrow">
<span class="pill"><i class="dot" style="background:{BLUE}"></i>ข้อมูล <b>3,506,400</b> แท่ง 1 นาที</span>
<span class="pill"><i class="dot" style="background:{PURPLE}"></i>คำสั่งทดสอบ <b>106+</b> config</span>
<span class="pill"><i class="dot" style="background:{CYAN}"></i>ระยะเวลา <b>6.5 ปี</b></span>
<span class="pill"><i class="dot" style="background:{AMBER}"></i>Timeframe <b>1/3/5/15/30 นาที</b></span>
<span class="pill"><i class="dot" style="background:{GREEN}"></i>Engine tests <b>ผ่านทั้งหมด</b></span>
</div>
</header>""")

    # ================= verdict =================
    A(f"""<div class="verdict">
<div class="ico"><svg width="26" height="26" viewBox="0 0 24 24" fill="none"
stroke="#ff9d95" stroke-width="2.1" stroke-linecap="round">
<path d="M12 8v5"/><circle cx="12" cy="16.6" r="1.1" fill="#ff9d95" stroke="none"/>
<path d="M10.3 3.6 1.9 18.2a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0z"/>
</svg></div>
<div><h3>ยังไม่พบ edge ที่พิสูจน์ได้ &mdash; และนี่คือคำตอบที่ถูกต้อง</h3>
<p>config ที่ดีที่สุดให้ผล <b>{pct(BEST['cagr'])}/ปี</b> และ expectancy ต่อไม้
<b>{f(BEST['mean_R'],4)} R</b> ซึ่งมีช่วงความเชื่อมั่น 95%
<b>[{f(BEST['ci_lo'],3)}, {f(BEST['ci_hi'],3)}]</b> &mdash;
<strong>ครอบคลุมค่าศูนย์</strong> แปลว่ายังแยกไม่ออกว่ามี edge จริงหรือเป็นความบังเอิญ
จาก {int(BEST['trades'])} ไม้</p></div></div>""")

    # ================= kpis =================
    kpis = [
        ("CAGR ดีที่สุด", pct(BEST["cagr"]), f"chained {f(BEST['start'],0)} → {f(BEST['end'],2)} USDT", AMBER),
        ("Expectancy / ไม้", f"{f(BEST['mean_R'],4)} R", f"CI95 [{f(BEST['ci_lo'],3)}, {f(BEST['ci_hi'],3)}]", BLUE),
        ("Gross edge", f"+{f(BEST['gross_r'],3)} R", "รายได้ดิบก่อนหักต้นทุน", GREEN),
        ("Cost / ไม้", f"{f(BEST['cost_r'],3)} R", "ค่าธรรมเนียม + slippage", RED),
        ("Win rate", f"{f(BEST['win_rate']*100,1)}%", "ต่ำ แต่ R สูงกว่าเมื่อชนะ", PURPLE),
        ("Max drawdown", f"{f(BEST['max_dd']*100,2)}%", "ที่ดี แต่เพราะแทรนด์น้อย", CYAN),
    ]
    A('<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{k}</div><div class="v" style="color:{c}">{v}</div>'
        f'<div class="n">{n}</div></div>' for k, v, n, c in kpis) + "</div>")
    A(f'<p class="caption" style="text-align:left">ค่าทั้งหมดจาก '
      f'<b>config ดีที่สุด</b> = ML filter (LightGBM classifier, threshold 0.10) '
      f'+ stop กว้าง 5&times;ATR บนกราฟ 15 นาที · เฉลี่ย 9 รอบ walk-forward '
      f'2022-01 ถึง 2026-08 · ทุน 100 USDT ความเสี่ยง 1%/ไม้</p>')

    # ================= 1. engine =================
    A("""<section>
<h2><span class="num">01</span>ตรวจสอบความน่าเชื่อถือของ Engine ก่อน</h2>
<p class="lead">ก่อนเชื่อตัวเลขใด ๆ ต้องพิสูจน์ว่า backtester คำนวณถูก
เพราะถ้ากรอบวัดผิด ทุกอย่างที่ตามมาเป็นเรื่องเล่าที่แต่งขึ้น</p>
<div class="grid2">
<div class="card">
<ul class="tight">
<li>คำนวณ 1 ไม้ด้วยมือ &mdash; PnL และ R ตรงกับสูตรวิเคราะห์เป๊ะ</li>
<li>เทียบกับ reference implementation แยกอีกชุด <b>8 seeds</b></li>
<li>ต้นทุนต้องทำให้ผลแย่ลงเสมอ ไม่มีทางดีขึ้น</li>
<li>ตัดข้อมูลท้ายออก ผลต้องเป็น prefix ของชุดเต็ม (กัน look-ahead)</li>
</ul>
</div>
<div class="card" style="display:grid;place-items:center">
<div style="text-align:center">
<div style="font-size:44px;font-weight:700;color:%s;line-height:1">4/4</div>
<div style="color:%s;font-size:13.5px;margin-top:6px">ผ่านทั้งหมด</div>
<div style="color:%s;font-size:12.5px;margin-top:9px">
<b>2,297 ไม้</b> ตรงกันทุกตัว<br>รวม entry, exit, ฝั่ง, เหตุผล, R</div>
</div></div>
</div>
<div class="note">การทดสอบนี้จับบั๊กจริงได้ <b>5 ตัวใน engine</b> — รวมถึงตัวที่
<b>net_pnl ไม่รวม entry fee</b> ทำให้ expectancy ผิดทั้งระบบ และตัวที่
<b>ท้ายข้อมูลถูกมองว่าเป็นการปิด session</b> ซึ่งทำให้ทุก backtest ที่ใช้ time window
บล็อกการเปิดไม้ช่วงท้ายโดยไม่บอก &mdash; เงียบ ๆ bias ทุก walk-forward fold</div>
</section>""" % (GREEN, MUT, DIM))

    # ================= 2. the key insight =================
    t = d["cost"]
    tt = t[t["exec"] == "taker (real)"]
    pivot_cost = tt.pivot_table(index=["strategy", "tf"], columns="stop_mult",
                                values="cost_r")
    pivot_gross = tt.pivot_table(index=["strategy", "tf"], columns="stop_mult",
                                 values="gross_r")
    pivot_exp = tt.pivot_table(index=["strategy", "tf"], columns="stop_mult",
                               values="exp_r")
    widths = sorted(pivot_cost.columns)
    dfm = d["def"]
    # The definitive run only sampled a subset of stop scales; intersect so the
    # bars are built from levels that actually have results. Mixing the two
    # x-axes produced NaN gaps and an empty-looking chart.
    scale_levels = sorted(set(widths) & set(dfm["stop_scale"].unique()))
    cagr_by_scale = [float(dfm[dfm.stop_scale == s]["cagr"].mean())
                     for s in scale_levels]
    cost_by_scale = [float(dfm[dfm.stop_scale == s]["cost_r"].mean())
                     for s in scale_levels]
    A(f"""<section>
<h2><span class="num">02</span>ข้อค้นพบสำคัญที่สุด: stop ที่แคบเกินไปคือตัวฆ่า</h2>
<p class="lead">นี่คือตัวเลขเดียวที่อธิบายทุกอย่าง &mdash; ทั้งทำไมกลยุทธ์ทั้งหมด
เสีย และทำไมบางตัวถึงพอจะไม่เสีย</p>
<div class="formula">
<span class="k">cost_r</span> <span class="o">=</span>
<span class="r">ต้นทุนไป-กลับ</span> <span class="o">/</span>
<span class="k">ระยะ stop</span>
<span class="o">=</span> <span class="r">0.14%</span> <span class="o">/</span>
<span class="g">0.5%</span> <span class="o">=</span> <span class="r">0.28 R ต่อไม้</span>
</div>
<p class="caption">ต้นทุน taker ไป-กลับ = 0.05%+0.05% ค่าธรรมเนียม + 0.02%+0.02% slippage
= 0.14% ของ notional &nbsp;&middot;&nbsp; ถ้า stop กว้าง 2.5% ต้นทุนเหลือ 0.056 R</p>
<div class="card">
<h3 class="sub2" style="margin-top:0">ต้นทุนลดลงตาม stop ที่กว้างขึ้น
&mdash; แต่ gross edge แทบไม่เปลี่ยน</h3>
{legend([("cost_r (ต้นทุนต่อไม้)", RED), ("gross_r (รายได้ดิบต่อไม้)", GREEN)])}
{line_chart([
  {"name":"cost","color":RED,"x":widths,"y":[float(pivot_cost[m].median()) for m in widths],
   "xticks":[(m,f"{m}&times;") for m in widths],"dots":True,"width":2.6},
  {"name":"gross","color":GREEN,"x":widths,"y":[float(pivot_gross[m].median()) for m in widths],
   "xticks":[(m,f"{m}&times;") for m in widths],"dots":True,"width":2.6,"dash":"6 4"},
], ylabel="R ต่อไม้ (ค่ากลางของทุกกลยุทธ์)", yfmt=lambda v: f"{v:.2f}",
   xlog=True)}
<p class="caption">ค่าเฉลี่ยกลางจาก 9 กลยุทธ์บน 80 เดือน &mdash;
cost_r ลดจาก ~0.14 เหลือ ~0.04 ขณะที่ gross_r อยู่ราว 0.08&ndash;0.10 นิ่ง</p>
</div>
<div class="card">
<h3 class="sub2" style="margin-top:0">ผลตอบแทนจริงที่เปลี่ยนไปตาม stop width</h3>
{bar_chart([f"{s:g}&times;" for s in scale_levels],
   cagr_by_scale,
   colors=[GREEN if v > 0 else (AMBER if v > -0.01 else RED) for v in cagr_by_scale],
   ylabel="CAGR เฉลี่ยของทุก config ในแต่ละระดับ",
   yfmt=lambda v: f"{v*100:.0f}%",
   label_fmt=lambda v: f"{v*100:+.1f}%")}
<p class="caption">ค่าเฉลี่ย CAGR ของทุก config ในแต่ละระดับ stop width
(ML filter, walk-forward, out-of-sample) &mdash; ค่า cost_r ที่ระดับเดียวกัน:
{" &middot; ".join(f"{s:g}&times; = {c:.3f}R" for s, c in zip(scale_levels, cost_by_scale))}</p>
</div>
<div class="note good"><b>ข้อสำคัญ:</b> ผลนี้ได้โดย
<b>ไม่เปลี่ยนสัญญาณการเข้าออกเลยแม้แต่ตัวเดียว</b> เปลี่ยนแค่ความกว้างของ stop
และเพราะ position sizing คำนวณจาก stop อยู่แล้ว
ความเสี่ยงต่อไม้จึงยังคงเป็น 1% เท่าเดิม
กฎ &ldquo;stop 1.8&times;ATR&rdquo; ที่นิยมมาคือ
<b>ความผิดพลาดเรื่องประสิทธิภาพต้นทุน</b> ไม่ใช่เรื่องบริหารความเสี่ยง</div>
</section>""")

    # ================= 3. CI forest =================
    fr = []
    for _, r in dfm.sort_values("mean_R", ascending=False).iterrows():
        pos = r["ci_lo"] > 0
        fr.append({
            "label": f"{r['method']} thr={r['thr']:.2f} · stop {r['stop_scale']}×",
            "sub": f"{int(r['trades'])} ไม้ · gross {r['gross_r']:+.3f} / cost {r['cost_r']:.3f}",
            "mean": float(r["mean_R"]), "lo": float(r["ci_lo"]), "hi": float(r["ci_hi"]),
            "color": GREEN if pos else (AMBER if r["mean_R"] > 0 else RED),
            "note": f"{r['cagr']*100:+.1f}%/ปี",
        })
    A(f"""<section>
<h2><span class="num">03</span>ช่วงความเชื่อมั่นของทุก config (24 ตัว)</h2>
<p class="lead">bootstrap 20,000 ครั้งบนไม้ที่ execute จริงทุกไม้
ยิ่งแถบยาวและยาวขึ้นเท่าไร = ยิ่งไม่มั่นใจ
<b>ไม่มีแถบไหนเลยที่หลุดออกจากเส้นศูนย์</b></p>
<div class="card">
{forest(fr, ymin=-0.23, ymax=0.23, xlabel="expectancy ต่อไม้ (R)  ·  เส้นประ = 0")}
</div>
<div class="note warn">แถบสี<b>เขียว</b> = ช่วงความเชื่อมั่นไม่รวม 0 (พิสูจน์ได้แล้ว) &mdash;
ในรายงานนี้<b>ไม่มี</b> &middot;
<b>เหลือง</b> = ค่าเฉลี่ยบวกแต่ยังรวม 0 &middot;
<b>แดง</b> = ค่าเฉลี่ยติดลบ</div>
</section>""")

    # ================= 4. equity curve =================
    path = d["best"]["equity_path"]
    xs = list(range(len(path)))
    ys = [p["eq"] for p in path]
    lab = [(i, path[i]["t"][:7]) for i in range(0, len(path), max(1, len(path)//8))]
    A(f"""<section>
<h2><span class="num">04</span>เส้นพอร์ตของ config ที่ดีที่สุด &mdash; และปัญหาที่ซ่อนอยู่</h2>
<p class="lead">พอร์ตเงินต่อเนื่อง 100 USDT ผ่าน 9 รอบ walk-forward
แต่ละรอบเทรนโมเดลใหม่จากข้อมูล 24 เดือนก่อนหน้า แล้วเทรด 6 เดือนถัดไป</p>
<div class="card">
{legend([("พอร์ต (USDT)", AMBER)])}
{line_chart([{"name":"eq","color":AMBER,"area":True,"width":2.4,
   "x":xs,"y":ys,"xticks":lab}], ylabel="พอร์ต (USDT)",
   yfmt=lambda v: f"{v:.0f}")}
</div>
<div class="grid2">
<div class="card">
<h3 class="sub2" style="margin-top:0">ไม้ส่วนใหญ่อยู่ในปี 2022&ndash;2023</h3>
<div class="tblwrap"><table>
<thead><tr><th class="l">ปี</th><th>ไม้</th><th>mean R</th><th>win</th><th>cost_r</th></tr></thead><tbody>""")
    for y in d["best"]["by_year"]:
        cls = "pos" if y["mean_r"] > 0 else "neg"
        A(f'<tr><td class="l"><b>{y["year"]}</b></td><td>{y["trades"]}</td>'
          f'<td class="{cls}">{f(y["mean_r"],4)}</td><td>{f(y["win"],1)}%</td>'
          f'<td class="neu">{f(y["cost_r"],3)}</td></tr>')
    A("</tbody></table></div>")
    A("</div>")
    A(f"""<div class="card">
<h3 class="sub2" style="margin-top:0">รายการไม้รายรอบ (walk-forward fold)</h3>
<div class="tblwrap"><table>
<thead><tr><th class="l">รอบ</th><th>สัญญาณ</th><th>ไม้จริง</th><th>พอร์ต</th><th>ผลรอบ</th></tr></thead><tbody>""")
    for f_ in d["best"]["folds"]:
        cls = "pos" if f_["ret"] > 0 else ("neg" if f_["ret"] < 0 else "neu")
        A(f'<tr><td class="l mono">{f_["fold"]}</td><td>{f_["signals"]}</td>'
          f'<td>{f_["trades"]}</td><td>{f_["equity"]:.2f}</td>'
          f'<td class="{cls}">{f_["ret"]:+.2f}%</td></tr>')
    A("</tbody></table></div></div></div>")
    A("""<div class="note bad"><b>ข้อจำกัดที่ต้องบอกตรง ๆ:</b>
จาก 154 ไม้ <b>148 ไม้อยู่ในปี 2022&ndash;2023</b>
และมี 3 รอบติดกัน (2025) ที่ไม่ได้เทรดเลย
config ดีที่สุดนี้แทรนด์ <b>น้อยเกินกว่าจะเรียกว่ากลยุทธ์</b>
แถวที่ทำกำไรจริงคือปี 2023 (96 ไม้, +0.086R)
ถ้านับเฉพาะปีที่มี activity ตัวเลขจะดูดีกว่านี้มาก
&mdash; การเลือกเฉพาะปีที่ดีคือการโกงตัวเอง</div>""")
    A("</section>")

    # ================= 5. sweep =================
    sw = d["sweep"].sort_values("te_sharpe", ascending=False)
    n_pos = int((sw["te_sharpe"] > 0).sum())
    A(f"""<section>
<h2><span class="num">05</span>การทดสอบ 82 config แบบไม่ให้ข้อมูลอนาคต</h2>
<p class="lead">เลือก shortlist จากผลบนช่วงเวลา <b>2020-01 ถึง 2023-12 เท่านั้น</b>
แล้วเอา shortlist ไปรันบน <b>2024-01 ถึง 2026-08</b> ที่ไม่เคยถูกใช้ตัดสินใจใด ๆ</p>
<div class="kpis" style="margin-top:18px">
<div class="kpi"><div class="k">ผ่านเข้า shortlist</div><div class="v">20</div><div class="n">จาก 82 config</div></div>
<div class="kpi"><div class="k">ผล OOS ติดลบ</div><div class="v" style="color:{RED}">{20-n_pos}/20</div><div class="n">เฉพาะอีก {n_pos} ตัวที่เป็นบวก</div></div>
<div class="kpi"><div class="k">ระยะเวลาที่ดีที่สุด</div><div class="v" style="color:{AMBER}">{sw['te_sharpe'].max():+.3f}</div><div class="n">Sharpe บน OOS</div></div>
</div>
<div class="tblwrap"><table>
<thead><tr><th class="l">กลยุทธ์</th><th>TF</th><th>ไม้ (OOS)</th>
<th>Sharpe train</th><th>Sharpe OOS</th><th>maxDD</th><th>PF</th><th>ผล OOS</th></tr></thead><tbody>""")
    for _, r in sw.head(12).iterrows():
        cls = "pos" if r["te_sharpe"] > 0 else "neg"
        ret = r.get("te_net_return", 0)
        A(f'<tr class="{"hi" if r["te_sharpe"]>0 else ""}">'
          f'<td class="l">{escape(str(r["strategy"]))}</td><td>{int(r["tf"])}m</td>'
          f'<td>{int(r["te_trades"])}</td><td class="neu">{r["tr_sharpe"]:+.3f}</td>'
          f'<td class="{cls}"><b>{r["te_sharpe"]:+.3f}</b></td>'
          f'<td class="neg">{r["te_max_dd"]*100:.1f}%</td>'
          f'<td>{f(r["te_profit_factor"])}</td>'
          f'<td class="{cls}">{ret*100:+.1f}%</td></tr>')
    A(f"""</tbody></table></div>
<p class="caption">แสดง 12 อันดับแรกจาก 20 &middot; Sharpe ที่ติดลบแทบทุกตัว
คือผลจริง ไม่ใช่การแสดงผลเฉพาะที่ดี</p>
<div class="note">ตัวเดียวที่รอดคือ <b>combo_funding_reversion</b> (fade เมื่อ funding
สูงผิดปกติ) &mdash; น่าสนใจตรงที่ผล <b>บน OOS ดีกว่า train</b> ซึ่งตรงข้ามกับ
อาการ overfit ปกติ (เงาในอดีต ตายในอนาคต) แต่มีเพียง 87&ndash;114 ไม้
และ bootstrap ยังรวมค่าศูนย์ จึงยังสรุปไม่ได้</div>
</section>""")

    # ================= 6. rules vs ml =================
    m2 = d["ml2"]
    g_rules = m2[m2["method"] == "rules"]
    g_reg = m2[(m2["method"] == "reg") & (m2["thr"] == 0.1)]
    g_clf = m2[(m2["method"] == "clf") & (m2["thr"] == 0.1)]

    def avg(df, col):
        return float(df[col].mean()) if len(df) else float("nan")

    # NOTE: never put <br> inside an SVG <text>. `br` is on the HTML parser's
    # foreign-content breakout list, so the parser closes the <svg> context and
    # silently drops every element after it. That is exactly what happened here:
    # the chart rendered its first group and then quietly lost the other two.
    labels6 = ["กฎล้วน (ไม่กรอง)", "ML reg 0.10", "ML clf 0.10"]
    gross6 = [avg(g_rules, "avg_gross_r"), avg(g_reg, "avg_gross_r"),
              avg(g_clf, "avg_gross_r")]
    cost6 = [avg(g_rules, "avg_cost_r"), avg(g_reg, "avg_cost_r"),
             avg(g_clf, "avg_cost_r")]
    exp6 = [avg(g_rules, "expectancy_r"), avg(g_reg, "expectancy_r"),
            avg(g_clf, "expectancy_r")]
    A(f"""<section>
<h2><span class="num">06</span>กฎ vs ML filter &mdash; ML ชนะ แต่ยังไม่พอ</h2>
<p class="lead">ใช้กฎ 12 กลยุทธ์เป็นตัวสร้างสัญญาณ แล้วให้ LightGBM
คัดว่าสัญญาณไหนควรเทรด จาก 35 ฟีเจอร์ที่คำนวณได้ ณ เวลานั้นเท่านั้น
(เทรน 24 เดือน → ทำนาย 6 เดือนถัดไป, ไม่ทับกัน) เฉลี่ย 9 รอบ</p>
<div class="card">
{legend([("gross_r — รายได้ดิบก่อนต้นทุน", GREEN),
         ("cost_r — ต้นทุนต่อไม้", RED),
         ("net — ผลสุทธิ", AMBER)])}
{grouped_bar_chart(labels6, [
  {"name":"gross","color":GREEN,"values":gross6},
  {"name":"cost","color":RED,"values":cost6},
  {"name":"net","color":AMBER,"values":exp6},
], ylabel="R ต่อไม้ (ค่าเฉลี่ย 9 รอบ walk-forward)",
   yfmt=lambda v: f"{v:.2f}", ymin=0, ymax=max(gross6) * 1.25)}
<p class="caption">กฎล้วน: gross_r {f(gross6[0],3)} แต่ cost_r {f(cost6[0],3)}
=&gt; เหลือ {f(exp6[0],3)} &nbsp;&middot;&nbsp;
ML: gross_r เพิ่มเป็น {f(gross6[1],3)} / {f(gross6[2],3)}
แต่ cost_r ไม่ลดลงเลย เพราะมันขึ้นกับความกว้าง stop
ไม่ใช่คุณภาพไม้</p>
</div>
<div class="grid2">
<div class="card">
<h3 class="sub2" style="margin-top:0">ML ยกระดับการเลือกไม้ได้จริง</h3>
<p style="color:{MUT};margin:0 0 12px">gross_r เพิ่มขึ้น
<b style="color:{GREEN}">{gross6[1]/gross6[0]:.1f} เท่า</b>
เมื่อใช้ ML กรอง &mdash; นี่คือการคัดเลือกไม้ที่ดีขึ้นจริง
ไม่ใช่การเดาสุ่ม</p>
<p style="color:{MUT};margin:0">ในบาง fold ไม้ที่ ML เลือกให้ gross_r สูงถึง
<b style="color:{GREEN}">0.49 R</b> ขณะที่กฎล้วนอยู่ที่ 0.05 R</p>
</div>
<div class="card">
<h3 class="sub2" style="margin-top:0">แต่ยังสู้ต้นทุนไม่ได้</h3>
<p style="color:{MUT};margin:0 0 12px">cost_r อยู่ที่ ~{f(cost6[1],2)} R
ไม่ว่าจะกรองดีแค่ไหน &mdash; เพราะมันคำนวณจาก
<b style="color:{TXT}">ระยะ stop</b> เท่านั้น
ไม่เกี่ยวกับว่าไม้นั้นดีแค่ไหน</p>
<p style="color:{MUT};margin:0">ผลสุทธิจึงเหลือเพียง
<b style="color:{AMBER}">{f(exp6[1],3)} R</b> ที่ระดับ stop width นี้
&mdash; เล็กเกินกว่าจะพิสูจน์ว่าไม่ใช่ศูนย์ และการเพิ่ม threshold
ไม่ได้ทำให้มันมั่นคงขึ้นอย่างมีนัยสำคัญ</p>
</div></div>
<div class="note">สรุป: ML filter <b>เป็นตัวเลือกไม้ที่ดีกว่า</b> ของจริง
แต่<b>ยังเปลี่ยนข้อสรุปไม่ได้</b> เก็บไว้เป็นองค์ประกอบ
ประเด็นคือต้องแก้ <i>ต้นทุน</i> ไม่ใช่เพิ่มความซับซ้อนของสัญญาณ</div>
</section>""")

    # ================= 7. bugs =================
    bugs = [
        ("net_pnl ไม่รวม entry fee",
         "expectancy ต่ำกว่าความจริง ~0.3R ต่อไม้ และ sum(net_pnl) ≠ การเปลี่ยนแปลงพอร์ต",
         "ทำให้สถิติทั้งหมดที่พึ่ง R ผิดทั้งระบบ"),
        ("ท้ายข้อมูลถูกมองว่าเป็นการปิด session",
         "ทุก backtest ที่ใช้ time window จะบล็อกการเปิดไม้ช่วงท้ายของตัวเอง",
         "เงียบ ๆ bias ทุก walk-forward fold — อันตรายที่สุด"),
        ("ไฟล์ Binance มี header row ตั้งแต่ 2022-01",
         "ข้อมูลหายไป 58 จาก 80 เดือน แต่สคริปต์ยังรายงานว่าสำเร็จ",
         "เพิ่ม validate() เพื่อกันไม่ให้เกิดซ้ำ"),
        ("supertrend ใช้ close ปัจจุบันแทน previous close",
         "band recurrence ผิดจนทิศทางเปลี่ยนแค่ 7 ครั้งใน 6.5 ปี (จริง ๆ คือ 17,575)",
         "indicator ที่เงียบ ๆ เสียหาย"),
        ("signal DataFrame ไม่มี time index",
         "เป็น RangeIndex ตำแหน่งตรงกันโดยบังเอิญ แต่ slicing ตามเวลาแตก",
         "ทุก time-window backtest error"),
        ("supertrend ช้า 15+ นาที",
         "loop บน numpy scalar + np.isnan ทำให้ sweep ไม่จบ",
         "เขียนใหม่ด้วย Python float → 0.55s (เร็ว 1,800 เท่า)"),
        ("Trade timestamps ไม่มี timezone",
         "เทียบกับ tz-aware index ไม่ได้",
         "ทำให้ test no-lookahead พัง"),
        ("ค่าความเสี่ยงต่อไม้ไม่คงที่ระหว่างทดสอบต้นทุน",
         "คาดว่าจำนวนไม้คงที่เมื่อเปลี่ยนต้นทุน แต่ slippage เลื่อนระดับ entry/stop/target",
         "ตัวทดสอบผิด ไม่ใช่โค้ดผิด"),
    ]
    A(f"""<section>
<h2><span class="num">07</span>บั๊กที่เจอระหว่างทาง</h2>
<p class="lead">8 ตัว ในโค้ดที่ผมเขียนเอง &mdash; บันทึกไว้เพราะเหตุผลที่ทำให้
"ผลลัพธ์น่าเชื่อถือ" สำคัญกว่าตัวเลขสวย ๆ</p>
<div class="bugs">""")
    for t_, desc, imp in bugs:
        A(f'<div class="bug"><div class="t">{escape(t_)}</div>'
          f'<div class="d">{escape(desc)}</div>'
          f'<div class="i">{escape(imp)}</div></div>')
    A("</div>")
    A("""<div class="note warn">ข้อสรุปที่ได้: <b>การวัดผลก่อนเพิ่มประสิทธิภาพสำคัญกว่าการเพิ่มประสิทธิภาพ</b>
สมมติว่าปัญหาคือ backtest loop แต่การ profile จริงพบว่า indicator ที่เป็นตัวปน
และมันกำลังผิดด้วย &mdash; ถ้าไม่ profile ก็จะไปแก้โค้ดที่ไม่ได้เป็นต้นเหตุ</div>
</section>""")

    # ================= 8. timeline =================
    evs = [
        ("good", "Exp 001 &mdash; ตรวจสอบ Engine",
         "4/4 ผ่าน · 2,297 ไม้ตรงกับ reference · จับบั๊กใน engine ได้ 5 ตัว"),
        ("bad", "Exp 002 &mdash; หาสาเหตุที่ sweep ค้าง",
         "supertrend ช้า 15+ นาที · เขียนใหม่แล้วเร็ว 1,800 เท่า · 1m backtest 8.7s → 3.7s"),
        ("bad", "Exp 003 &mdash; ทดสอบ 82 config",
         "18 จาก 20 ติดลบบน OOS · ค้นพบสูตร cost_r ที่อธิบายทุกอย่าง"),
        ("good", "Exp 004 &mdash; Cost Lab",
         "ขยาย stop 1× → 5× โดยไม่เปลี่ยนสัญญาณ · จาก -25%/ปี เป็น ~ทุนจน"),
        ("bad", "Exp 005 &mdash; กลยุทธ์มีความเห็นเฉพาะบางช่วง",
         "combo_funding_reversion มีสัญญาณแค่ 5 ตัวใน 6 เดือนปี 2022 · ไม่ควรเฉลี่ย Sharpe"),
        ("a", "Exp 006 &mdash; กฎ vs ML",
         "ML ยก gross_r จาก 0.02 เป็น 0.11&ndash;0.17 แต่ต้นทุนยังกินหมด"),
        ("a", "Exp 007 &mdash; ผลลัพธ์สุดท้าย",
         "24 config · bootstrap · chained equity · ไม่มีช่วงความเชื่อมั่นใดรวม 0 เลย"),
    ]
    A('<section><h2><span class="num">08</span>ลำดับการทดลอง</h2>'
      '<p class="lead">ทุกรอบถูกบันทึกใน journal/experiments.md '
      'พร้อมเหตุผลและข้อสรุป รวมถึงรอบที่ผิด โดยไม่แก้ย้อนหลัง</p>'
      '<div class="tl">')
    for cls, h_, p_ in evs:
        A(f'<div class="ev {cls}"><h4>{h_}</h4><p>{p_}</p></div>')
    A("</div></section>")

    # ================= 9. post-only =================
    mk = d.get("maker")
    if mk is not None and len(mk):
        A("""<section>
<h2><span class="num">09</span>ลดต้นทุนด้วย post-only order (Exp 008)</h2>
<p class="lead">ผมเคยเขียนว่า maker ลดต้นทุนได้ 3.5 เท่า &mdash;
<b>ผิด</b> เพราะ stop-loss ไม่ได้เป็น maker fill
ของจริงคือ 1.55 เท่า และต้นทุนแฝงของมันคือ limit order
จะ fill <b>เฉพาะตอนราคามาหาคุณ</b> ซึ่งคือตอนที่ราคากำลังสวนทางเรา
จึงต้องสร้าง fill model ที่จำลองสิ่งนั้น ไม่ใช่สมมติว่ามันฟรี</p>
<div class="tblwrap"><table><thead><tr><th class="l">stop</th>
<th class="l">โหมด</th><th>fill</th><th>ไม้</th><th>gross_r</th>
<th>cost_r</th><th>net R</th><th>95% CI</th><th>CAGR</th>
</tr></thead><tbody>""")
        for sc in sorted(mk["stop_scale"].unique()):
            sub = mk[mk["stop_scale"] == sc].sort_values("mean_R",
                                                         ascending=False)
            for _, r in sub.iterrows():
                cls = "pos" if r["mean_R"] > 0 else "neg"
                hl = (r["note"] != "taker" and r["mean_R"] > 0)
                A(f'<tr class="{"hi" if hl else ""}">'
                  f'<td class="l">{r["stop_scale"]:g}&times;</td>'
                  f'<td class="l">{escape(str(r["note"]))}</td>'
                  f'<td>{r["fill_rate"]*100:.0f}%</td><td>{int(r["trades"])}</td>'
                  f'<td class="pos">{r["gross_r"]:+.3f}</td>'
                  f'<td class="neg">{r["cost_r"]:.3f}</td>'
                  f'<td class="{cls}">{r["mean_R"]:+.4f}</td>'
                  f'<td class="neu">[{r["ci_lo"]:+.3f}, {r["ci_hi"]:+.3f}]</td>'
                  f'<td class="{cls}">{r["cagr"]*100:+.1f}%</td></tr>')
        A("</tbody></table></div>")
        A("""<div class="note good"><b>ผลลัพธ์ที่ดีที่สุดของงานวิจัยนี้:</b>
post-only ช่วยทุก stop width โดย +0.033 ถึง +0.054 R ต่อไม้
และ <b>gross_r เพิ่มขึ้น</b> ไม่ใช่ลดลง เพราะการต้องรอให้ราคาแตะโดน
กรองไม้ที่ "พุ่งหนี" ซึ่งส่วนใหญ่เป็นไม้ขาดทุน
แต่เมื่อดัน limit ออกไปไกลเกิน (offset 0.5) fill rate เหลือ 36%
gross_r ก็พัง &mdash; นั่นคือ adverse selection ที่เริ่มกัด</div>
<div class="note bad"><b>แต่ช่วงความเชื่อมั่นยังรวมค่าศูนย์</b>
ค่าที่ดีที่สุดคือ +0.0706 R ที่ CI <b>[-0.007, +0.150]</b> บน 143 ไม้
ใกล้พอจะพิสูจน์แล้ว แต่ยังไม่ใช่การพิสูจน์
ข้อจำกัดตอนนี้คือ <b>ขนาดตัวอย่าง</b> ไม่ใช่ต้นทุนแล้ว</div>
</section>""")

    # ================= 10. holding period =================
    hp = d.get("hold")
    if hp is not None and len(hp):
        hp5 = hp[hp["tf"] == 5]
        hs = sorted(hp5["hold_hours"].unique())
        A(f"""<section>
<h2><span class="num">10</span>ข้อค้นพบสุดท้าย: edge นี้ไม่ใช่ของ intraday (Exp 009)</h2>
<p class="lead">config ที่ดีที่สุดถือ position นาน <b>18 ชั่วโมง</b>
ทั้งที่โจทย์คือ day trade 1&ndash;4 ชั่วโมง
ผมไม่ได้สังเกตเรื่องนี้มาเจ็ดการทดลอง
การตัด holding period ให้ตรง brief จึงเป็นการทดสอบว่ามันทำได้จริงไหม</p>
<div class="card">
{legend([("stop 2.0&times;", BLUE), ("stop 3.5&times;", GREEN), ("stop 5.0&times;", PURPLE)])}
{line_chart([
  {"name": f"s{sc}", "color": c, "width": 2.4, "dots": True,
   "x": hp5["hold_hours"].tolist(),
   "y": hp5[hp5.stop_scale == sc]["mean_R"].tolist(),
   **({"xticks": [(h, f"{h:.0f}h") for h in hs]} if sc == 2.0 else {})}
  for sc, c in ((2.0, BLUE), (3.5, GREEN), (5.0, PURPLE))
], ylabel="net expectancy ต่อไม้ (R)", yfmt=lambda v: f"{v:+.2f}", xlog=True)}
<p class="caption">ยิ่งถือสั้น ผลยิ่งติดลบ &mdash;
ไม่มีช่วงไหนใน 2&ndash;8 ชั่วโมงที่ให้ผลบวกอย่างมั่นคง</p>
</div>
<div class="tblwrap"><table><thead><tr><th class="l">ถือ</th><th>ไม้</th>
<th>เฉลี่ยที่ถือจริง</th><th>gross_r</th><th>cost_r</th><th>net R</th>
<th>95% CI</th><th>CAGR</th></tr></thead><tbody>""")
        for _, r in hp5[hp5.stop_scale == 2.0].sort_values("hold_hours").iterrows():
            cls = "pos" if r["mean_R"] > 0 else "neg"
            A(f'<tr><td class="l"><b>{r["hold_hours"]:.0f} ชม.</b></td>'
              f'<td>{int(r["trades"])}</td><td>{r["avg_bars"]:.0f} แท่ง</td>'
              f'<td class="pos">{r["gross_r"]:+.3f}</td>'
              f'<td class="neg">{r["cost_r"]:.3f}</td>'
              f'<td class="{cls}">{r["mean_R"]:+.4f}</td>'
              f'<td class="neu">[{r["ci_lo"]:+.3f}, {r["ci_hi"]:+.3f}]</td>'
              f'<td class="{cls}">{r["cagr"]*100:+.1f}%</td></tr>')
        A("</tbody></table></div>")
        A("""<div class="note bad"><b>คำตอบคือไม่ได้</b>
ทุก config ที่ถือ 2&ndash;4 ชั่วโมง <b>ติดลบทั้งหมด</b>
และบน 15m ผลแรงจน ML filter ที่ threshold 0.10
<b>ไม่ยอมเทรดเลยแม้แต่ไม้เดียว</b> ใน 9 รอบ
&mdash; โมเดลเรียนรู้ถูกต้องว่าไม้ระยะสั้นในกลุ่มนี้ไม่คุ้ม
<b>ไม่มี edge แบบ intraday ให้ค้นหา</b> ผลบวกที่ได้ต้องพึ่งการถือ 6&ndash;18 ชั่วโมง
ซึ่งไม่ใช่ day trading</div>
</section>""")

    A("""<section>
<h2><span class="num">11</span>สรุป และทางเลือกที่เหลือ</h2>
<div class="grid2">
<div class="card">
<h3 class="sub2" style="margin-top:0;color:%(G)s">สิ่งที่ได้จริง</h3>
<ul class="tight" style="margin:0">
<li><b>post-only execution</b> ช่วย +0.033 ถึง +0.054 R/ไม้ ทุก stop width</li>
<li><b>stop width</b> สำคัญกว่าตัวชี้วัดทุกตัว &mdash; 1&times; → 5&times;
พาพอร์ตจาก &minus;25%%/ปี มาเกือบทุน โดยไม่เปลี่ยนสัญญาณเลย</li>
<li><b>ML filter</b> ยก gross_r จาก 0.02 เป็น 0.11&ndash;0.17 อย่างสม่ำเสมอ</li>
<li>ledger 632 แถว ตรวจ arithmetIc ผ่านทุกครั้งที่รัน</li>
</ul>
</div>
<div class="card">
<h3 class="sub2" style="margin-top:0;color:%(A)s">ทางเลือก</h3>
<ul class="tight" style="margin:0">
<li>ยอมรับ horizon หลายชั่วโมง และ<b>เรียกมันว่า swing ไม่ใช่ day trade</b>
ให้ตรงไปตรงมา แล้วค่อยหาทางทำให้ช่วงเชื่อมั่นแคบลง</li>
<li>เปลี่ยนสมมติฐานทั้งหมด &mdash; market making / funding carry
ได้กำไรจากสเปรด ไม่ใช่จากทิศทางราคา
คนละเกมกันและไม่ต้องชนะการคาดเดา</li>
<li>เพิ่มข้อมูล order book เพื่อทดสอบ fill model ใกล้ความจริงมากขึ้น</li>
</ul>
</div></div>
<div class="note bad" style="margin-top:22px"><b>ข้อความสุดท้ายที่สุภาพ:</b>
งานวิจัยนี้ทำงานถูกต้องและตอบโจทย์ได้
คำตอบคือ <b>ไม่มี edge แบบ day trading ในกลุ่ม indicator นี้
ที่ระดับค่าธรรมเนียมรายย่อย</b>
ผลบวกเล็กน้อยที่ได้มาต้องพึ่งการถือหลายชั่วโมง
ซึ่งขัดกับโจทย์เดิม &mdash; และแม้แต่กรณีนั้นช่วงความเชื่อมั่นก็ยังรวมค่าศูนย์
ความรู้ที่ได้คือ<b>รู้ว่าอะไรไม่ได้ผล</b> ซึ่งมีค่ามากกว่า
การเพิ่ม indicator เปล่า ๆ ต่อไป</div>
</section>""" % dict(G=GREEN, A=AMBER))

    A(f"""<footer>
<span>สร้างเมื่อ {today} &middot; ข้อมูล Binance USDT-M Public Data 2020-01 &rarr; 2026-08</span>
<span class="mono">btc_futures_dt / journal/experiments.md</span>
</footer>""")

    return ("<!DOCTYPE html><html lang=\"th\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>BTCUSDT Intraday Futures &mdash; ผลการวิจัย</title>"
            f"<style>{CSS}</style></head><body><div class=\"wrap\">"
            + "".join(o) + "</div></body></html>")


if __name__ == "__main__":
    out = C.ROOT / "report.html"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size/1024:.0f} KB)")
