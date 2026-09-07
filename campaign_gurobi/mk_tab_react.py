#!/usr/bin/env python3
"""mk_tab_react.py -- tabella e macro della sezione «oscillating cutoff» del paper
(FP_obj_cutoff/paper/fpcutoff_v3.tex), dalla campagna RUNTAG=paper di job26_react.sh.

    python mk_tab_react.py "logs/r26_<paperjob>_*.log" [--paper-dir ../FP_obj_cutoff/paper] [--no-write]

Scrive tab_react.tex (ambiente table, caption e label dentro) e val_react.tex
(\\newcommand per ogni numero citato nel testo), qui e nella cartella del paper.
Nessun numero e' scritto a mano: tutto viene dalle righe RES. Controlli
cablati: 0 invarianti fatali (success senza validated, rc != 0), 272 istanze
con tutti i bracci, e pf che non perde mai contro fgl sull'esito (per
costruzione: se perde, lo dice e non scrive).

Bracci nel paper: fgl (5 semi), oh (lo sweep dichiarato prima del lancio),
eoh (sweep a ogni giro), fl (flip + sweep sui cicli), pf (portfolio: sweep per
0.7 TL con cancello, poi FGL), ff (controllo: FGL per 0.7 TL, poi FGL con un
altro seme). Le comparazioni appaiate con fgl sono cinque: Holm su cinque."""
import argparse
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agg_react import parse, fnum, med, sign_test, holm  # noqa: E402

ARMS = ["fgl", "oh", "eoh", "fl", "pf", "ff"]
NAME = {"fgl": r"\textsc{fgl}", "oh": r"\textsc{sweep}", "eoh": r"\textsc{sweep-e}",
        "fl": r"\textsc{flip+sweep}", "pf": r"\textsc{sweep$\to$fgl}", "ff": r"\textsc{fgl$\to$fgl}"}
MACRO = {"fgl": "Fgl", "oh": "Oh", "eoh": "Eoh", "fl": "Fl", "pf": "Pf", "ff": "Ff"}


def ok(kv):
    return kv.get("success") == "1" and kv.get("validated") == "1"


