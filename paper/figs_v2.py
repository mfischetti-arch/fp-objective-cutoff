#!/usr/bin/env python3
"""
Le figure del paper v2, dai file prodotti dagli aggregatori (mai dai numeri a mano).

    python figs_v2.py          # da paper/: legge band_positions.csv e e1_profile.csv

fig5_band.pdf     dove stanno gli arrotondati ammissibili e migliorativi nella fascia [U, z_inc]
                  (agg_band.py --dump band_positions.csv, opzioni di default)
fig6_profile.pdf  performance profile di E1 sul gap finale (agg_e1.py --dump e1_profile.csv:
                  colonne braccio, istanza, gap)

Colori: palette categoriale a 5 (blu, arancio, verde, viola, grigio) in ordine fisso, uno per
braccio, con stile di linea diverso per ciascuno perche' la figura regga anche in bianco e nero.
"""
import csv
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e4e4e4", "grid.linewidth": 0.6,
                     "axes.edgecolor": "#888888", "xtick.color": "#444444", "ytick.color": "#444444"})

# i bracci nell'ordine del paper, con nome, colore e tratto
# palette categoriale validata (slot 1-5 della skill dataviz, ordine fisso)
ARMS = [("bare",    "plain",           "#2a78d6", "-"),
        ("recbare", "recover",         "#eb6834", "--"),
        ("cut50",   "cutoff",          "#1baf7a", ":"),
        ("rec50",   "cutoff+recover",  "#eda100", "-."),
        ("prog",    "cut(0.95)",       "#e87ba4", "-")]


def fig_band():
    path = os.path.join(HERE, "band_positions.csv")
    if not os.path.exists(path):
        print("manca band_positions.csv: salto fig5"); return
    pos = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pos[r["fam"].strip().lower()].append(float(r["pos"]))
    fams = [("covering", "set covering"), ("miplib2003", "MIPLIB 2003"), ("miplib2017", "MIPLIB 2017")]
    fams = [(k, lab) for k, lab in fams if k in pos] or [(k, k) for k in pos]
    allpos = [p for v in pos.values() for p in v]
    fig, ax = plt.subplots(figsize=(4.6, 2.6))
    bins = [i / 10 for i in range(11)]
    ax.hist([pos[k] for k, _ in fams], bins=bins, stacked=True, color=["#2a78d6", "#eb6834", "#1f9e6a"][:len(fams)],
            edgecolor="white", linewidth=0.8, label=[lab for _, lab in fams])
    ax.set_xlabel("position in $[U, z_{\\mathrm{inc}}]$:  0 = on the cutoff, 1 = on the incumbent")
    ax.set_ylabel("feasible improving rounded points")
    ax.set_xlim(0, 1)
    ax.legend(frameon=False, loc="upper right")
    med = sorted(allpos)[len(allpos) // 2]
    ax.axvline(med, color="#444444", linewidth=1, linestyle="--")
    ax.annotate(f"median {med:.2f}", (med, ax.get_ylim()[1] * 0.92), xytext=(6, 0),
                textcoords="offset points", fontsize=8, color="#444444")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig5_band.pdf"))
    print(f"fig5_band.pdf: {len(allpos)} punti, mediana {med:.3f}")


def fig_profile():
    path = os.path.join(HERE, "e1_profile.csv")
    if not os.path.exists(path):
        print("manca e1_profile.csv: salto fig6"); return
    gap = defaultdict(dict)   # inst -> arm -> gap
    with open(path, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames
        karm = [c for c in cols if c.lower().startswith("arm") or c.lower().startswith("bracc")][0]
        kinst = [c for c in cols if "ist" in c.lower() or "inst" in c.lower()][0]
        kgap = [c for c in cols if "gap" in c.lower()][0]
        for r in rd:
            gap[r[kinst]][r[karm]] = float(r[kgap])
    arms = [a for a in ARMS if any(a[0] in g for g in gap.values())]
    insts = [i for i, g in gap.items() if all(a[0] in g for a in arms)]
    # ratio al migliore, in punti di gap: tau = gap_arm - min gap (differenza, non rapporto: il gap e' gia' relativo)
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    taus = [x / 100 for x in range(0, 3001)]
    for key, lab, col, ls in arms:
        diffs = [gap[i][key] - min(gap[i][a[0]] for a in arms) for i in insts]
        ys = [sum(1 for d in diffs if d <= t + 1e-9) / len(insts) for t in taus]
        ax.plot(taus, ys, color=col, linestyle=ls, linewidth=1.6, label=lab)
    ax.set_xlabel("distance from the best variant, in points of final gap")
    ax.set_ylabel("fraction of instances")
    ax.set_xlim(0, 30); ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig6_profile.pdf"))
    print(f"fig6_profile.pdf: {len(insts)} istanze, {len(arms)} bracci")


if __name__ == "__main__":
    fig_band()
    fig_profile()
