"""Фирменные графики Wareon (чёрный/золото) для премиальной подачи в боте."""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

BG = "#0f0f12"
GOLD = "#d9b45b"
GOLD2 = "#f0d488"
GREEN = "#4fbf7a"
GRID = "#26262e"
TXT = "#f4f2ec"
DIM = "#9b9aa4"


def _thousands(v: float, _pos=None) -> str:
    v = int(round(v))
    if abs(v) >= 1000:
        return f"{v / 1000:g}к"
    return str(v)


def pulse_chart_png(series: list[float], days: int, title: str = "Выручка по дням") -> bytes | None:
    """Столбчатый график выручки по дням в фирменной палитре. None — если мало точек."""
    if not series or len(series) < 2:
        return None

    n = len(series)
    fig, ax = plt.subplots(figsize=(8, 3.4), dpi=170)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    colors = [GOLD] * (n - 1) + [GREEN]
    ax.bar(range(n), series, color=colors, width=0.72, zorder=3)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=DIM, labelsize=9, length=0)
    ax.set_xticks([0, n - 1])
    ax.set_xticklabels([f"{days} дн назад", "сегодня"])
    ax.grid(axis="y", color=GRID, alpha=0.7, linewidth=0.8, zorder=0)
    ax.yaxis.set_major_formatter(FuncFormatter(_thousands))
    ax.margins(x=0.01)
    ax.set_title(title, color=TXT, fontsize=13, fontweight="bold", loc="left", pad=12)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
