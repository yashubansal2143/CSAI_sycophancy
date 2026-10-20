"""Paper figures from saved results (no GPU). Run from the repo root: python3 src/make_paper_figures.py"""
import base64
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import scoring  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "figures" / "summary"
OUT.mkdir(parents=True, exist_ok=True)

C_CORRECT, C_WRONG, C_GREY, C_INK = "#2a6fc9", "#c8571f", "#9aa3b2", "#1b2230"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 11, "axes.titleweight": "bold", "figure.dpi": 150})


def arr(v):
    if isinstance(v, dict) and "bdata" in v:
        return np.frombuffer(base64.b64decode(v["bdata"]), dtype=np.dtype(v["dtype"])).astype(float)
    return np.asarray(v, dtype=float)


def plotly_traces(html_path):
    s = Path(html_path).read_text()
    i = s.find("Plotly.newPlot(")
    j = s.find("[", i)
    data, _ = json.JSONDecoder().raw_decode(s[j:])
    return data


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


# Fig 1: behaviour (Phase 1b, scorer v2.1)
pq = list(csv.DictReader(open(ROOT / "results/phase1b/phase1b_v2_per_question.csv")))
conds = [("correct_push", "Correct answer\npushed"), ("doubt_only", "'Are you sure?'\nonly"),
         ("wrong_novice", "Wrong +\n'student'"), ("wrong_plain", "Wrong\nanswer"), ("wrong_expert", "Wrong +\n'professor'")]
fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1.5, 1]})
for i, (c, lab) in enumerate(conds):
    rows = [r for r in pq if r["condition"] == c]
    k = sum(r["abandoned"] == "True" for r in rows)
    n = len(rows)
    lo, hi = wilson(k, n)
    col = C_WRONG if c.startswith("wrong") else C_GREY
    a.bar(i, k / n, color=col)
    a.errorbar(i, k / n, yerr=[[k / n - lo], [hi - k / n]], color=C_INK, capsize=3, lw=1)
    a.text(i, hi + 0.03, f"{k / n:.0%}", ha="center", fontsize=9)
a.set_xticks(range(len(conds)), [l for _, l in conds], fontsize=8)
a.set_ylim(0, 1.08)
a.set_ylabel("Abandoned the correct answer\n(within 3 pushbacks)")
a.set_title("A. Caving depends on the user naming an answer")
for c, lab, col in [("wrong_expert", "professor", C_WRONG), ("wrong_plain", "plain", "#e39a6e"), ("wrong_novice", "student", "#f0c7ad")]:
    rows = [r for r in pq if r["condition"] == c]
    n = len(rows)
    cum = [sum(1 for r in rows if r["first_wrong_turn"] and int(float(r["first_wrong_turn"])) <= t) / n for t in (1, 2, 3)]
    b.plot([1, 2, 3], cum, marker="o", color=col, label=lab, lw=2)
b.set_xticks([1, 2, 3])
b.set_xlabel("Pushback turn")
b.set_ylabel("Adopted the user's answer (cumulative)")
b.set_ylim(0, 1)
b.legend(frameon=False, title="Wrong answer +", fontsize=8.5, title_fontsize=8.5)
b.set_title("B. Claimed expertise speeds caving")
save(fig, "fig1_behaviour")

# Fig 2: confidence and flip timing (wrong_plain)
rows = [r for r in pq if r["condition"] == "wrong_plain"]
groups = [("1", "turn 1"), ("2", "turn 2"), ("3", "turn 3"), ("", "never")]
fig, ax = plt.subplots(figsize=(5, 3.2))
data = []
for g, _ in groups:
    vals = [float(r["margin"]) for r in rows if (r["first_wrong_turn"] and str(int(float(r["first_wrong_turn"]))) == g) or (g == "" and not r["first_wrong_turn"])]
    data.append(vals)
bp = ax.boxplot(data, widths=0.5, patch_artist=True, showfliers=False)
for patch, col in zip(bp["boxes"], [C_WRONG, "#e39a6e", "#f0c7ad", C_CORRECT]):
    patch.set_facecolor(col)
    patch.set_alpha(0.7)
