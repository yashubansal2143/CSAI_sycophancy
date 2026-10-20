"""Column-width figures for the ICASSP-format paper. Run from the repo root: python3 src/make_icassp_figures.py"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "paper"
OUT.mkdir(exist_ok=True)
C_CORRECT, C_WRONG, C_GREY, C_INK = "#1f5fbf", "#c8571f", "#8f98a8", "#1b2230"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"], "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6, "legend.fontsize": 8, "pdf.fonttype": 42})
W = 3.39   # one ICASSP column in inches
L = np.arange(1, 27)

# Fig. 1: what Gemma says (decision point) vs what it knows (fact probe), mean over conversations
h = json.load(open(ROOT / "results/phase2b/phase2b_H_figure_data.json"))
fig, ax = plt.subplots(figsize=(W, 2.15))
for t in [t for t in h["H1"]["data"] if t.get("name")]:
    y = np.asarray(t["y"], float)
    if "fact slot" in t["name"]:
        ax.plot(L, y, color=C_WRONG, ls="--", lw=1.3, label="same 141 conversations: fact probe (knows)")
    elif "user's" in t["name"]:
        ax.plot(L, y, color=C_WRONG, lw=1.5, label="named user's answer: decision point (says), $n$=141")
    else:
        ax.plot(L, y, color=C_CORRECT, lw=1.5, label="named correct answer: decision point, $n$=146")
ax.axhline(0, color=C_GREY, lw=0.6)
ax.axvspan(15.5, 18.5, color=C_GREY, alpha=0.18, lw=0)
ax.set_xlim(1, 26)
ax.set_xticks([1, 5, 10, 15, 20, 26])
ax.set_ylim(-25, 13)
ax.set_xlabel("Layer")
ax.set_ylabel(r"Mean lean $\Delta_\ell$")
ax.legend(frameon=False, loc="lower left", handlelength=1.8, borderaxespad=0.2)
fig.tight_layout(pad=0.2)
fig.savefig(OUT / "fig_knows_says.pdf")
plt.close(fig)

# Fig. 2: steering by layer (Phase 3a-2)
sw = pd.read_csv(ROOT / "results/phase3/phase3_sweep.csv")
fig, ax = plt.subplots(figsize=(W, 2.0))
for s, ls, mk in [(1, ":", "o"), (2, "-", "o"), (3, "--", "s")]:
    q = sw[(sw.kind == "direction") & (sw.strength == s)]
    ax.plot(q.layer, 100 * q.says_user, ls=ls, marker=mk, ms=2.8, lw=1.2, color=C_CORRECT, label=fr"steering $\alpha$=+{s}")
r = sw[sw.kind == "random"].groupby("layer").says_user.agg(["min", "max", "mean"]).reset_index()
ax.fill_between(r.layer, 100 * r["min"], 100 * r["max"], color=C_GREY, alpha=0.35, lw=0, label=r"random direction, $\alpha$=+2 (range)")
ax.axhline(57.5, color=C_INK, ls="-.", lw=0.8, label="no steering (57.5%)")
ax.set_xticks(sorted(sw.layer.unique()))
ax.set_ylim(-3, 112)
ax.set_yticks([0, 20, 40, 60, 80])
ax.set_xlabel("Steered layer")
ax.set_ylabel("Caving rate (%)")
ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.02), columnspacing=1.0, handlelength=1.8)
fig.tight_layout(pad=0.2)
fig.savefig(OUT / "fig_sweep.pdf")
plt.close(fig)
print("wrote", OUT / "fig_knows_says.pdf", OUT / "fig_sweep.pdf")
