"""Re-score the saved Phase 1b replies with scorer v2 and redraw the figures. No GPU needed.

Reads   results/phase1b/phase1b_turns.csv, results/phase1b/phase1b_questions.csv, results/phase1b/phase1b_per_question.csv (for the margin)
Writes  results/phase1b/phase1b_v2_turns.csv, results/phase1b/phase1b_v2_per_question.csv, results/phase1b/phase1b_v2_summary.csv,
        results/phase1b/phase1b_v2_stats.txt, figures/phase1b/phase1b_v2_*.png

Run from the repo root:  python3 src/rescore_phase1b.py
"""
import ast
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from scoring import APOLOGY, HOLDS_CORRECT, label  # noqa: E402

RES, FIG = "results/phase1b", "figures/phase1b"
CONDITIONS = ["wrong_plain", "wrong_expert", "wrong_novice", "doubt_only", "correct_push"]

# ---------------------------------------------------------------- re-score every reply
q = pd.read_csv(f"{RES}/phase1b_questions.csv")
for col in ["correct_aliases", "wrong_aliases"]:
    q[col] = q[col].apply(ast.literal_eval)
qinfo = q.set_index("qid")

turns = pd.read_csv(f"{RES}/phase1b_turns.csv").rename(columns={"label": "label_v1"})
turns["label"] = [label(r.reply, qinfo.at[r.qid, "category"], qinfo.at[r.qid, "correct_aliases"], qinfo.at[r.qid, "wrong_aliases"])
                  for r in turns.itertuples()]
turns["apologised"] = turns.reply.apply(lambda s: bool(APOLOGY.search(s)))
turns.to_csv(f"{RES}/phase1b_v2_turns.csv", index=False)

margin = pd.read_csv(f"{RES}/phase1b_per_question.csv")[["qid", "margin"]].drop_duplicates("qid")
per = (turns.groupby(["qid", "category", "difficulty", "condition"])
       .agg(adopted_wrong=("label", lambda s: (s == "WRONG").any()),
            abandoned=("label", lambda s: s.isin(["WRONG", "OTHER"]).any()),
            first_wrong_turn=("label", lambda s: next((t for t, l in enumerate(s, 1) if l == "WRONG"), np.nan)),
            final_label=("label", "last"),
            apologised_t1=("apologised", "first"))
       .reset_index()
       .merge(margin, on="qid"))
per.to_csv(f"{RES}/phase1b_v2_per_question.csv", index=False)

# ---------------------------------------------------------------- statistics
def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half

def rate(series):
    k, n = int(series.sum()), len(series)
    lo, hi = wilson(k, n)
    return f"{k / n:.0%} [{lo:.0%}-{hi:.0%}]" if n else "n/a"

def exact_mcnemar(a, b):
    """Two-sided exact McNemar test on paired booleans a, b."""
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    n = only_a + only_b
    if n == 0:
        return only_a, only_b, 1.0
    tail = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n
    return only_a, only_b, min(1.0, 2 * tail)

def auc(held, caved):
    """P(random held question has a higher margin than a random caved one); ties count half."""
    h, c = np.asarray(held)[:, None], np.asarray(caved)[None, :]
    return float(((h > c) + 0.5 * (h == c)).mean())

lines = []
def out(s=""):
    print(s)
    lines.append(s)

rows = []
for cond in CONDITIONS:
    g = per[per.condition == cond]
    rows.append({"condition": cond, "n": len(g),
                 "adopted user's wrong answer (any turn)": rate(g.adopted_wrong) if cond.startswith("wrong") else "-",
                 "abandoned correct answer (any turn)": rate(g.abandoned),
                 "holds correct answer at turn 3": rate(g.final_label.isin(HOLDS_CORRECT)),
                 "apologises at turn 1": rate(g.apologised_t1)})
summary = pd.DataFrame(rows)
summary.to_csv(f"{RES}/phase1b_v2_summary.csv", index=False)
out(summary.to_string(index=False))

out("\nLabel changes v1 -> v2:")
out(pd.crosstab(turns.label_v1, turns.label).to_string())

out("\nLabel shares by condition and turn (v2):")
out(pd.crosstab([turns.condition, turns.turn], turns.label, normalize="index").round(2).to_string())

out("\nPaired comparisons (exact McNemar):")
for col, name in [("adopted_wrong", "adopted wrong by turn 3"), ("t1", "adopted wrong at turn 1")]:
    per["t1"] = per.first_wrong_turn == 1
    for a, b in [("wrong_expert", "wrong_novice"), ("wrong_expert", "wrong_plain"), ("wrong_plain", "wrong_novice")]:
        x = per[per.condition == a].set_index("qid")[col]
        y = per[per.condition == b].set_index("qid")[col]
        x, y = x.align(y, join="inner")
        oa, ob, p = exact_mcnemar(x, y)
        out(f"  {name}: {a} {x.mean():.0%} vs {b} {y.mean():.0%} | discordant {oa} vs {ob} | p = {p:.2g}")

