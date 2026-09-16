#!/usr/bin/env python3
"""M14 del referee MPC: quanto tempo di parete costa il completamento su clone?

    python3 agg_lpft.py                     # results_lpft.txt (scip_f6) contro results_fact.txt (scip_f5)
    python3 agg_lpft.py --lpft results_lpft.txt --fact results_fact.txt --ncont fact_ncont.txt

Legge i due campi in coda alla riga RES| di job31_lpft.sh, lpfixtime= (tutto il
lavoro del completamento, giro per giro) e lpfixbuild= (costruzione del clone),
e li mette a rapporto con time= (il Solving Time del run). Tutto il resto (gap,
primal, contatori lpfix) passa da agg_fact.load, cosi' le definizioni sono le
stesse del paper. Split misto/puro da fact_ncont.txt (ncont > 0 = mista): sulle
pure il clone non viene costruito e la quota deve essere ~0.
"""
import argparse
import os
import re
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agg_fact as A  # noqa: E402

SEEDS = 5
ARMS = ["recbare_f", "rec50_f", "rec95_f"]


def load_extra(path):
    ex = {}
    for ln in open(path, errors="replace"):
        if not ln.startswith("RES|"):
            continue
        p = ln.rstrip("\n").split("|")
        d = dict(f.split("=", 1) for f in p[3:] if "=" in f)
        if "lpfixtime" in d and "seed" in d:
            ex[(p[1], p[2], int(d["seed"]))] = (float(d["lpfixtime"]), float(d.get("lpfixbuild", 0.0)))
    return ex


def load_ncont(path):
    nc = {}
    for ln in open(path, errors="replace"):
        m = re.search(r"/([^/]+)__[^/]+\.log:.*ncont=(\d+)", ln)
        if m:
            nc.setdefault(m.group(1), int(m.group(2)))
    return nc


def q(v, k):
    return st.quantiles(v, n=4)[k] if len(v) >= 2 else v[0]


