# Figura «ping-pong» di §2: le due sequenze della pompa from-scratch con cutoff su
# un'istanza (default scpnrh3, seme 0, lambda_v2 = 0.5, primi 150 giri), dai csv per
# giro di ../fpc/grid/ (nomi in convenzione v1: a 0.5 le due convenzioni coincidono).
# y = (c'x - U)/(z_inc - U): 0 = cutoff, 1 = incumbent di riferimento (z_ref).
# Classi dell'arrotondato come in fp.py (TOL = 1e-6): perso = ammissibile, sopra U,
# sotto z_ref; accettato = ammissibile e <= U; non migliorante = ammissibile e >= z_ref.
# Uso: python fig_pingpong.py [inst] [giri]      -> fig7_pingpong.pdf
import csv, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
# i csv per giro stanno in ../fpc/grid/ (repo di ricerca) o in ../prototype/grid/ (pacchetto MPC)
GRID = next((d for d in (os.path.join(HERE, "..", "fpc", "grid"),
                         os.path.join(HERE, "..", "prototype", "grid")) if os.path.isdir(d)),
            os.path.join(HERE, "..", "fpc", "grid"))
inst = sys.argv[1] if len(sys.argv) > 1 else "scpnrh3"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 150
TOL = 1e-6
YMAX = 1.25

p = os.path.join(GRID, f"{inst}__cutoff_lam0.5_s0.csv")
js = json.load(open(p[:-4] + ".json"))
zinc, U = js["z_ref"], js["ub"]
band = zinc - U
rows = [r for r in csv.DictReader(open(p)) if r["ub_free"] == "0"][:N]
it = np.array([int(r["it"]) for r in rows])
cz = np.array([float(r["cz_round"]) for r in rows])
ylp = (np.array([float(r["cz_lp"]) for r in rows]) - U) / band
yrd = (cz - U) / band
feas = np.array([r["feas"] == "1" for r in rows])
lost = feas & (cz > U + TOL) & (cz < zinc - TOL)
acc = feas & (cz <= U + TOL)
far = feas & (cz >= zinc - TOL)
inf = ~feas
yplot = np.minimum(yrd, YMAX)

fig, ax = plt.subplots(figsize=(6.4, 3.4))
ax.axhspan(0, 1, color="#fff3c4", alpha=.7, lw=0, zorder=0)
ax.axhline(0, color="k", lw=1.0, zorder=1)
ax.axhline(1, color="#666", lw=0.8, ls="--", zorder=1)
ax.vlines(it, np.minimum(ylp, yplot), np.maximum(ylp, yplot), color="#bbb", lw=0.5, zorder=1)
ax.plot(it, ylp, color="#1f77b4", lw=1.0, zorder=2, label=r"LP iterate $\tilde x$")
ax.scatter(it[inf], yplot[inf], marker="x", s=10, color="#999", lw=0.6, zorder=3,
           label=r"$\hat x$ infeasible")
ax.scatter(it[acc], yplot[acc], marker="v", s=16, color="#1f77b4", zorder=4,
           label=r"$\hat x$ feasible, below $U$ (accepted)")
ax.scatter(it[lost], yplot[lost], marker="o", s=16, color="#2ca02c", zorder=5,
           label=r"$\hat x$ feasible and improving, above $U$ (lost)")
ax.scatter(it[far], yplot[far], marker="o", s=14, facecolors="none", edgecolors="#2ca02c",
           lw=0.7, zorder=4, label=r"$\hat x$ feasible, not improving")
ax.set_ylim(-0.4, YMAX + 0.02)
ax.set_xlim(it.min() - 1, it.max() + 1)
ax.set_xlabel("pumping round")
ax.set_ylabel(r"$(c^\top x - U)\,/\,(z_{\mathrm{inc}} - U)$")
ax.text(1.005, 0, "cutoff $U$", transform=ax.get_yaxis_transform(), ha="left",
        va="center", fontsize=8, color="k")
ax.text(1.005, 1, r"incumbent $z_{\mathrm{inc}}$", transform=ax.get_yaxis_transform(),
        ha="left", va="center", fontsize=8, color="#666")
ax.grid(axis="y", color="#eee", lw=0.5, zorder=0)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.legend(fontsize=8.5, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.0),
           columnspacing=1.5, handletextpad=0.5)
fig.set_size_inches(6.4, 3.9)
fig.tight_layout(rect=(0, 0.15, 1, 1))
out = os.path.join(HERE, "fig7_pingpong.pdf")
fig.savefig(out)
print(f"{out}: {inst}, {len(rows)} rounds, lost {lost.sum()}, accepted {acc.sum()}, "
      f"not improving {far.sum()}, infeasible {inf.sum()}, clipped {(yrd > YMAX).sum()}; "
      f"z_lp {js['z_lp']:.4g}, U {U:.4g}, z_inc {zinc:.4g}")