wp = per[per.condition == "wrong_plain"]
held, caved = wp[~wp.adopted_wrong].margin, wp[wp.adopted_wrong].margin
rng = np.random.default_rng(0)
obs = auc(held, caved)
m, lab = wp.margin.to_numpy(), wp.adopted_wrong.to_numpy()
perm = np.array([auc(m[~l], m[l]) for l in (rng.permutation(lab) for _ in range(5000))])
p_perm = (np.sum(np.abs(perm - 0.5) >= abs(obs - 0.5)) + 1) / (len(perm) + 1)
out(f"\nConfidence vs caving (wrong_plain): median margin held {held.median():.1f} (n={len(held)}) vs caved {caved.median():.1f} (n={len(caved)})")
out(f"  AUC = {obs:.2f}, permutation p = {p_perm:.2g}")
for cat, g in wp.groupby("category"):
    out(f"  {cat}: AUC = {auc(g[~g.adopted_wrong].margin, g[g.adopted_wrong].margin):.2f} "
        f"(held {int((~g.adopted_wrong).sum())}, caved {int(g.adopted_wrong.sum())})")
out("  median margin by turn of first switch: " +
    ", ".join(f"{('never' if t == 9 else f'turn {int(t)}')}: {v:.1f}"
              for t, v in wp.groupby(wp.first_wrong_turn.fillna(9)).margin.median().items()))
open(f"{RES}/phase1b_v2_stats.txt", "w").write("\n".join(lines) + "\n")

# ---------------------------------------------------------------- figures
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a63", "#e6e5df", "#ffffff"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK})
pct = plt.FuncFormatter(lambda v, _: f"{v:.0%}")

def tidy(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)

cats = ["arithmetic", "fact"]

# Figure 1: what Gemma does at each turn (plain pushback)
STATES = [("Keeps answer, no apology", "#2a78d6"),
          ("Apologises but keeps answer", "#1baf7a"),
          ("Says 'you're right' but reframes", "#e87ba4"),
          ("No answer given", "#eda100"),
          ("Switches to user's answer", "#eb6834"),
          ("Other / unclear", "#9b9a92")]

def state(row):
    if row.label == "RESISTS":
        return STATES[0][0]
    if row.label == "CORRECT":
        return STATES[1][0] if row.apologised else STATES[0][0]
    return {"REFRAME": STATES[2][0], "NONE": STATES[3][0], "WRONG": STATES[4][0]}.get(row.label, STATES[5][0])

tp = turns[turns.condition == "wrong_plain"].copy()
tp["state"] = tp.apply(state, axis=1)
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4), sharey=True)
for ax, cat in zip(axes, cats):
    sub = tp[tp.category == cat]
    shares = pd.crosstab(sub.turn, sub.state, normalize="index").reindex(columns=[s for s, _ in STATES], fill_value=0)
    bottom = np.zeros(len(shares))
    for name, color in STATES:
        ax.bar(shares.index, shares[name], 0.6, bottom=bottom, color=color, edgecolor=SURFACE, linewidth=1.5, label=name)
        bottom += shares[name].values
    ax.set_xticks([1, 2, 3], ["push 1", "push 2", "push 3"])
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(pct)
    ax.set_title(f"{cat.capitalize()} (n={sub.qid.nunique()})", loc="left", fontsize=11)
    tidy(ax)
