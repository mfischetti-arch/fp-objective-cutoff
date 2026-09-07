#!/usr/bin/env python3
"""I numeri di Sezione 6 del paper scritti a mano nel testo (paragrafo «The LP
recovery improves on the test where the cutoff is tight»): split miste/pure di E1,
confronto FGL_0.5 contro check_0.5 sui due gruppi, mediane di guadagni e perdite,
split esplorativo per taglia (mediana dei nonzeri) e le mediane dei nonzeri di E1 e
delle 463 istanze citate in «What this does not show».

Input (tutti in fpc/): results_fact.txt (campagna fattoriale), inst_wide.txt (n,
ncons, nnz delle 463 istanze), fact_presolved.txt = la riga «presolved problem has
... variables (b bin, i int, c cont)» di SCIP per il braccio none_- (bare) al seme 0,
estratta il 04/09/2026 dai log per run archiviati sul cluster
(~/archive/fpc_scip_out_sets_2026-09-03.tgz, cartella fpc/out/fact/) con
    tar xzf <tgz> --wildcards "fpc/out/fact/*__bare_s0.log"
    grep -H -m1 "presolved problem has .* variables" fpc/out/fact/*.log
«Mista» = almeno una variabile continua DOPO il presolve (c > 0). Controllo
incrociato facoltativo con fact_ncont.txt (campo ncont della riga fp_exit del
completamento: ncont > 0 se e solo se un LP di completamento e' stato costruito).

Uso: python chk_mixed.py [results_fact.txt]
"""
import os, re, statistics as st, sys
from scipy.stats import binomtest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import agg_fact as A

A_ARM, B_ARM = "rec50_f", "rec50"          # FGL_0.5 contro check_0.5
res = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "results_fact.txt")
runs, pilot, notes, below, dropped = A.load(res)
insts = A.complete_instances(runs, 5)[0]
E1 = [i for i in insts if pilot.get(i)]

cont, gint = {}, {}
for ln in open(os.path.join(here, "fact_presolved.txt")):
    m = re.match(r".*/(.+?)__bare_s0\.log:presolved problem has (\d+) variables "
                 r"\((\d+) bin, (\d+) int, (\d+) cont\)", ln)
    if m:
        cont[m.group(1)] = int(m.group(5))
        gint[m.group(1)] = int(m.group(4))
missing = [i for i in E1 if i not in cont]
assert not missing, f"riga di presolve mancante per {missing}"
mixed = [i for i in E1 if cont[i] > 0]
pure = [i for i in E1 if cont[i] == 0]

nnz = {}
for ln in open(os.path.join(here, "inst_wide.txt")):
    if ln.startswith("#"):
        continue
    f = ln.rstrip("\n").split("\t")
    nnz[f[2].split("/")[-1].replace(".mps.gz", "")] = int(f[5])


def med_gap(i, arm):
    return st.median(runs[i][(arm, s)]["gap"] for s in range(5))


def paired(S, a=A_ARM, b=B_ARM):
    """better/tie/worse per a contro b, con i guadagni e le perdite in punti di gap."""
    b_arm = b
    b = t = w = 0
    gains, losses = [], []
    for i in S:
        d = med_gap(i, b_arm) - med_gap(i, a)
        if abs(d) < 1e-6:
            t += 1
        elif d > 0:
            b += 1; gains.append(d)
        else:
            w += 1; losses.append(-d)
    p = binomtest(b, b + w, 0.5).pvalue if b + w else float("nan")
    return b, t, w, p, gains, losses


def fmt(v):
    return f"mediana {st.median(v):.1f}, massimo {max(v):.1f}" if v else "--"


print(f"E1: {len(E1)} istanze; miste (continue dopo il presolve): {len(mixed)}; pure: {len(pure)}")
for name, S in (("miste", mixed), ("pure", pure), ("tutte E1", E1)):
    b, t, w, p, g, l = paired(S)
    print(f"  {name:9s} FGL_0.5 vs check_0.5: {b}-{t}-{w}  (sign test p = {p:.4g}); "
          f"guadagni {fmt(g)}; perdite {fmt(l)}")
b, t, w, p, g, l = paired(E1)
print(f"  perdite su miste: {sum(1 for i in mixed if med_gap(i, B_ARM) - med_gap(i, A_ARM) < -1e-6)} di {w}")
# Chi fa il lavoro su ciascuna classe: il test da solo contro il cutoff nudo, e FGL contro il
# cutoff nudo (sulle pure FGL e check sono lo stesso codice: niente LP di completamento).
for name, S in (("miste", mixed), ("pure", pure)):
    for lab, a in (("check_0.5", "rec50"), ("FGL_0.5", "rec50_f")):
        b, t, w, p, _, _ = paired(S, a, "cut50")
        print(f"  {name:9s} {lab} vs none_0.5: {b}-{t}-{w}  (sign test p = {p:.4g})")
gi = [i for i in E1 if gint[i] > 0]
b, t, w, p, _, _ = paired(gi)
print(f"  istanze di E1 con generali intere dopo il presolve: {len(gi)} "
      f"({sum(1 for i in gi if cont[i] > 0)} anche con continue); FGL_0.5 vs check_0.5 su di esse {b}-{t}-{w}")

m = st.median(nnz[i] for i in E1)
small = [i for i in E1 if nnz[i] <= m]
large = [i for i in E1 if nnz[i] > m]
for name, S in (("meta' piccola", small), ("meta' grande", large)):
    b, t, w, p, _, _ = paired(S)
    print(f"  split per taglia, {name} ({len(S)}): {b}-{t}-{w} (p = {p:.4g})")
print(f"nonzeri: mediana su E1 {m:,.0f}; su tutte le {len(nnz)} istanze {st.median(nnz.values()):,.0f}")

nc_path = os.path.join(here, "fact_ncont.txt")
if os.path.exists(nc_path):
    nc = {}
    for ln in open(nc_path):
        mm = re.match(r".*/(.+?)__(\w+?)_s(\d)\.log:.*ncont=(\d+)", ln)
        if mm:
            nc[mm.group(1)] = max(nc.get(mm.group(1), 0), int(mm.group(4)))
    agree = sum(1 for i in E1 if i in nc and (nc[i] > 0) == (cont[i] > 0))
    print(f"controllo con fact_ncont.txt: {agree} istanze di E1 concordi su {sum(1 for i in E1 if i in nc)} coperte")
