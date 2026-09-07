#!/usr/bin/env python3
"""Robustezza sui semi della POSIZIONE nella fascia (Tabella 1, colonne di destra;
Figura 1). Il paper v3 la misurava sul solo seme 0 (audit ChatGPT, M7): qui la si
ricalcola, con la stessa definizione canonica di agg_band.py, sui semi 0, 1, 2.

Dati: seme 0 in grid/ (job03 + job20), semi 1 e 2 in grid_s12/ (job25, 04/09/2026,
out/grid_s12/ sul cluster). Per ogni lambda_v2 in {0.25, 0.5, 0.75} stampa, per
seme, la mediana delle mediane per istanza e il numero di istanze con mediana < 0.5;
poi l'aggregato «per istanza sui tre semi» (regola dell'handoff: prima dentro
l'istanza, poi fra istanze): posizione dell'istanza = mediana dei tre valori per seme.

Controllo di consistenza: i .json nuovi dei semi 1-2 contro quelli di grid/ (stessi
seme e parametri: z_ref, iters, n_feas, n_killed_improving devono coincidere, salvo
i run fermati dal limite di 120 s, dove il numero di giri puo' differire).

Uso: python agg_band_seeds.py [--s12 grid_s12] [--latex]
"""
import argparse, glob, json, os, statistics as st, sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import agg_band as B

CANON = dict(ucol="ub_eff", zinc="zref", sel="killed_impr", clamp=False)


def lam_file(seed, lam_v1):
    """Nome del file per il livello lam_v1. grid/ (seme 0, job03/job20) e' nominata in
    convenzione v1 (file lam0.25 = lambda_v2 0.75); grid_s12/ (job25, fp.py del 03/09,
    json con lam_conv = v2) e' nominata in v2: lo stesso livello sta nel file lam(1-v1).
    Verificato sui json: (ub - z_lp)/(z_ref - z_lp) = 0.75 in grid/*lam0.25* e 0.25 in
    grid_s12/*lam0.25*. A 0.5 le due convenzioni coincidono."""
    return lam_v1 if seed == 0 else round(1.0 - lam_v1, 2)