for i, vals in enumerate(data):
    ax.scatter(np.random.default_rng(i).normal(i + 1, 0.06, len(vals)), vals, s=6, color=C_INK, alpha=0.35, zorder=3)
    ax.text(i + 1, 25, f"n={len(vals)}\nmedian {np.median(vals):.1f}", ha="center", va="top", fontsize=7.5)
ax.set_xticks(range(1, 5), [l for _, l in groups])
ax.set_ylim(0, 26)
ax.set_xlabel("Turn at which Gemma first adopted the wrong answer")
ax.set_ylabel("Neutral confidence margin\nlog P(correct) - log P(wrong)")
ax.set_title("Less confident answers cave sooner")
save(fig, "fig2_confidence")

# Fig 3: knows vs says by condition (Phase 2, 60 facts, first reply)
items = list(csv.DictReader(open(ROOT / "results/phase2/phase2_items.csv")))
order = [("neutral", "Neutral"), ("doubt_only", "'Are you\nsure?'"), ("correct_push", "Correct\npushed"),
         ("wrong_novice", "Wrong +\nstudent"), ("wrong_plain", "Wrong"), ("wrong_expert", "Wrong +\nprofessor")]
knows, says = [], []
for c, _ in order:
    r = [x for x in items if x["condition"] == c]
    knows.append(np.mean([float(x["final_diff"]) > 0 for x in r]))
    says.append(np.mean([scoring.label(x["actual_reply"], "fact", [x["correct"]], [x["wrong"]]) == "WRONG" for x in r]))
fig, ax = plt.subplots(figsize=(7, 3.2))
x = np.arange(len(order))
ax.bar(x - 0.2, knows, 0.4, color=C_CORRECT, label="Fact probe prefers the correct answer (knows)")
ax.bar(x + 0.2, says, 0.4, color=C_WRONG, label="Reply states the user's / lure answer (says)")
for i in range(len(order)):
    ax.text(i - 0.2, knows[i] + 0.02, f"{knows[i]:.0%}", ha="center", fontsize=8)
    ax.text(i + 0.2, says[i] + 0.02, f"{says[i]:.0%}", ha="center", fontsize=8)
ax.set_xticks(x, [l for _, l in order], fontsize=8.5)
ax.set_ylim(0, 1.15)
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_title("Pressure changes what Gemma says, not what it knows (60 facts)")
save(fig, "fig3_knows_vs_says")

# Fig 4: Egypt decision point vs fact slot, and patching
c_tr = plotly_traces(ROOT / "figures/phase2b/phase2b_C_decision_point.html")
e_tr = plotly_traces(ROOT / "figures/phase2b/phase2b_E_patching.html")
L = np.arange(1, 27)
fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.3))
for t in c_tr:
    y = arr(t["y"])
    says_line = "SAYS" in (t.get("name") or "")
    a.plot(L[: len(y)], y, color=C_WRONG if says_line else C_CORRECT, lw=2, ls="-" if says_line else "--",
           label="Decision point (what it says)" if says_line else "Fact probe (what it knows)")
a.axhline(0, color=C_GREY, lw=1)
a.set_xlabel("Layer")
a.set_ylabel("Lean: Cairo (+) vs Alexandria (-)")
a.legend(frameon=False, fontsize=8)
a.set_title("A. Same conversation, opposite answers")
y = arr(e_tr[0]["y"])
b.plot(L[: len(y)], y, color=C_INK, marker="o", ms=3, lw=1.8)
b.axhline(y[0], color=C_WRONG, ls=":", lw=1.2)
b.axhline(y[-1], color=C_CORRECT, ls=":", lw=1.2)
b.text(1, y[0] + 0.25, "pressured (wrong answer named)", color=C_WRONG, fontsize=8)
b.text(1, y[-1] - 0.6, "calm ('Are you sure?' only)", color=C_CORRECT, fontsize=8)
b.axvspan(14.5, 16.5, color=C_GREY, alpha=0.2)
b.set_xlabel("Layer whose last-token state is transplanted")
b.set_ylabel("Final lean")
b.set_title("B. The user's answer arrives at layers 15-16")
save(fig, "fig4_egypt_case")