axes[0].set_ylabel("Share of conversations")
axes[1].legend(frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
fig.suptitle("How Gemma-2-2B-it gives in under pushback", x=0.01, ha="left", fontsize=12)
fig.tight_layout()
fig.savefig(f"{FIG}/phase1b_v2_trajectory.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# Figure 2: abandoned the correct answer, by condition
COND_STYLE = {"wrong_plain": ("Wrong answer", "#2a78d6"), "wrong_expert": ("Wrong + 'professor'", "#eb6834"),
              "wrong_novice": ("Wrong + 'student'", "#1baf7a"), "doubt_only": ("'Are you sure?' only", "#eda100"),
              "correct_push": ("Correct answer (control)", "#e87ba4")}
fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
for ax, cat in zip(axes, cats):
    sub = per[per.category == cat]
    for i, cond in enumerate(CONDITIONS):
        g = sub[sub.condition == cond].abandoned
        k, n = int(g.sum()), len(g)
        p = k / n
        lo, hi = wilson(k, n)
        ax.bar(i, p, 0.7, color=COND_STYLE[cond][1], yerr=[[max(p - lo, 0)], [max(hi - p, 0)]], ecolor=MUTED,
               error_kw={"elinewidth": 1, "capsize": 3})
        ax.annotate(f"{p:.0%}", (i, max(hi, p)), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9, color=INK)
    ax.set_xticks(range(len(CONDITIONS)), [COND_STYLE[c][0] for c in CONDITIONS], rotation=25, ha="right", fontsize=9)
    ax.set_ylim(0, 1.08)
    ax.yaxis.set_major_formatter(pct)
    ax.set_title(f"{cat.capitalize()} (n={sub.qid.nunique()})", loc="left", fontsize=11)
    tidy(ax)
axes[0].set_ylabel("Abandoned the correct answer\n(by push 3)")
fig.suptitle("Is it sycophancy or just doubt? Pushback conditions compared", x=0.01, ha="left", fontsize=12)
fig.text(0.01, -0.12, "Error bars: 95% Wilson intervals. 'Abandoned' = stated the user's wrong answer or another wrong answer at any turn.",
         fontsize=8, color=MUTED)
fig.tight_layout()
fig.savefig(f"{FIG}/phase1b_v2_conditions.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# Figure 3: confidence vs caving (plain pushback), all questions pooled into quartiles plus per category
CAT_COLOR = {"arithmetic": "#2a78d6", "fact": "#eb6834"}
fig, ax = plt.subplots(figsize=(6.8, 4))
for cat in cats:
    g = wp[wp.category == cat].copy()
    g["bin"] = pd.qcut(g.margin, 4, duplicates="drop")
    b = g.groupby("bin", observed=True).agg(x=("margin", "median"), k=("adopted_wrong", "sum"), n=("adopted_wrong", "size"))
    p = b.k / b.n
    ci = np.array([wilson(int(k), int(n)) for k, n in zip(b.k, b.n)])
    ax.errorbar(b.x, p, yerr=[np.clip(p - ci[:, 0], 0, None), np.clip(ci[:, 1] - p, 0, None)], color=CAT_COLOR[cat],
                ecolor=CAT_COLOR[cat], elinewidth=1, capsize=3, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=f"{cat} (n={len(g)})")
    ax.annotate(cat, (b.x.iloc[-1], p.iloc[-1]), xytext=(8, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
ax.set_xlabel("Confidence margin: log P(correct) − log P(user's wrong answer)")
ax.set_ylabel("Adopted user's wrong answer")
ax.set_ylim(0, 1.05)
ax.yaxis.set_major_formatter(pct)
ax.set_title("Less confident answers are abandoned more often (quartile bins)", loc="left", fontsize=11)
tidy(ax)
ax.legend(frameon=False, fontsize=9, loc="lower left")
fig.tight_layout()
fig.savefig(f"{FIG}/phase1b_v2_confidence.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# Figure 4: margin by turn of first switch (dose-response in time)
order = [("turn 1", 1.0), ("turn 2", 2.0), ("turn 3", 3.0), ("never", 9.0)]
fig, ax = plt.subplots(figsize=(6.8, 4))
groups = wp.assign(t=wp.first_wrong_turn.fillna(9.0))
for i, (name, t) in enumerate(order):
    vals = groups[groups.t == t].margin.to_numpy()
    jitter = np.random.default_rng(i).uniform(-0.18, 0.18, len(vals))
    ax.scatter(np.full(len(vals), i) + jitter, vals, s=14, color="#2a78d6", alpha=0.45, linewidths=0)
    if len(vals):
        ax.plot([i - 0.28, i + 0.28], [np.median(vals)] * 2, color=INK, linewidth=2)
        ax.annotate(f"median {np.median(vals):.1f}\nn={len(vals)}", (i + 0.3, np.median(vals)), va="center", fontsize=8, color=INK)
ax.set_xticks(range(len(order)), [f"switched at\n{n}" if n != "never" else "never\nswitched" for n, _ in order])
ax.set_xlim(-0.5, len(order) - 0.1)
ax.set_ylabel("Confidence margin")
ax.set_title("The less confident Gemma is, the sooner it gives in", loc="left", fontsize=11)
tidy(ax)
fig.tight_layout()
fig.savefig(f"{FIG}/phase1b_v2_flip_timing.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("\nWrote results/phase1b/phase1b_v2_*.csv, results/phase1b/phase1b_v2_stats.txt and figures/phase1b/phase1b_v2_*.png")
