"""Shared figure style. Categorical colours in fixed order (validated
palette, dataviz reference); flow modes always keep the same colour and
marker so they read without colour too."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, MUTED, GRID = "#1f1f1e", "#6b6b66", "#e4e3de"
MODE_STYLE = {"MaB": (SERIES[0], "o", "Marangoni + buoyancy"),
              "B": (SERIES[1], "s", "buoyancy only"),
              "none": (SERIES[2], "^", "conduction only")}

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 200, "savefig.bbox": "tight",
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "lines.linewidth": 2, "lines.markersize": 6,
})
