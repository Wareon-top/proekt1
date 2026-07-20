"""Фирменная графика бренда Wareon (баннер-шапка меню) — чёрный/золото."""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

BG = "#0f0f12"
GOLD = "#d9b45b"
GOLD2 = "#f0d488"
TXT = "#f4f2ec"
DIM = "#9b9aa4"

_cache: bytes | None = None


def _bold(size: int):
    return font_manager.FontProperties(weight="bold", size=size)


def menu_banner_png() -> bytes:
    """Баннер-шапка для меню бота. Рендерится один раз и кэшируется."""
    global _cache
    if _cache is not None:
        return _cache

    fig = plt.figure(figsize=(9, 3.2), dpi=170)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.axis("off")

    # Вордмарк: WAR e ON — акцентная «e» золотом.
    ax.text(0.5, 0.60, "WAR", ha="right", va="center", color=TXT, fontproperties=_bold(58))
    ax.text(0.5, 0.60, "e", ha="center", va="center", color=GOLD, fontproperties=_bold(58))
    ax.text(0.5, 0.60, "  ON", ha="left", va="center", color=TXT, fontproperties=_bold(58))

    ax.text(0.5, 0.30, "И И   Б И З Н Е С - А С С И С Т Е Н Т", ha="center", va="center",
            color=DIM, fontproperties=_bold(15))
    ax.text(0.5, 0.16, "видит  ·  думает  ·  делает", ha="center", va="center",
            color=GOLD2, fontproperties=font_manager.FontProperties(size=13, style="italic"))

    # Тонкая золотая линия-акцент.
    ax.plot([0.36, 0.64], [0.42, 0.42], color=GOLD, linewidth=1.2, alpha=0.7)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    _cache = buf.getvalue()
    return _cache