# Fig 5 and 6: batch decision points (H1, H2)
h = json.load(open(ROOT / "results/phase2b/phase2b_H_figure_data.json"))
named = [t for t in h["H1"]["data"] if t.get("name")]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
for t in named:
    y = arr(t["y"])
    nm = t["name"]
    if "fact slot" in nm:
        ax.plot(L, y, color=C_WRONG, ls="--", lw=2, label="Same caving conversations: fact probe (n=141)")
    elif "user's" in nm:
        ax.plot(L, y, color=C_WRONG, lw=2.2, label="Named the user's answer: decision point (n=141)")
    else:
        ax.plot(L, y, color=C_CORRECT, lw=2.2, label="Named the correct answer: decision point (n=146)")
ax.axhline(0, color=C_GREY, lw=1)
ax.axvspan(15.5, 18.5, color=C_GREY, alpha=0.18)
ax.set_xlabel("Layer")
ax.set_ylabel("Mean lean: correct (+) vs user's (-)")
ax.legend(frameon=False, fontsize=7.5, loc="lower left")
ax.set_title("Decision point splits at layers 16-18; knowledge stays correct")
save(fig, "fig5_decision_vs_fact")

fig, ax = plt.subplots(figsize=(5.6, 4.2))
cols = {"Wrong answer": "#2a6fc9", "Wrong + 'professor'": C_WRONG, "Wrong + 'student'": "#1baf7a",
        "'Are you sure?' only": "#d9a400", "Correct answer pushed": "#c76aa0"}
for t in h["H2"]["data"]:
    ax.scatter(arr(t["x"]), arr(t["y"]), s=14, alpha=0.75, color=cols.get(t["name"], C_GREY), label=t["name"], edgecolor="none")
ax.axhline(0, color=C_GREY, lw=1)
ax.axvline(0, color=C_GREY, lw=1)
ax.text(-14.5, 14.5, "knows the truth,\nsays the user's answer", color=C_WRONG, fontsize=8.5, va="top", fontweight="bold")
ax.text(-14.5, -7.8, "persuaded / unsure", color=C_INK, fontsize=8, va="bottom")
ax.set_xlabel("What it SAYS: decision-point lean (- = user's answer)")
ax.set_ylabel("What it KNOWS: fact-probe lean (+ = correct)")
ax.legend(frameon=False, fontsize=7, loc="lower right")
ax.set_title("Every conversation: knowing vs saying (n=287)")
save(fig, "fig6_knows_vs_says_scatter")

# Fig 7: steering
labels = ["Direction -2", "Random -2", "No steering", "Random +2\n(6 seeds)", "Direction +2"]
vals = [0.80, 0.68, 0.57, np.mean([0.32, 0.42, 0.40, 0.55, 0.40, 0.57]), 0.05]
colors = [C_WRONG, C_GREY, C_INK, C_GREY, C_CORRECT]
fig, ax = plt.subplots(figsize=(6.4, 3.2))
ax.barh(range(5), vals, color=colors, alpha=0.9)
ax.errorbar(vals[3], 3, xerr=[[vals[3] - 0.32], [0.57 - vals[3]]], color=C_INK, capsize=3, lw=1)
for i, v in enumerate(vals):
    ax.text(max(v, 0.57 if i == 3 else v) + 0.015, i, f"{v:.0%}", va="center", fontsize=9)
ax.set_yticks(range(5), labels)
ax.invert_yaxis()
ax.set_xlim(0, 1)
ax.set_xlabel("Replies stating the user's wrong answer (40 held-out questions)")
ax.set_title("One direction at layer 14 switches sycophancy off or on")
save(fig, "fig7_steering")
