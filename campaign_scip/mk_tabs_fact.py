#!/usr/bin/env python3
"""Tabelle LaTeX della campagna FATTORIALE, dai dati grezzi di results_fact.txt.

    python mk_tabs_fact.py                       # scrive in ../paper
    python mk_tabs_fact.py --out /tmp/x          # altrove

Produce, in --out:
    tab_fact_e1.tex     T1 sullo strato E1 (il pilota trova una soluzione)
    tab_fact_e2.tex     T1 sullo strato E2 (il pilota non trova niente)
    tab_fact_paired.tex T2: confronti appaiati per ISTANZA sul gap finale, Holm (solo E1)
    tab_fact_found.tex  T3: found/not-found per run, tutte e quattro le celle, E1 ed E2

Solo il corpo `\\begin{tabular}...\\end{tabular}`: table, caption e label li mette il .tex
a mano. booktabs e' gia' caricato nel preambolo; il corpo del testo (\\footnotesize e simili)
lo decide il .tex.

NIENTE DEFINIZIONI NUOVE. Parsing, strati E1/E2, gamma/gap, primal integral prolungato,
mediana per seme dentro istanza, test dei segni e Holm sono importati da agg_fact.py, cosi'
i numeri di queste tabelle e quelli del report markdown di agg_fact.py coincidono cifra per
cifra (il testo del paper cita entrambi).

I nomi dei bracci sono macro definite nel preambolo del paper. Il disegno e' fattoriale:
tre modi di trattare il punto arrotondato x cinque livelli di cutoff.
    \\armnone{\nocut} \\armnone{0.5}                              nessun trattamento
    \\armchk{\nocut} \\armchk{0.5} \\armchk{0.75} \\armchk{0.9} \\armchk{0.95}   controllo diretto
    \\armfgl{\nocut} \\armfgl{0.5} \\armfgl{0.95}                 postprocessing FGL
    \\armfb{0.5} \\armfbn{0.5}                               col ripiego su c'xhat
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg_fact as A          # noqa: E402  -- le definizioni sono TUTTE le sue

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_RES = os.path.join(HERE, "results_fact.txt")
DEF_OUT = os.path.abspath(os.path.join(HERE, os.pardir, "paper"))

# ------------------------------------------------------------- nomi per il paper
TEX = {"bare": r"\armnone{\nocut}", "cut50": r"\armnone{0.5}",
       "recbare": r"\armchk{\nocut}", "rec50": r"\armchk{0.5}", "rec75": r"\armchk{0.75}",
       "rec90": r"\armchk{0.9}", "rec95": r"\armchk{0.95}",
       "recbare_f": r"\armfgl{\nocut}", "rec50_f": r"\armfgl{0.5}", "rec95_f": r"\armfgl{0.95}",
       "rec50_fb": r"\armfb{0.5}", "cut50_fb": r"\armfbn{0.5}"}

# ordine FATTORIALE: i tre modi di trattare il punto arrotondato, ciascuno a cutoff
# crescente; in coda le due varianti col ripiego su c'xhat.
ORDER = ["bare", "cut50",
         "recbare", "rec50", "rec75", "rec90", "rec95",
         "recbare_f", "rec50_f", "rec95_f",
         "rec50_fb", "cut50_fb"]
GAP_AFTER = {"cut50", "rec95", "rec95_f"}      # riga vuota fra i blocchi del disegno
FGL = {"recbare_f", "rec50_f", "rec95_f"}      # i soli bracci col completamento

# verbatim da agg_fact.main(): la famiglia di confronti su cui si corregge con Holm
FAM = [("recbare", "bare", "direct check vs none, no cutoff"),
       ("rec50", "cut50", "direct check vs none, lambda=0.5"),
       ("cut50", "bare", "cutoff vs none, no candidate handling"),
       ("rec50", "recbare", "cutoff vs none, direct check"),
       ("rec95", "recbare", "loose cutoff vs none, direct check"),
       ("rec95", "rec50", "loose vs mid-gap cutoff, direct check"),
       ("rec50_f", "rec50", "FGL postprocessing vs direct check, lambda=0.5"),
       ("rec95_f", "rec95", "FGL postprocessing vs direct check, lambda=0.95"),
       ("recbare_f", "recbare", "FGL postprocessing vs direct check, no cutoff"),
       ("rec50_f", "recbare", "faithful FGL vs recovery without cutoff"),
       ("rec50_fb", "rec50", "fallback on c'xhat vs none, lambda=0.5"),
       ("cut50_fb", "cut50", "fallback on c'xhat vs none, no recovery")]

if set(ORDER) != set(A.ARMS):
    raise SystemExit("ORDER e agg_fact.ARMS non coincidono: %s" %
                     (set(ORDER) ^ set(A.ARMS)))


def num(x):
    """intero con le migliaia separate da uno spazio fine (leggibile in tabella)"""
    s = "%d" % round(x)
    sg, s = ("-", s[1:]) if s.startswith("-") else ("", s)
    out = ""
    while len(s) > 3:
        out, s = "\\," + s[-3:] + out, s[:-3]
    return sg + s + out


def pv(p):
    return r"$<10^{-4}$" if p < 1e-4 else "%.4f" % p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=DEF_RES)
    ap.add_argument("--out", default=DEF_OUT)
    ap.add_argument("--tol", type=float, default=1e-6)
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()
    RES = a.results

    cmd = ["mk_tabs_fact.py"] + sys.argv[1:]
    runs, pilot, notes, below, dropped = A.load(a.results)

    # invariante fatale di agg_fact.py: un primale sotto il bound LP ferma tutto
    if below:
        print("FATALE: %d run con primale SOTTO il bound LP." % len(below), file=sys.stderr)
        sys.exit(2)

    # le STESSE istanze di agg_fact.py: griglia bracci x semi completa
    insts, arms = A.complete_instances(runs, a.seeds)
    E1 = [i for i in insts if pilot.get(i)]
    E2 = [i for i in insts if i in pilot and not pilot[i]]

    def inst_med(i, arm, key):
        v = [runs[i][(arm, s)][key] for s in range(a.seeds) if (arm, s) in runs[i]]
        return A.med(v)

    def paired_seeds(i, x, y):
        return [s for s in range(a.seeds) if (x, s) in runs[i] and (y, s) in runs[i]]

    # ------------------------------------------------------------------- T1
    def t1(sl):
        L = [r"\begin{tabular}{lrrrrrrrrrr}", r"\toprule",
             r" & \multicolumn{2}{c}{with a solution} & \multicolumn{5}{c}{medians}"
             r" & \multicolumn{3}{c}{completion LPs} \\",
             r"\cmidrule(lr){2-3}\cmidrule(lr){4-8}\cmidrule(lr){9-11}",
             r"variant & inst. & runs & gap (\%) & PI/TL (\%) & $t_{\mathrm{first}}$ (s)"
             r" & rounds & LP iter. & calls & feas. & infeas. \\",
             r"\midrule"]
        for arm in ORDER:
            if arm not in arms:
                continue
            recs = [runs[i][(arm, s)] for i in sl for s in range(a.seeds) if (arm, s) in runs[i]]
            if not recs:
                continue
            wi = sum(1 for i in sl if any((arm, s) in runs[i] and runs[i][(arm, s)]["primal"] is not None
                                          for s in range(a.seeds)))
            wr = sum(1 for r in recs if r["primal"] is not None)
            g = A.med([inst_med(i, arm, "gap") for i in sl if inst_med(i, arm, "gap") is not None])
            pit = A.med([inst_med(i, arm, "pin") / (inst_med(i, arm, "tl") or 1.0)
                         for i in sl if inst_med(i, arm, "pin") is not None])
            tf = A.med([r["tfirst"] for r in recs if r["tfirst"] is not None])
            nl = A.med([r["nloops"] for r in recs])
            it = A.med([r["nlpiter"] for r in recs])
            c1 = sum(r["lpfix"] for r in recs)
            c2 = sum(r["lpfixfeas"] for r in recs)
            c3 = sum(r["lpfixinf"] for r in recs)
            comp = ([num(c1), num(c2), num(c3)] if (arm in FGL or c1) else ["--", "--", "--"])
            L.append("%s & %s/%s & %s/%s & %.2f & %.1f & %s & %s & %s & %s & %s & %s \\\\"
                     % (TEX[arm], num(wi), num(len(sl)), num(wr), num(len(recs)), g, pit,
                        ("%.2f" % tf) if tf is not None else "--", num(nl), num(it), *comp))
            if arm in GAP_AFTER:
                L.append(r"\addlinespace")
        L += [r"\bottomrule", r"\end{tabular}"]
        return L

    # ------------------------------------------------------------------- T2
    def paired(sl, x, y, key="gap"):
        """better/tie/worse per istanza, piu' la mediana della differenza
        appaiata (B - A, in punti di gap: positiva = A migliore) sulle sole
        istanze NON pari, cioe' l'entita' dell'effetto dove l'effetto c'e'."""
        b = t = w = 0
        diffs = []
        for i in sl:
            ss = paired_seeds(i, x, y)
            if not ss:
                continue
            mx = A.med([runs[i][(x, s)][key] for s in ss])
            my = A.med([runs[i][(y, s)][key] for s in ss])
            if mx < my - a.tol:
                b += 1
                diffs.append(my - mx)
            elif mx > my + a.tol:
                w += 1
                diffs.append(my - mx)
            else:
                t += 1
        return b, t, w, (A.med(diffs) if diffs else None)

    def t2(sl):
        rows = []
        for x, y, lab in FAM:
            if x not in arms or y not in arms:
                continue
            b, t, w, md = paired(sl, x, y)
            rows.append((x, y, b, t, w, A.sign_test(b, w), md))
        adj = A.holm([r[5] for r in rows]) if rows else []
        L = [r"\begin{tabular}{lrrrrrr}", r"\toprule",
             r" & \multicolumn{3}{c}{instances} & \multicolumn{2}{c}{$p$-value} & median diff. \\",
             r"\cmidrule(lr){2-4}\cmidrule(lr){5-6}\cmidrule(lr){7-7}",
             r"comparison ($A$ vs.\ $B$) & $A$ better & tie & $A$ worse & sign test & Holm & $B-A$, non-tied \\",
             r"\midrule"]
        for r, pa in zip(rows, adj):
            L.append("%s vs.\\ %s & %d & %d & %d & %s & %s & %s \\\\"
                     % (TEX[r[0]], TEX[r[1]], r[2], r[3], r[4], pv(r[5]), pv(pa),
                        ("$%+.1f$" % r[6]) if r[6] is not None else "--"))
        L += [r"\bottomrule", r"\end{tabular}"]
        return L

    # ------------------------------------------------------------------- T3
    def t3rows(sl):
        L = []
        for x, y, lab in FAM:
            if x not in arms or y not in arms:
                continue
            AA = BB = CC = DD = 0
            for i in sl:
                for s in paired_seeds(i, x, y):
                    px = runs[i][(x, s)]["primal"] is not None
                    py = runs[i][(y, s)]["primal"] is not None
                    if px and not py:
                        AA += 1
                    elif py and not px:
                        BB += 1
                    elif px and py:
                        CC += 1
                    else:
                        DD += 1
            L.append("%s vs.\\ %s & %s & %s & %s & %s \\\\"
                     % (TEX[x], TEX[y], num(AA), num(BB), num(CC), num(DD)))
        return L

    def t3():
        L = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"comparison ($A$ vs.\ $B$) & $A$ only & $B$ only & both & neither \\",
             r"\midrule",
             r"\multicolumn{5}{l}{\emph{E1: the pilot finds a solution (%d instances)}} \\" % len(E1)]
        L += t3rows(E1)
        L += [r"\midrule",
              r"\multicolumn{5}{l}{\emph{E2: the pilot finds nothing (%d instances)}} \\" % len(E2)]
        L += t3rows(E2)
        L += [r"\bottomrule", r"\end{tabular}"]
        return L

    # ------------------------------------------------------------------- output
    os.makedirs(a.out, exist_ok=True)
    hdr = ["%%%% generata da: python %s" % " ".join(cmd),
           "%%%% input: %s" % os.path.abspath(a.results),
           r"%% nomi dei bracci: macro \armnone \armchk \armfgl \armfb \armfbn del preambolo",
           "%% solo il tabular: table/caption/label e il corpo del testo li mette il .tex"]

    def write(name, note, body):
        path = os.path.join(a.out, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(hdr + ["%% " + note, ""] + body) + "\n")
        print("scritto %s (%d righe)" % (path, len(body)))

    write("tab_fact_e1.tex",
          "T1, strato E1: %d istanze, %d bracci x %d semi" % (len(E1), len(arms), a.seeds),
          t1(E1))
    write("tab_fact_e2.tex",
          "T1, strato E2: %d istanze, %d bracci x %d semi" % (len(E2), len(arms), a.seeds),
          t1(E2))
    write("tab_fact_paired.tex",
          "T2, SOLO E1 (%d istanze): appaiato per istanza sul gap finale, Holm su %d confronti"
          % (len(E1), len(FAM)), t2(E1))
    write("tab_fact_found.tex",
          "T3: found/not-found per run, tutte e quattro le celle (neither inclusa), E1 ed E2",
          t3())
    print("E1=%d E2=%d istanze, bracci: %s" % (len(E1), len(E2), " ".join(arms)))


if __name__ == "__main__":
    main()
