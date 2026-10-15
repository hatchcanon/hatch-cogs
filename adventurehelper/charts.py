"""Matplotlib chart rendering for adventure stats.

Everything here is synchronous and CPU-bound; call it through run_in_executor.
"""
import io
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

# Styled for Discord's dark theme. Series colors are a fixed categorical order,
# validated for CVD separation against the surface below.
SURFACE = "#313338"
TEXT_PRIMARY = "#f2f3f5"
TEXT_SECONDARY = "#b5bac1"
GRID = "#404249"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
MAX_SERIES = len(SERIES)

# (label, [(ts, value), ...]) for one line.
Series = Tuple[str, List[Tuple[float, int]]]


def _short_number(value: float, _pos=None) -> str:
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= size:
            return f"{value / size:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,.0f}"


def _to_dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _extend_to_now(points: List[Tuple[float, int]], now: float) -> Tuple[list, list]:
    """Split points into x/y lists, carrying the last value forward to now."""
    xs = [_to_dt(ts) for ts, _ in points]
    ys = [v for _, v in points]
    if points[-1][0] < now:
        xs.append(_to_dt(now))
        ys.append(ys[-1])
    return xs, ys


def _new_figure(title: str, subtitle: str, ylabel: str):
    fig, ax = plt.subplots(figsize=(10, 5), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0, pad=6)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY, fontsize=9)

    fig.text(0.06, 0.94, title, color=TEXT_PRIMARY, fontsize=15, fontweight="bold", ha="left")
    fig.text(0.06, 0.895, f"{subtitle} · UTC", color=TEXT_SECONDARY, fontsize=10, ha="left")

    locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=timezone.utc))
    return fig, ax


def _finish(fig, ax, start: Optional[float], now: float, right_pad: float = 0.0, top: float = 0.84) -> io.BytesIO:
    if start is not None:
        span = now - start
        ax.set_xlim(_to_dt(start), _to_dt(now + span * right_pad))
    fig.subplots_adjust(left=0.06, right=0.97, top=top, bottom=0.12)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    buf.seek(0)
    return buf


def _signed(value: int) -> str:
    return ("+" if value > 0 else "") + _short_number(value)


def gold_chart(name: str, period_label: str, points, start: Optional[float], now: float) -> io.BytesIO:
    xs, ys = _extend_to_now(points, now)
    net = ys[-1] - ys[0]
    fig, ax = _new_figure(
        f"{name} · Gold",
        f"{period_label} · now {_short_number(ys[-1])} · net {_signed(net)}",
        "Gold",
    )
    color = SERIES[0]
    ax.step(xs, ys, where="post", color=color, linewidth=2)
    ax.fill_between(xs, ys, step="post", color=color, alpha=0.15, linewidth=0)
    ax.yaxis.set_major_formatter(FuncFormatter(_short_number))
    ax.set_ylim(bottom=0)

    # Label the peak only; a number on every step would be noise.
    peak = max(range(len(ys)), key=ys.__getitem__)
    if len(set(ys)) > 1:
        ax.plot([xs[peak]], [ys[peak]], "o", color=color, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.annotate(
            f"peak {_short_number(ys[peak])}",
            (xs[peak], ys[peak]),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            color=TEXT_PRIMARY,
            fontsize=9,
        )
    return _finish(fig, ax, start if start is not None else points[0][0], now)


def level_chart(name: str, period_label: str, points, start: Optional[float], now: float) -> io.BytesIO:
    """points are (ts, lvl, rebirths)."""
    xs, ys = _extend_to_now([(ts, lvl) for ts, lvl, _ in points], now)
    rebirths_now = points[-1][2]
    fig, ax = _new_figure(
        f"{name} · Level",
        f"{period_label} · level {ys[-1]} · rebirth {rebirths_now}",
        "Level",
    )
    ax.step(xs, ys, where="post", color=SERIES[0], linewidth=2)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylim(bottom=0)

    # Rebirths reset level to 1; mark each so the drop reads as progress, not loss.
    for (_, _, prev_rb), (ts, _, rb) in zip(points, points[1:]):
        if rb > prev_rb:
            x = _to_dt(ts)
            ax.axvline(x, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)))
            ax.annotate(
                f"rebirth {rb}",
                (x, 1),
                xycoords=("data", "axes fraction"),
                xytext=(4, -4),
                textcoords="offset points",
                va="top",
                color=TEXT_SECONDARY,
                fontsize=8,
            )
    return _finish(fig, ax, start if start is not None else points[0][0], now)


def rebirth_chart(name: str, period_label: str, points, start: Optional[float], now: float) -> io.BytesIO:
    """points are (ts, lvl, rebirths)."""
    xs, ys = _extend_to_now([(ts, rb) for ts, _, rb in points], now)
    gained = ys[-1] - ys[0]
    fig, ax = _new_figure(
        f"{name} · Rebirths",
        f"{period_label} · rebirth {ys[-1]} · gained {_signed(gained)}",
        "Rebirths",
    )
    color = SERIES[0]
    ax.step(xs, ys, where="post", color=color, linewidth=2)
    ax.fill_between(xs, ys, step="post", color=color, alpha=0.15, linewidth=0)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylim(bottom=0, top=max(ys) + 1)

    # Dot each rebirth so individual steps stay visible on long periods.
    for (_, _, prev_rb), (ts, _, rb) in zip(points, points[1:]):
        if rb > prev_rb:
            ax.plot([_to_dt(ts)], [rb], "o", color=color, markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5)
    return _finish(fig, ax, start if start is not None else points[0][0], now)


def compare_chart(
    metric: str, period_label: str, series: Sequence[Series], start: Optional[float], now: float
) -> io.BytesIO:
    fig, ax = _new_figure(f"{metric} comparison", f"{period_label} · {len(series)} players", metric)
    direct_labels = len(series) <= 4
    for (label, points), color in zip(series, SERIES):
        xs, ys = _extend_to_now(points, now)
        ax.step(xs, ys, where="post", color=color, linewidth=2, label=label)
        if direct_labels:
            ax.annotate(
                label,
                (xs[-1], ys[-1]),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                color=TEXT_PRIMARY,
                fontsize=9,
            )
    if metric == "Gold":
        ax.yaxis.set_major_formatter(FuncFormatter(_short_number))
    else:
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylim(bottom=0)

    legend = ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.0),
        ncol=min(len(series), 4),
        frameon=False,
        fontsize=9,
        labelcolor=TEXT_PRIMARY,
        handlelength=1.5,
    )
    for line in legend.get_lines():
        line.set_linewidth(3)

    if start is None:
        start = min(points[0][0] for _, points in series)
    # Leave room on the right for the end-of-line name labels.
    return _finish(fig, ax, start, now, right_pad=0.12 if direct_labels else 0.0, top=0.79)
