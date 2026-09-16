#!/usr/bin/env python3
"""Q2 del referee MPC: il vantaggio del test del punto arrotondato senza cutoff
(recbare su bare, E1) sparisce con la proiezione pura, alpha = 0?

    python3 agg_alpha0.py                       # results_alpha0.txt contro results_fact.txt
    python3 agg_alpha0.py --a0 results_alpha0.txt --fact results_fact.txt --ncont fact_ncont.txt

Le definizioni (gap finale gamma, mediana per istanza sui 5 semi, 100 se
nessuna soluzione, test dei segni esatto) sono importate da agg_fact.py; il
confronto appaiato e la mediana della differenza sulle non pari sono quelli di
mk_tabs_fact.paired (B - A in punti di gap: positiva = A migliore).

E1 = le istanze con griglia completa in results_fact.txt in cui il pilota trova
una soluzione (le stesse di mk_tabs_fact.py); nella campagna alpha0 entrano
quelle con i 2 bracci x 5 semi completi, e le mancanti si dichiarano.
Split misto/puro da fact_ncont.txt: ncont > 0 dopo presolve = mista.
"""
import argparse
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agg_fact as A  # noqa: E402

SEEDS = 5
TOL = 1e-6


def load_ncont(path):
    nc = {}
    for ln in open(path, errors="replace"):
        m = re.search(r"/([^/]+)__[^/]+\.log:.*ncont=(\d+)", ln)
        if m:
            nc.setdefault(m.group(1), int(m.group(2)))
    return nc


def inst_med(runs, i, arm, key="gap"):
    v = [runs[i][(arm, s)][key] for s in range(SEEDS) if (arm, s) in runs[i]]
    return A.med(v)


def paired_inst(sl, rx, x, ry, y, key="gap"):
    """per istanza: mediana sui semi di x (in rx) contro y (in ry).
    Ritorna better/tie/worse di x, la mediana di (y - x) sulle non pari, e la lista."""
    b = t = w = 0
    diffs = []
    for i in sl:
        mx = inst_med(rx, i, x, key)
        my = inst_med(ry, i, y, key)
        if mx is None or my is None:
            continue
        if mx < my - TOL:
            b += 1; diffs.append(my - mx)
        elif mx > my + TOL:
            w += 1; diffs.append(my - mx)
        else:
            t += 1
    return b, t, w, (A.med(diffs) if diffs else None), diffs


def paired_run(sl, rx, x, ry, y, key="gap"):
    b = t = w = 0
    for i in sl:
        for s in range(SEEDS):
            if (x, s) not in rx[i] or (y, s) not in ry[i]:
                continue
            gx = rx[i][(x, s)][key]; gy = ry[i][(y, s)][key]
            if gx < gy - TOL: b += 1
            elif gx > gy + TOL: w += 1
            else: t += 1
    return b, t, w


