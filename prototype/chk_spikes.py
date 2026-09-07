#!/usr/bin/env python
# Chi genera gli spike della Figura 2 (ping-pong, 05/09/2026): classifica ogni giro dei csv
# di grid/ dal solo confronto dist/frac (fp.py: dist = ||x_t - x_hat||_1 DOPO l'anti-ciclo).
#   puro    : dist == frac            -> x_hat e' l'arrotondamento dell'iterato LP
#   flip    : dist = frac + T - 2F    -> ramo FGL (x_hat ripete il precedente), T in [10,30],
#                                        F = frazionarieta' delle T componenti ribaltate
#   restart : dist ~ 0.2 * nbin       -> ramo «chiave gia' vista» (p = gap + max(rand-0.3, 0) > 0.5)
# La stima T = ceil(dist - frac) vale solo se frac < 0.5 (altrimenti e' un minorante); la
# fascia 1e-7 < dist - frac < 0.5 resta non classificata (4 punti su 5197 a lam 0.5 s0).
# Il censimento «none» NON e' un baseline: senza cutoff la pompa si ferma su un punto intero
# e da li' in poi ogni giro e' un flip (fp.py riparte dopo un intero, per disegno).
# Uso: python chk_spikes.py [grid]   (verificato da 4 agenti avversariali, workflow del 05/09)
import csv, glob, json, os, sys
import numpy as np

GRID = sys.argv[1] if len(sys.argv) > 1 else "."
TOL = 1e-6
FLIPMAX = 31.0

def load(path):
    rows = list(csv.DictReader(open(path)))
    js = json.load(open(path[:-4] + ".json"))
    f = lambda k: np.array([float(r[k]) for r in rows])
    d = dict(it=f("it").astype(int), cz_lp=f("cz_lp"), cz=f("cz_round"), frac=f("frac"),
             dist=f("dist"), feas=f("feas") > 0.5, ub_free=f("ub_free") > 0.5, ub=f("ub"))
    d["U"], d["zref"], d["nbin"] = js["ub"], js["z_ref"], js["nbin"]
    df = d["dist"] - d["frac"]
    d["noflip"] = np.abs(df) < 1e-7
    d["flip"] = (df >= 0.5) & (df <= FLIPMAX)
    d["restart"] = df > FLIPMAX
    d["T"] = np.ceil(df - 1e-9).astype(int)           # frac < 0.5 -> T = ceil(dist - frac)
    d["lost"] = d["feas"] & (d["cz"] > d["U"] + TOL) & (d["cz"] < d["zref"] - TOL)
    d["acc"] = d["feas"] & (d["cz"] <= d["U"] + TOL)
    d["on_cut"] = np.abs(d["cz_lp"] - d["U"]) < 1e-6
    same = np.zeros(len(rows), bool)
    same[1:] = (np.abs(np.diff(d["frac"])) < 1e-9) & (np.abs(np.diff(d["cz_lp"])) < 1e-6)
    d["same_lp"] = same
    return d

def report_inst(path, N=150):
    d = load(path)
    m = ~d["ub_free"]
    m[np.cumsum(m) > N] = False
    n = m.sum()
    print(f"{os.path.basename(path)}: primi {n} giri, U={d['U']:.2f} z_ref={d['zref']:.0f}")
    for k in ("noflip", "flip", "restart", "on_cut", "same_lp", "lost", "acc", "feas"):
        print(f"  {k:8s} {int((d[k] & m).sum()):4d}")
    lf, lp = int((d["lost"] & d["flip"] & m).sum()), int((d["lost"] & d["noflip"] & m).sum())
    print(f"  lost da flip {lf}, lost da arrotondamento puro {lp}")
    fl = d["flip"] & m
    print(f"  T dei flip: min {d['T'][fl].min()} max {d['T'][fl].max()} media {d['T'][fl].mean():.1f}")
    print(f"  giri con flip: parita' pari {int((fl & (d['it'] % 2 == 0)).sum())}, dispari {int((fl & (d['it'] % 2 == 1)).sum())}")
    print(f"  spike (flip) ammissibili {int((fl & d['feas']).sum())}/{int(fl.sum())}; "
          f"sopra z_ref {int((fl & d['feas'] & (d['cz'] >= d['zref'] - TOL)).sum())}")
    nf = d["noflip"] & m
    y = (d["cz"] - d["U"]) / (d["zref"] - d["U"])
    print(f"  y degli arrotondamenti puri: min {y[nf].min():.4f} mediana {np.median(y[nf]):.4f} max {y[nf].max():.4f}")
    print(f"  y degli spike: min {y[fl].min():.3f} mediana {np.median(y[fl]):.3f} max {y[fl].max():.3f}")
    # e' un 2-ciclo esatto? flip esattamente ai giri in cui l'LP e' lo stesso del giro prima
    print(f"  flip & same_lp {int((fl & d['same_lp']).sum())}, flip & ~same_lp {int((fl & ~d['same_lp']).sum())}, "
          f"same_lp & noflip {int((nf & d['same_lp']).sum())}")
    ia = np.where(d["acc"] & m)[0]
    print(f"  primo accettato al giro {d['it'][ia[0]] if len(ia) else None}; "
          f"restart nei 2000 giri: {int(d['restart'].sum())} (primo al giro {d['it'][d['restart']][0] if d['restart'].any() else None})")
    tot = ~d["ub_free"]
    print(f"  tutti i {tot.sum()} giri col cutoff: flip {100*(d['flip']&tot).sum()/tot.sum():.0f}%, "
          f"lost da flip {int((d['lost']&d['flip']&tot).sum())} / lost {int((d['lost']&tot).sum())}")