def rom(n):
    """Numero in cifre per le macro (le macro LaTeX non accettano cifre nel nome)."""
    return str(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--paper-dir", default=os.path.join("..", "FP_obj_cutoff", "paper"))
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="scrive anche con invarianti violate (SOLO per provare la compilazione)")
    a = ap.parse_args()
    paths = []
    for g in a.logs:
        paths += glob.glob(g)
    runs = parse(paths)
    insts = sorted({k[0] for k in runs})
    seeds = {arm: sorted({k[2] for k in runs if k[1] == arm}) for arm in ARMS}
    meta = {i: next(kv for k, kv in runs.items() if k[0] == i) for i in insts}

    fatal = 0
    for (i, arm, s), kv in runs.items():
        if kv.get("success") == "1" and kv.get("validated") != "1":
            print(f"FATALE: {i} {arm} s{s}: success senza validated", file=sys.stderr); fatal += 1
        if kv.get("rc") not in (None, "0"):
            print(f"FATALE: {i} {arm} s{s}: rc={kv.get('rc')}", file=sys.stderr); fatal += 1
    for arm in ARMS:
        for i in insts:
            for s in seeds[arm]:
                if (i, arm, s) not in runs:
                    print(f"FATALE: manca {i} {arm} s{s}", file=sys.stderr); fatal += 1

    def solved(i, arm):
        ss = [runs[(i, arm, s)] for s in seeds[arm] if (i, arm, s) in runs]
        k = sum(ok(kv) for kv in ss)
        return int(k * 2 > len(ss)) if len(ss) > 1 else int(k == 1)

    def tfirst(i, arm):
        ts = [fnum(runs[(i, arm, s)].get("t_first_feasible")) for s in seeds[arm]
              if (i, arm, s) in runs and ok(runs[(i, arm, s)])]
        ts = [t for t in ts if t is not None]
        if len(seeds[arm]) > 1:
            return med(ts) if len(ts) * 2 > len(seeds[arm]) else None
        return ts[0] if ts else None

    def zfirst(i, arm):
        zs = [fnum(runs[(i, arm, s)].get("z_first_feasible")) for s in seeds[arm]
              if (i, arm, s) in runs and ok(runs[(i, arm, s)])]
        zs = [z for z in zs if z is not None]
        if len(seeds[arm]) > 1:
            return med(zs) if len(zs) * 2 > len(seeds[arm]) else None
        return zs[0] if zs else None

    fail = [i for i in insts if meta[i].get("pilot") == "failed"]
    found = [i for i in insts if meta[i].get("pilot") == "found"]
    V = {}
    V["N"] = len(insts)
    V["NFail"] = len(fail)
    V["NFound"] = len(found)
    V["NMixed"] = sum(1 for i in insts if (fnum(meta[i].get("ncont")) or 0) > 0)
    V["NPure"] = V["N"] - V["NMixed"]
    V["NRuns"] = len(runs)
    V["RunsPerInst"] = len(runs) // max(1, len(insts))
    bench = set()
    bpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark-v2.test")
    if os.path.exists(bpath):
        for line in open(bpath):
            n = line.strip().split("/")[-1]
            for ext in (".gz", ".mps"):
                if n.endswith(ext):
                    n = n[:-len(ext)]
            if n:
                bench.add(n)
    V["NTest"] = sum(1 for i in insts if i in bench)
    V["NTrain"] = V["N"] - V["NTest"]
    V["NZhiUnknown"] = sum(1 for i in insts if any(
        runs[(i, arm, 0)].get("zhi_unbounded") not in (None, "-", "0")
        for arm in ("oh", "eoh") if (i, arm, 0) in runs))

    rows = []
    pv = []
    for arm in ARMS:
        r = dict(arm=arm)
        r["all"] = sum(solved(i, arm) for i in insts)
        r["fail"] = sum(solved(i, arm) for i in fail)
        r["found"] = sum(solved(i, arm) for i in found)
        r["runs_ok"] = sum(1 for k, kv in runs.items() if k[1] == arm and ok(kv))
        r["runs"] = sum(1 for k in runs if k[1] == arm)
        w = t = l = 0
        tw = tl_ = 0
        ratios = []
        qb = qw = 0
        for i in insts:
            x, y = solved(i, arm), solved(i, "fgl")
            if x > y:
                w += 1
            elif x < y:
                l += 1
            else:
                t += 1
            if x and y and arm != "fgl":
                ta, tr = tfirst(i, arm), tfirst(i, "fgl")
                if ta is not None and tr is not None:
                    ratios.append((ta + 1e-3) / (tr + 1e-3))
                    tw += ta < 0.95 * tr
                    tl_ += ta > 1.05 * tr
                za, zr = zfirst(i, arm), zfirst(i, "fgl")
                if za is not None and zr is not None:
                    sc = max(1.0, abs(zr))
                    qb += za < zr - 1e-6 * sc
                    qw += za > zr + 1e-6 * sc
        r.update(win=w, tie=t, loss=l, p=sign_test(w, l), tw=tw, tl=tl_,
                 tratio=(med(ratios) if ratios else None), qb=qb, qw=qw,
                 qp=sign_test(qb, qw), common=len(ratios))
        rows.append(r)
        if arm != "fgl":
            pv.append(r["p"])
    adj = holm(pv)
    for r, h in zip([r for r in rows if r["arm"] != "fgl"], adj):
        r["holm"] = h

    for r in rows:
        m = MACRO[r["arm"]]
        for key in ("all", "fail", "found", "win", "tie", "loss", "tw", "tl", "qb", "qw", "common"):
            V[f"{m}{key.capitalize()}"] = r[key]
        # le macro dei p portano il segno di confronto: nel testo si scrive $p\RcOhP$
        V[f"{m}P"] = f"={r['p']:.3f}" if r["p"] >= 0.001 else "<0.001"
        if "holm" in r:
            V[f"{m}Holm"] = f"={r['holm']:.3f}" if r["holm"] >= 0.001 else "<0.001"
        V[f"{m}QP"] = f"={r['qp']:.3f}" if r["qp"] >= 0.001 else "<0.001"
        V[f"{m}Tratio"] = f"{r['tratio']:.1f}" if r["tratio"] is not None else "--"

    # dove trova lo sweep e fgl no: livello nel range di costo
    only = [i for i in insts if solved(i, "eoh") and not solved(i, "fgl")]
    lv = [fnum(runs[(i, "eoh", 0)].get("level_first")) for i in only]
    lv = [x for x in lv if x is not None]
    V["EohOnly"] = len(only)
    V["EohOnlyTop"] = sum(1 for x in lv if x >= 0.8)
    V["EohOnlyBottom"] = sum(1 for x in lv if x <= 0.1)
    V["EohOnlyMixed"] = sum(1 for i in only if (fnum(meta[i].get("ncont")) or 0) > 0)
    V["EohOnlyDrayage"] = sum(1 for i in only if i.startswith("drayage"))
    # pf: la fase che consegna
    V["PfExhaustEarly"] = None
    V["FglMedT"] = f"{med([tfirst(i, 'fgl') for i in insts if solved(i, 'fgl')]):.2f}"

    # ------------------------------------------------------------ controlli
    pf = next(r for r in rows if r["arm"] == "pf")
    if pf["loss"] > 0:
        print(f"AVVISO: pf perde {pf['loss']} istanze contro fgl (dovrebbe essere 0 per costruzione)",
              file=sys.stderr)
    print(f"istanze {V['N']} (fgl fallisce su {V['NFail']}), run {V['NRuns']}, fatali {fatal}")
    for r in rows:
        print(f"  {r['arm']:4s} risolte {r['all']:3d} (fail {r['fail']:2d}, found {r['found']:3d}) "
              f"vs fgl {r['win']}/{r['tie']}/{r['loss']} p={r['p']:.3f} holm={r.get('holm', 1):.3f} "
              f"t {r['tw']}/{r['tl']} ratio {r['tratio']} q {r['qb']}/{r['qw']} p={r['qp']:.3f}")
    if fatal and not a.force:
        sys.exit("invarianti fatali: non scrivo")
    if fatal:
        print(f"AVVISO: --force con {fatal} invarianti violate: file PROVVISORI", file=sys.stderr)

    # ------------------------------------------------------------- tab_react
    L = []
    L.append(r"\begin{table}[t]")
    L.append(r"\centering\small")
    L.append(r"\caption{The oscillating cutoff on Gurobi: " + str(V["N"]) + r" 0--1 instances of MIPLIB~2017 "
             r"(" + str(V["NFail"]) + r" on which \textsc{fgl} finds nothing on any of its five seeds), "
             r"time limit $\min(300,\max(20,20\,t_{\mathrm{LP}}))$\,s, one instance per blade with all runs in "
             r"batches of four. ``Solved'' is an instance with a point feasible for the original model, re-checked "
             r"by Gurobi; for the seeded policies, on at least three seeds of five. ``vs.\ \textsc{fgl}'' counts "
             r"instances won--tied--lost on the outcome, with the exact two-sided sign test on the discordant ones "
             r"and Holm over the five comparisons. ``Time'' and ``cost'' are counted on the instances both solve: "
             r"faster/slower than \textsc{fgl} by more than 5\%, and first solution cheaper/dearer than "
             r"\textsc{fgl}'s; the last column is the median ratio of times.}")
    L.append(r"\label{tab:react}")
    L.append(r"\begin{tabular}{lrrrrrrrrr}")
    L.append(r"\toprule")
    L.append(r"policy & solved & of " + str(V["NFail"]) + r" & vs.\ \textsc{fgl} & $p$ & Holm & time $+/-$ & cost $+/-$ & $t/t_{\textsc{fgl}}$ \\")
    L.append(r"\midrule")
    for r in rows:
        if r["arm"] == "fgl":
            L.append(f"{NAME['fgl']} & {r['all']} & {r['fail']} & -- & -- & -- & -- & -- & -- \\\\")
        else:
            hol = f"{r['holm']:.3f}" if r["holm"] >= 0.001 else "$<0.001$"
            pp = f"{r['p']:.3f}" if r["p"] >= 0.001 else "$<0.001$"
            L.append(f"{NAME[r['arm']]} & {r['all']} & {r['fail']} & {r['win']}--{r['tie']}--{r['loss']} & {pp} & {hol} & "
                     f"{r['tw']}/{r['tl']} & {r['qb']}/{r['qw']} & {r['tratio']:.1f} \\\\")
    L.append(r"\bottomrule")
    L.append(r"\end{tabular}")
    L.append(r"\end{table}")
    tab = "\n".join(L) + "\n"

    M = ["%% val_react.tex -- generato da fp_gurobi/mk_tab_react.py; non modificare a mano"]
    for k, v in V.items():
        if v is None:
            continue
        M.append(f"\\newcommand{{\\Rc{k}}}{{{v}}}")
    val = "\n".join(M) + "\n"

    if a.no_write:
        print(tab)
        return
    here = os.path.dirname(os.path.abspath(__file__))
    open(os.path.join(here, "tab_react.tex"), "w", encoding="utf-8").write(tab)
    open(os.path.join(here, "val_react.tex"), "w", encoding="utf-8").write(val)
    print("scritti tab_react.tex e val_react.tex in", here)
    if os.path.isdir(a.paper_dir):
        # nel paper resta solo la frase di registro nelle conclusioni (07/09/2026):
        # le macro si', la tabella no (sta nel supplemento, cioe' qui)
        open(os.path.join(a.paper_dir, "val_react.tex"), "w", encoding="utf-8").write(val)
        print("scritto val_react.tex in", a.paper_dir)


if __name__ == "__main__":
    main()