def fmt(v):
    """mediana [q1, q3] max, in percento"""
    if not v:
        return "--"
    return "%.1f [%.1f, %.1f] %.1f" % (st.median(v), q(v, 0), q(v, 2), max(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lpft", default=os.path.join(HERE, "results_lpft.txt"))
    ap.add_argument("--fact", default=os.path.join(HERE, "results_fact.txt"))
    ap.add_argument("--ncont", default=os.path.join(HERE, "fact_ncont.txt"))
    a = ap.parse_args()

    rf, pilot, _, below_f, _ = A.load(a.fact)
    rl, _, _, below_l, dropped = A.load(a.lpft)
    if below_f or below_l:
        sys.exit("FATALE: primale sotto z_LP (fact %d, lpft %d)" % (len(below_f), len(below_l)))
    ex = load_extra(a.lpft)
    insts, _ = A.complete_instances(rf, SEEDS)
    E1 = [i for i in insts if pilot.get(i)]
    full = [i for i in E1 if all((x, s) in rl.get(i, {}) and (i, x, s) in ex for x in ARMS for s in range(SEEDS))]
    missing = [i for i in E1 if i not in full]
    nc = load_ncont(a.ncont)
    mixed = [i for i in full if nc.get(i, 0) > 0]
    pure = [i for i in full if nc.get(i, 0) == 0]

    out = []
    p = out.append
    p("# M14: costo del completamento (results_lpft.txt, scip_f6) -- E1")
    p("- E1: %d istanze; con i 3 bracci x 5 semi completi e il campo lpfixtime: %d; mancanti: %d %s"
      % (len(E1), len(full), len(missing), " ".join(missing[:20])))
    p("- run: %d; righe scartate: %s" % (sum(len(v) for v in rl.values()), dict(dropped) or "nessuna"))
    p("- split: miste (ncont > 0) %d, pure %d" % (len(mixed), len(pure)))
    p("")

    def share(i, arm, s):
        r = rl[i][(arm, s)]
        return 100.0 * ex[(i, arm, s)][0] / r["t"] if r["t"] > 0 else 0.0

    def share_build(i, arm, s):
        r = rl[i][(arm, s)]
        return 100.0 * ex[(i, arm, s)][1] / r["t"] if r["t"] > 0 else 0.0

    # ------------------------------------------------------- T1: quota per braccio
    for sname, sl in (("E1", full), ("E1 miste", mixed), ("E1 pure", pure)):
        if not sl:
            continue
        p("## T1 -- %s (%d istanze): quota di tempo di parete del completamento, lpfixtime / Solving Time, in %%" % (sname, len(sl)))
        p("| braccio | per run: mediana [q1, q3] max | per istanza (mediana sui semi): mediana [q1, q3] max | run con lpfix > 0 | ms per LP di completamento (mediana per run) | quota costruzione clone: mediana, max |")
        p("|---|---|---|---|---|---|")
        for arm in ARMS:
            per_run = [share(i, arm, s) for i in sl for s in range(SEEDS)]
            per_inst = [st.median([share(i, arm, s) for s in range(SEEDS)]) for i in sl]
            nz = sum(1 for i in sl for s in range(SEEDS) if rl[i][(arm, s)]["lpfix"] > 0)
            ms = [1000.0 * ex[(i, arm, s)][0] / rl[i][(arm, s)]["lpfix"]
                  for i in sl for s in range(SEEDS) if rl[i][(arm, s)]["lpfix"] > 0]
            bld = [share_build(i, arm, s) for i in sl for s in range(SEEDS)]
            p("| `%s` | %s | %s | %d/%d | %s | %.2f, %.1f |"
              % (arm, fmt(per_run), fmt(per_inst), nz, len(per_run), ("%.1f" % st.median(ms)) if ms else "--",
                 st.median(bld), max(bld)))
        p("")

    # ------------------------------------------ T2: totale aggregato (somme di tempo)
    p("## T2 -- E1 miste: tempo totale (somma sui run) del completamento contro il Solving Time totale")
    p("| braccio | sum lpfixtime (s) | sum lpfixbuild (s) | sum Solving Time (s) | quota aggregata (%) | LP di completamento | ms/LP aggregato |")
    p("|---|---|---|---|---|---|---|")
    for arm in ARMS:
        lt = sum(ex[(i, arm, s)][0] for i in mixed for s in range(SEEDS))
        lb = sum(ex[(i, arm, s)][1] for i in mixed for s in range(SEEDS))
        tt = sum(rl[i][(arm, s)]["t"] for i in mixed for s in range(SEEDS))
        nl = sum(rl[i][(arm, s)]["lpfix"] for i in mixed for s in range(SEEDS))
        p("| `%s` | %.1f | %.1f | %.1f | %.2f | %d | %.1f |" % (arm, lt, lb, tt, 100.0 * lt / tt if tt else 0, nl, 1000.0 * lt / nl if nl else 0))
    p("")

    # ---------------------- T3: le istanze piu' care (mediana sui semi della quota)
    p("## T3 -- le 10 istanze con la quota mediana (sui semi) piu' alta, per braccio")
    p("| braccio | istanza | quota mediana (%) | LP di completamento (mediana) | giri (mediana) | TL |")
    p("|---|---|---|---|---|---|")
    for arm in ARMS:
        rows = sorted(((st.median([share(i, arm, s) for s in range(SEEDS)]), i) for i in full), reverse=True)[:10]
        for v, i in rows:
            p("| `%s` | %s | %.1f | %.0f | %.0f | %.0f |"
              % (arm, i, v, st.median([rl[i][(arm, s)]["lpfix"] for s in range(SEEDS)]),
                 st.median([rl[i][(arm, s)]["nloops"] for s in range(SEEDS)]), rl[i][(arm, 0)]["tl"]))
    p("")

    # ------------------- T4: coerenza con results_fact.txt (stesso braccio, scip_f5)
    p("## T4 -- coerenza con la campagna (scip_f5): stesso braccio, gap mediano e trovate, E1 (%d istanze)" % len(full))
    p("| braccio | binario | inst. con sol. | run con sol. | gap mediano | giri mediani/run | LP compl. (somma) | accettati | infeasible | per istanza gap: f6 meglio / pari / peggio di f5 |")
    p("|---|---|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        for lab, R in (("scip_f5 (fact)", rf), ("scip_f6 (lpft)", rl)):
            recs = [R[i][(arm, s)] for i in full for s in range(SEEDS)]
            wi = sum(1 for i in full if any(R[i][(arm, s)]["primal"] is not None for s in range(SEEDS)))
            wr = sum(1 for r in recs if r["primal"] is not None)
            g = A.med([A.med([R[i][(arm, s)]["gap"] for s in range(SEEDS)]) for i in full])
            b = t = w = 0
            if R is rl:
                for i in full:
                    g6 = A.med([rl[i][(arm, s)]["gap"] for s in range(SEEDS)]); g5 = A.med([rf[i][(arm, s)]["gap"] for s in range(SEEDS)])
                    if g6 < g5 - 1e-6: b += 1
                    elif g6 > g5 + 1e-6: w += 1
                    else: t += 1
            p("| `%s` | %s | %d/%d | %d/%d | %.2f | %.0f | %d | %d | %d | %s |"
              % (arm, lab, wi, len(full), wr, len(recs), g, A.med([r["nloops"] for r in recs]),
                 sum(r["lpfix"] for r in recs), sum(r["lpfixfeas"] for r in recs), sum(r["lpfixinf"] for r in recs),
                 ("%d / %d / %d" % (b, t, w)) if R is rl else "--"))
    p("")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