def census(mode):
    out = []
    for p in sorted(glob.glob(os.path.join(GRID, f"*__{mode}_lam0.5_s0.csv"))):
        d = load(p)
        n = len(d["it"])
        lost = d["lost"].sum()
        out.append((os.path.basename(p).split("__")[0], n, 100 * d["flip"].sum() / n,
                    100 * d["restart"].sum() / n, 100 * d["on_cut"].sum() / n, int(lost),
                    (100 * (d["lost"] & d["flip"]).sum() / lost) if lost else float("nan")))
    return out

def table3(here):
    """Tabella 1 spaccata puri/flip, con la STESSA aggregazione del paper: per istanza la
    mediana sui tre semi (seme 0 in grid/, nomi v1; semi 1-2 in grid_s12/, nomi v2), poi la
    mediana fra istanze, per famiglia (inst_list.txt, come agg_band.fam_of) e su tutte.
    Frazione = ammissibili sopra U / ammissibili (tutti i giri, U = colonna ub: coincide con
    n_killed/n_feas dei json); posizione = mediana di y sui persi (feas, U < c'x < z_ref)."""
    import statistics as st
    sys.path.insert(0, here)
    import agg_band as B
    fam = B.stem_map(B.fam_of(os.path.join(here, "inst_list.txt")))
    print("Tabella 1 spaccata (mediana sui semi dentro l'istanza, poi fra istanze):")
    print("lam_v2 famiglia      | frazione sopra U: tutti  puri (ist.) | posizione: tutti  puri (ist.) | persi da flip pooled")
    for lam in (0.25, 0.5, 0.75):
        lam_v1 = round(1.0 - lam, 2)
        acc = {}                                   # inst -> dict di liste per seme
        for seed in (0, 1, 2):
            pat = (os.path.join(here, "grid", f"*__cutoff_lam{lam_v1}_s0.csv") if seed == 0
                   else os.path.join(here, "grid_s12", f"*__cutoff_lam{lam}_s{seed}.csv"))
            for p in sorted(glob.glob(pat)):
                d = load(p); inst = os.path.basename(p).split("__")[0]
                a = acc.setdefault(inst, dict(fa=[], fp=[], pa=[], pp=[], nl=0, nf=0))
                F = d["feas"]; above = d["cz"] > d["ub"] + TOL
                if F.any():
                    a["fa"].append(above[F].mean())
                    Fp = F & d["noflip"]
                    if Fp.any(): a["fp"].append(above[Fp].mean())
                y = (d["cz"] - d["U"]) / (d["zref"] - d["U"]); L = d["lost"]
                if L.any():
                    a["pa"].append(float(np.median(y[L])))
                    if (L & d["noflip"]).any(): a["pp"].append(float(np.median(y[L & d["noflip"]])))
                    a["nl"] += int(L.sum()); a["nf"] += int((L & d["flip"]).sum())
        for fname in ("ORLib_setcover", "miplib2003", "miplib2017", "all"):
            sel = {i: a for i, a in acc.items() if fname == "all" or fam.get(i, "?") == fname}
            fa = [st.median(a["fa"]) for a in sel.values() if a["fa"]]
            fp_ = [st.median(a["fp"]) for a in sel.values() if a["fp"]]
            pa = [st.median(a["pa"]) for a in sel.values() if a["pa"]]
            pp = [st.median(a["pp"]) for a in sel.values() if a["pp"]]
            nl = sum(a["nl"] for a in sel.values()); nf = sum(a["nf"] for a in sel.values())
            print(f"{lam:5.2f} {fname:12s} | {100*st.median(fa):5.1f}% {100*st.median(fp_):5.1f}% ({len(fa)}/{len(fp_)}) | "
                  f"{st.median(pa):.3f} {st.median(pp):.3f} ({len(pa)}/{len(pp)}) | {100*nf/nl:5.1f}% ({nf}/{nl})")


if __name__ == "__main__":
    if "--table" in sys.argv:
        table3(os.path.dirname(os.path.abspath(__file__))); sys.exit(0)
    report_inst(os.path.join(GRID, "scpnrh3__cutoff_lam0.5_s0.csv"))
    print()
    print("Censimento lam 0.5 seme 0: istanza | giri | %flip | %restart | %LP sul cutoff | lost | %lost da flip")
    for mode in ("cutoff", "none"):
        rows = census(mode)
        print(f"--- {mode}: {len(rows)} istanze")
        for r in rows:
            print(f"  {r[0]:22s} {r[1]:5d} {r[2]:6.1f} {r[3]:6.1f} {r[4]:6.1f} {r[5]:6d} {r[6]:6.1f}")
        a = np.array([r[2:] for r in rows], float)
        print(f"  MEDIANA                     {np.nanmedian(a[:,0]):6.1f} {np.nanmedian(a[:,1]):6.1f} "
              f"{np.nanmedian(a[:,2]):6.1f} {np.nanmedian(a[:,3]):6.0f} {np.nanmedian(a[:,4]):6.1f}")
        L = a[:, 3]; LF = a[:, 4] * a[:, 3] / 100
        print(f"  POOLED lost {np.nansum(L):.0f}, da flip {np.nansum(LF):.0f} = {100*np.nansum(LF)/np.nansum(L):.1f}%")