def per_inst_median(d, sfam, lam_v1, seed):
    data = B.band_data(d, sfam, "cutoff", lam_file(seed, lam_v1), seed, "w0.05", **CANON)
    return {b: (f, st.median([q for _, q in ps]), len(ps))
            for b, (f, ps) in data.items() if ps}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--s0", default=os.path.join(here, "grid"))
    p.add_argument("--s12", default=os.path.join(here, "grid_s12"))
    p.add_argument("--inst-list", default=os.path.join(here, "inst_list.txt"))
    p.add_argument("--latex", action="store_true")
    p.add_argument("--dump", nargs="?", const="band_positions_3seeds.csv", default=None,
                   help="scrive inst,fam,seed,it,pos per i tre semi a lambda_v2 = 0.5 (Figura 1)")
    a = p.parse_args()
    if a.dump:
        import csv
        sfam0 = B.stem_map(B.fam_of(a.inst_list))
        n = 0
        with open(a.dump, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["inst", "fam", "seed", "it", "pos"])
            for s, d in ((0, a.s0), (1, a.s12), (2, a.s12)):
                data = B.band_data(d, sfam0, "cutoff", 0.5, s, "w0.05", **CANON)
                for b in sorted(data):
                    fm, ps = data[b]
                    for it, q in ps:
                        w.writerow([b, B.FAM_LABEL.get(fm, fm), s, it, f"{q:.10g}"])
                        n += 1
        print(f"scritto {a.dump}: {n} righe (tre semi, lambda_v2 = 0.5)\n")
    sfam = B.stem_map(B.fam_of(a.inst_list))
    dirs = {0: a.s0, 1: a.s12, 2: a.s12}

    print("# Posizione nella fascia per seme (definizione canonica di agg_band.py)\n")
    print("pos = (c'x_round - U)/(z_inc - U) sui punti feas, sopra il cutoff e migliori "
          "dell'incumbent di riferimento del run; 0 = sul cutoff, 1 = sull'incumbent.\n")
    rows_tex = []
    for lam_v1 in (0.75, 0.5, 0.25):          # lambda_v2 = 1 - lam_v1: 0.25, 0.5, 0.75
        lv2 = round(1 - lam_v1, 2)
        print(f"## lambda_v2 = {lv2:g}  (file lam{lam_v1})\n")
        print("| seme | istanze | mediana delle mediane per istanza | mediana < 0.5 | punti |")
        print("|---|---|---|---|---|")
        per_seed = {}
        for s in (0, 1, 2):
            pi = per_inst_median(dirs[s], sfam, lam_v1, s)
            per_seed[s] = pi
            if not pi:
                print(f"| {s} | 0 | (nessun csv in {dirs[s]}) | | |")
                continue
            v = [m for _, m, _ in pi.values()]
            print(f"| {s} | {len(v)} | {st.median(v):.3f} | "
                  f"{sum(1 for m in v if m < 0.5)}/{len(v)} | {sum(n for _, _, n in pi.values())} |")
        insts = set().union(*[set(pi) for pi in per_seed.values()])
        agg = {}
        for b in insts:
            vals = [per_seed[s][b][1] for s in per_seed if b in per_seed[s]]
            if vals:
                agg[b] = (next(per_seed[s][b][0] for s in per_seed if b in per_seed[s]),
                          st.median(vals), len(vals))
        v = [m for _, m, _ in agg.values()]
        n3 = sum(1 for _, _, k in agg.values() if k == 3)
        print(f"| **per istanza, mediana sui semi** | {len(v)} ({n3} con tre semi) | "
              f"**{st.median(v):.3f}** | {sum(1 for m in v if m < 0.5)}/{len(v)} | |")
        byf = {}
        for f, m, _ in agg.values():
            byf.setdefault(f, []).append(m)
        print("\nPer famiglia (per istanza, mediana sui semi): " + "; ".join(
            f"{B.FAM_LABEL.get(f, f)} {st.median(ms):.3f} ({len(ms)})" for f, ms in sorted(byf.items())))
        print()
        rows_tex.append((lv2, len(v), st.median(v), sum(1 for m in v if m < 0.5),
                         {f: (st.median(ms), len(ms)) for f, ms in byf.items()}))

    print("# Controllo: .json nuovi (semi 1-2, nomi in v2) contro grid/ (nomi in v1)\n")
    print("Stesso livello = file lam L in grid_s12/ contro file lam (1-L) in grid/; il cutoff "
          "`ub` deve coincidere (stesso z_ref della fase A, stesso seme). I contatori coincidono "
          "se il run si e' fermato a max-iter; se l'ha fermato il limite di 120 s il numero "
          "di giri dipende dalla macchina (job25 gira 3 processi per lama).\n")
    keys = ("z_ref", "ub", "iters", "n_feas", "n_killed_improving", "z_best")
    same = diff = missing = ub_diff = both_maxiter_diff = 0
    diffs = []
    for f in sorted(glob.glob(os.path.join(a.s12, "*__cutoff_lam*_s[12].json"))):
        base = os.path.basename(f)
        stem, rest = base.split("__cutoff_lam")
        L, s = rest[:-5].split("_s")
        g = os.path.join(a.s0, f"{stem}__cutoff_lam{round(1 - float(L), 2):g}_s{s}.json")
        if not os.path.exists(g):
            missing += 1
            continue
        new, old = json.load(open(f)), json.load(open(g))
        d = {k: (old.get(k), new.get(k)) for k in keys if old.get(k) != new.get(k)}
        if "ub" in d and old.get("ub") is not None and new.get("ub") is not None \
                and abs(old["ub"] - new["ub"]) <= 1e-6 * max(1.0, abs(old["ub"])):
            del d["ub"]
        if d.get("ub"):
            ub_diff += 1
        if d:
            diff += 1
            if old.get("iters") == 2000 and new.get("iters") == 2000:
                both_maxiter_diff += 1
            diffs.append((base, d, old.get("secs"), new.get("secs")))
        else:
            same += 1
    print(f"coppie: identiche su {keys}: {same}; diverse: {diff} (di cui con `ub` diverso: "
          f"{ub_diff}; diverse pur con entrambi i run a max-iter 2000: {both_maxiter_diff}); "
          f"senza riscontro: {missing}")
    for name, d, so, sn in diffs[:60]:
        print(f"- {name}: {d}  (secs vecchio {so:.0f}, nuovo {sn:.0f})")
    if a.latex:
        # Le tre colonne di destra di Tabella 1 del paper (posizione), nell'ordine
        # lambda_v2 = 0.25, 0.5, 0.75, per famiglia con (n) e le righe di coda.
        rows_tex.sort(key=lambda r: r[0])
        print("\n% Tabella 1, colonne di destra (posizione per istanza, mediana sui tre semi):")
        for fam, lab in zip(B.FAM_ORDER, ("set covering", "MIPLIB 2003", "MIPLIB 2017")):
            cells = []
            for _, _, _, _, byf in rows_tex:
                m, n = byf.get(fam, (None, 0))
                cells.append(f"${m:.3f}$\\,{{\\scriptsize({n})}}" if n else "--")
            print(f"{lab} & " + " & ".join(cells) + r" \\")
        print("all & " + " & ".join(f"${m:.3f}$" for _, _, m, _, _ in rows_tex) + r" \\")
        print("instances & " + " & ".join(f"{n}" for _, n, _, _, _ in rows_tex) + r" \\")
        print("median $<0.5$ & " + " & ".join(f"{low}" for _, _, _, low, _ in rows_tex) + r" \\")


if __name__ == "__main__":
    main()