def found(sl, runs, arm):
    wi = sum(1 for i in sl if any((arm, s) in runs[i] and runs[i][(arm, s)]["primal"] is not None
                                  for s in range(SEEDS)))
    wr = sum(1 for i in sl for s in range(SEEDS) if (arm, s) in runs[i] and runs[i][(arm, s)]["primal"] is not None)
    return wi, wr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a0", default=os.path.join(HERE, "results_alpha0.txt"))
    ap.add_argument("--fact", default=os.path.join(HERE, "results_fact.txt"))
    ap.add_argument("--ncont", default=os.path.join(HERE, "fact_ncont.txt"))
    a = ap.parse_args()

    rf, pilot, _, below_f, _ = A.load(a.fact)
    r0, _, _, below_0, dropped_0 = A.load(a.a0)
    if below_f or below_0:
        sys.exit("FATALE: primale sotto z_LP (fact %d, alpha0 %d)" % (len(below_f), len(below_0)))
    insts, _ = A.complete_instances(rf, SEEDS)
    E1 = [i for i in insts if pilot.get(i)]
    arms0 = ["bare", "recbare"]
    full0 = [i for i in E1 if all((x, s) in r0.get(i, {}) for x in arms0 for s in range(SEEDS))]
    missing = [i for i in E1 if i not in full0]
    extra = [i for i in r0 if i not in E1]
    nc = load_ncont(a.ncont)
    mixed = [i for i in full0 if nc.get(i, 0) > 0]
    pure = [i for i in full0 if nc.get(i, 0) == 0]
    nonc = [i for i in full0 if i not in nc]

    out = []
    p = out.append
    p("# Q2: alpha = 0 (results_alpha0.txt) contro alpha di default (results_fact.txt), E1")
    p("- E1 (griglia completa in results_fact.txt, pilot trova una soluzione): %d istanze" % len(E1))
    p("- alpha0: istanze con 2 bracci x 5 semi completi: %d; mancanti: %d %s; fuori E1: %d"
      % (len(full0), len(missing), " ".join(missing[:20]), len(extra)))
    p("- run in results_alpha0.txt: %d; righe scartate: %s" % (sum(len(v) for v in r0.values()), dict(dropped_0) or "nessuna"))
    p("- split: miste (ncont > 0) %d, pure %d, senza ncont %d %s" % (len(mixed), len(pure), len(nonc), " ".join(nonc)))
    tl_ok = all(r0[i][(x, s)]["tl"] == rf[i][(x, s)]["tl"] and r0[i][(x, s)]["zlp"] == rf[i][(x, s)]["zlp"]
                for i in full0 for x in arms0 for s in range(SEEDS))
    p("- tl e z_LP identici alla campagna su tutte le istanze analizzate: %s" % tl_ok)
    p("")

    # ------------------------------------------------ T1: per braccio, alpha 0 vs default
    p("## T1 -- per braccio, E1 (%d istanze): trovate, gap mediano, giri e iterazioni LP" % len(full0))
    p("| braccio | alpha | inst. con sol. | run con sol. | gap mediano | giri mediani/run | LP iter mediane/run |")
    p("|---|---|---|---|---|---|---|")
    for arm in arms0:
        for lab, R in (("default", rf), ("0", r0)):
            recs = [R[i][(arm, s)] for i in full0 for s in range(SEEDS)]
            wi, wr = found(full0, R, arm)
            g = A.med([inst_med(R, i, arm) for i in full0])
            p("| `%s` | %s | %d/%d | %d/%d | %.2f | %.0f | %.0f |"
              % (arm, lab, wi, len(full0), wr, len(recs), g, A.med([r["nloops"] for r in recs]),
                 A.med([r["nlpiter"] for r in recs])))
    p("")

    # ------------------------------------------------ T2: confronti appaiati per istanza
    comps = [("recbare", r0, "bare", r0, "recbare vs bare, alpha = 0 (la domanda del referee)"),
             ("recbare", rf, "bare", rf, "recbare vs bare, alpha default (il paper, ricalcolato sulle stesse istanze)"),
             ("bare", r0, "bare", rf, "bare: alpha = 0 vs default"),
             ("recbare", r0, "recbare", rf, "recbare: alpha = 0 vs default")]
    for sname, sl in (("E1", full0), ("E1 miste", mixed), ("E1 pure", pure)):
        p("## T2 -- %s (%d istanze): appaiato per ISTANZA sul gap finale (mediana dei 5 semi), test dei segni esatto" % (sname, len(sl)))
        p("| confronto X vs Y | X meglio / pari / X peggio | p (segni) | mediana diff. (Y - X) sulle non pari | per run: meglio / pari / peggio |")
        p("|---|---|---|---|---|")
        for x, rx, y, ry, lab in comps:
            b, t, w, md, _ = paired_inst(sl, rx, x, ry, y)
            rb, rt, rw = paired_run(sl, rx, x, ry, y)
            p("| %s | %d / %d / %d | %.4f | %s | %d / %d / %d |"
              % (lab, b, t, w, A.sign_test(b, w), ("%+.1f" % md) if md is not None else "--", rb, rt, rw))
        p("")

    # --------------------------------------------- T3: found/not found a alpha = 0
    p("## T3 -- E1, alpha = 0: trovata/non trovata per run, recbare vs bare (quattro celle)")
    Aa = B = C = D = 0; IA = IB = 0
    for i in full0:
        fx = fy = False
        for s in range(SEEDS):
            px = r0[i][("recbare", s)]["primal"] is not None; py = r0[i][("bare", s)]["primal"] is not None
            fx |= px; fy |= py
            if px and not py: Aa += 1
            elif py and not px: B += 1
            elif px and py: C += 1
            else: D += 1
        if fx and not fy: IA += 1
        if fy and not fx: IB += 1
    p("| solo recbare | solo bare | entrambi | nessuno | inst. solo recbare | inst. solo bare |")
    p("|---|---|---|---|---|---|")
    p("| %d | %d | %d | %d | %d | %d |" % (Aa, B, C, D, IA, IB))
    p("")

    # ------------------------- T4: le istanze dove recbare batte bare, a alpha 0 e/o default
    p("## T4 -- istanze in cui recbare batte bare (gap mediano), a alpha = 0 e/o a default")
    win0 = {}; wind = {}
    for i in full0:
        g0b, g0r = inst_med(r0, i, "bare"), inst_med(r0, i, "recbare")
        gdb, gdr = inst_med(rf, i, "bare"), inst_med(rf, i, "recbare")
        if g0r < g0b - TOL: win0[i] = g0b - g0r
        if gdr < gdb - TOL: wind[i] = gdb - gdr
    both = sorted(set(win0) & set(wind)); only0 = sorted(set(win0) - set(wind)); onlyd = sorted(set(wind) - set(win0))
    p("- vince in entrambe: %d; solo a alpha = 0: %d; solo a default: %d" % (len(both), len(only0), len(onlyd)))
    p("| istanza | mista | diff. a alpha = 0 | diff. a default |")
    p("|---|---|---|---|")
    for i in sorted(set(win0) | set(wind)):
        p("| %s | %s | %s | %s |" % (i, "si" if nc.get(i, 0) > 0 else "no",
                                     ("%+.1f" % win0[i]) if i in win0 else "--", ("%+.1f" % wind[i]) if i in wind else "--"))
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
