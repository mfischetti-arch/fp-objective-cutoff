#!/usr/bin/env python3
"""
Le figure del paper v2, dai file prodotti dagli aggregatori (mai dai numeri a mano).

    python figs_v2.py          # da paper/: legge band_positions_3seeds.csv (o band_positions.csv)

fig5_band.pdf     dove stanno gli arrotondati ammissibili e migliorativi nella fascia [U, z_inc]
                  (agg_band_seeds.py --dump band_positions_3seeds.csv, tre semi; ripiego sul solo
                  seme 0 di agg_band.py --hist --dump band_positions.csv). E' la Figura 2 della v3.
(fig6_profile.pdf, il performance profile di E1 delle campagne vecchie, e' stato tolto il 07/09/2026:
 non era piu' nel paper.)

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


def fig_band():
    # Dal 04/09/2026 la figura mette insieme i TRE semi (band_positions_3seeds.csv, scritto da
    # fpc/agg_band_seeds.py --dump); se manca, ripiega sul solo seme 0 (band_positions.csv,
    # da agg_band.py --dump), che era la figura della v3 prima dell'audit (rilievo M7).
    path = os.path.join(HERE, "band_positions_3seeds.csv")
    if not os.path.exists(path):
        path = os.path.join(HERE, "band_positions.csv")
    if not os.path.exists(path):
        print("manca band_positions.csv: salto fig5"); return
    print("fig5 da", os.path.basename(path))
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
    ax.set_xlabel("position in $[U, z_{\\mathrm{inc}}]$")
    ax.set_ylabel("lost improving rounded points")
    ax.set_xlim(0, 1)
    ax.legend(frameon=False, loc="upper right")
    med = sorted(allpos)[len(allpos) // 2]
    ax.axvline(med, color="#444444", linewidth=1, linestyle="--")
    ax.annotate(f"median {med:.3f}", (med, ax.get_ylim()[1] * 0.92), xytext=(6, 0),
                textcoords="offset points", fontsize=8, color="#444444")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig5_band.pdf"))
    print(f"fig5_band.pdf: {len(allpos)} punti, mediana {med:.3f}")


if __name__ == "__main__":
    fig_band()
