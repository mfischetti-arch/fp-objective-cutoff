#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tabelle LaTeX della campagna "target" su Gurobi.

DA DOVE VENGONO I NUMERI
    results/eval50.res   righe RES del set di valutazione con a=0.5
    results/eval90.res   idem con a=0.9
    Lettura e statistiche sono quelle di `agg_target23.py` (importato, non
    duplicato): stesso parsing delle righe RES, stessa classe Row (ok, tts,
    t_cens, bench), stessa mediana `med`, stesso test del segno esatto
    `binom_sign_p`, stesso Holm. Se i numeri di queste tabelle e quelli
    dell'aggregatore divergono, e' un bug di questo file.

COME SI RIGENERANO
    python mk_tab_target.py
        scrive tab_target_outcome.tex e tab_target_paired.tex nella cartella
        dello script, stampa a video la versione testuale e i controlli
        obbligatori (valori attesi cablati in CHECKS).
    python mk_tab_target.py --outdir DIR      per scriverli altrove
    python mk_tab_target.py --no-write        solo controllo a video

DEFINIZIONI (identiche all'aggregatore)
    esito di (istanza, braccio) = mediana di target_ok sui 5 semi; l'istanza e'
      "risolta" se la mediana e' 1, cioe' se almeno 3 semi su 5 riescono;
    coppie = coppie (istanza, seme) con target_ok=1 (e validated != 0);
    tempo censurato = time_to_success se riuscito, altrimenti il time limit;
    famiglie: benchmark (bench=1, 43 istanze), non-benchmark (91), all (134);
    tipo: pure 0-1 (n_cont=0, 70) e mixed (n_cont>0, 64).
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg_target23 as agg  # noqa: E402  (dopo il sys.path)

ARMS = agg.ARMS                       # naive, test, completion
COMPARISONS = (("naive", "test"), ("naive", "completion"), ("test", "completion"))
FAMILIES = (("benchmark", "primario"), ("non-benchmark", "secondario"), ("all", "tutte"))
HOLM_FAMILIES = ("benchmark", "non-benchmark")   # le 12 righe della famiglia di Holm
# sottoinsiemi della tabella 1: etichetta -> (famiglia, tipo) nel gergo dell'aggregatore
SUBSETS = (("all", "tutte", "tutte"),
           ("benchmark", "primario", "tutte"),
           ("non-benchmark", "secondario", "tutte"),
           ("pure 0-1", "tutte", "puro"),
           ("mixed", "tutte", "misto"))
ALPHAS = (("0.5", "eval50.res"), ("0.9", "eval90.res"))

# controlli obbligatori: (a, sottoinsieme, braccio) -> (coppie_ok, istanze_risolte)
CHECKS_OUTCOME = {
    ("0.5", "all", "naive"): (438, 87),
    ("0.5", "all", "test"): (424, 84),
    ("0.5", "all", "completion"): (430, 85),
    ("0.9", "all", "naive"): (519, 104),
    ("0.9", "all", "test"): (518, 103),
    ("0.9", "all", "completion"): (561, 112),
    ("0.9", "mixed", "naive"): (206, 42),
    ("0.9", "mixed", "test"): (203, 40),
    ("0.9", "mixed", "completion"): (247, 49),
    ("0.9", "benchmark", "naive"): (162, 32),
    ("0.9", "benchmark", "test"): (163, 32),
    ("0.9", "benchmark", "completion"): (179, 35),
}
# (a, famiglia, A, B) -> (W, L, T, p, faster_W, faster_L, faster_T)
CHECKS_PAIRED = {
    ("0.9", "all", "naive", "completion"): (0, 8, 126, 0.008, 55, 35, 14),
    ("0.5", "benchmark", "naive", "test"): (3, 1, 39, None, None, None, None),
}


# ------------------------------------------------------------------ lettura dati

def load(path):
    """Righe RES set=eval di un file, con gli invarianti dell'aggregatore."""
    L = agg.read_logs([path])
    rows = [r for r in L.rows if r.dataset == "eval"]
    if not rows:
        sys.exit("nessuna riga set=eval in %s" % path)
    bad = agg.check_invariants(rows)
    if bad:
        sys.exit("invarianti violate in %s (%d): %s" % (path, len(bad), bad[0]))
    return rows


def arm_widths(rows):
    """braccio -> stringa di w cosi' com'e' nei log (un solo valore per braccio)."""
    out = {}
    for arm in ARMS:
        ws = sorted({r.w_str for r in rows if r.mode == arm})
        out[arm] = ws[0] if len(ws) == 1 else ",".join(ws)
    return out


# ------------------------------------------------------------------- statistiche

def outcome_cell(summ, insts, arm):
    """(istanze risolte, coppie riuscite, coppie totali) per un sottoinsieme."""
    ss = [summ[(i, arm)] for i in insts if (i, arm) in summ]
    solved = sum(1 for s in ss if s["outcome"] > 0.5)
    return solved, sum(s["n_ok"] for s in ss), sum(s["n_seed"] for s in ss)


def outcome_wlt(summ, insts, A, B):
    """W/L/T del braccio A contro B sul solo ESITO (mediana per istanza)."""
    w = l = t = 0
    for i in insts:
        sa, sb = summ.get((i, A)), summ.get((i, B))
        if sa is None or sb is None:
            continue
        if sa["outcome"] > sb["outcome"] + 1e-12:
            w += 1
        elif sb["outcome"] > sa["outcome"] + 1e-12:
            l += 1
        else:
            t += 1
    return w, l, t


def isnan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def faster_wlt(summ, insts, A, B, tol=agg.TIME_TOL):
    """Fra le istanze risolte da ENTRAMBI, chi ha il tempo mediano piu' basso
    di almeno il 5% (stessa tolleranza dell'aggregatore)."""
    w = l = t = 0
    for i in insts:
        sa, sb = summ.get((i, A)), summ.get((i, B))
        if sa is None or sb is None:
            continue
        if not (sa["outcome"] > 0.5 and sb["outcome"] > 0.5):
            continue
        ta, tb = sa["med_cens"], sb["med_cens"]
        if isnan(ta) or isnan(tb) or abs(ta - tb) <= tol * max(abs(ta), abs(tb), 1e-12):
            t += 1
        elif ta < tb:
            w += 1
        else:
            l += 1
    return w, l, t


def collect():
    """Tutto il materiale delle due tabelle, per valore di a."""
    here = os.path.dirname(os.path.abspath(__file__))
    data = {}
    for a, fname in ALPHAS:
        rows = load(os.path.join(here, "results", fname))
        summ, info = agg.build_summary(rows)
        data[a] = {
            "w": arm_widths(rows),
            "summ": summ,
            "subsets": {lab: agg.select(info, fam, kind) for lab, fam, kind in SUBSETS},
            "outcome": {}, "paired": [],
        }
        for lab, _, _ in SUBSETS:
            insts = data[a]["subsets"][lab]
            for arm in ARMS:
                data[a]["outcome"][(lab, arm)] = outcome_cell(summ, insts, arm)
        for fam_lab, fam in FAMILIES:
            insts = agg.select(info, fam, "tutte")
            for A, B in COMPARISONS:
                w, l, t = outcome_wlt(summ, insts, A, B)
                data[a]["paired"].append({
                    "family": fam_lab, "A": A, "B": B, "n": len(insts),
                    "w": w, "l": l, "t": t,
                    "p": agg.binom_sign_p(w, w + l),
                    "faster": faster_wlt(summ, insts, A, B),
                })
    add_holm(data)
    return data


def add_holm(data):
    """Holm sui 12 test dichiarati: 2 valori di a x 2 famiglie x 3 confronti."""
    fam = [(a, e) for a, _ in ALPHAS for e in data[a]["paired"]
           if e["family"] in HOLM_FAMILIES]
    adj = agg.holm([e["p"] for _, e in fam])
    for (_, e), pa in zip(fam, adj):
        e["p_holm"] = pa


# ----------------------------------------------------------------- versione testo

def print_text(data):
    print("TABELLA 1 -- esiti  [solved = istanze con mediana >= 3/5; pairs = coppie (ist,seme)]")
    print("")
    hdr = ("%-14s %5s   %-8s %-9s  %-8s %-9s  %-8s %-9s"
           % ("subset", "N", "naive", "pairs", "test", "pairs", "compl.", "pairs"))
    print(hdr)
    print("-" * len(hdr))
    for a, _ in ALPHAS:
        d = data[a]
        print("a=%s   (w: %s)" % (a, ", ".join("%s=%s" % (m, d["w"][m]) for m in ARMS)))
        for lab, _, _ in SUBSETS:
            n = len(d["subsets"][lab])
            cells = []
            for arm in ARMS:
                s, ok, tot = d["outcome"][(lab, arm)]
                cells.append("%-8d %-9s" % (s, "%d/%d" % (ok, tot)))
            print("%-14s %5d   %s" % (lab, n, "  ".join(cells)))
        print("")

    print("TABELLA 2 -- confronti appaiati  [W/L/T sull'esito; faster = tempo mediano -5%]")
    print("")
    hdr = ("%-14s %-24s %5s %12s %9s %9s %12s"
           % ("family", "comparison", "N", "W/L/T", "p", "p_Holm", "faster"))
    print(hdr)
    print("-" * len(hdr))
    for a, _ in ALPHAS:
        print("a=%s" % a)
        for e in data[a]["paired"]:
            ph = "%.3f" % e["p_holm"] if "p_holm" in e else "-"
            print("%-14s %-24s %5d %12s %9.3f %9s %12s"
                  % (e["family"], "%s vs %s" % (e["A"], e["B"]), e["n"],
                     "%d/%d/%d" % (e["w"], e["l"], e["t"]), e["p"], ph,
                     "%d/%d/%d" % e["faster"]))
        print("")


def check(data):
    """Confronto coi valori cablati: stampa e restituisce il numero di errori."""
    print("CONTROLLI OBBLIGATORI")
    bad = 0
    for (a, lab, arm), (ok_want, sol_want) in sorted(CHECKS_OUTCOME.items()):
        sol, ok, _ = data[a]["outcome"][(lab, arm)]
        good = (ok == ok_want and sol == sol_want)
        bad += 0 if good else 1
        print("%s a=%-4s %-14s %-11s  pairs %4d (atteso %4d)  solved %4d (atteso %4d)"
              % ("OK  " if good else "DIFF", a, lab, arm, ok, ok_want, sol, sol_want))
    for (a, fam, A, B), want in sorted(CHECKS_PAIRED.items()):
        e = [x for x in data[a]["paired"]
             if x["family"] == fam and x["A"] == A and x["B"] == B][0]
        got = (e["w"], e["l"], e["t"])
        good = got == want[:3]
        if want[3] is not None:
            good = good and abs(e["p"] - want[3]) < 5e-4 and e["faster"] == want[4:7]
        bad += 0 if good else 1
        print("%s a=%-4s %-14s %-22s  W/L/T %-10s (atteso %-10s)  p %.3f  faster %-10s"
              % ("OK  " if good else "DIFF", a, fam, "%s vs %s" % (A, B),
                 "%d/%d/%d" % got, "%d/%d/%d" % want[:3], e["p"], "%d/%d/%d" % e["faster"]))
    print("")
    print("controlli: %d su %d falliti" % (bad, len(CHECKS_OUTCOME) + len(CHECKS_PAIRED)))
    return bad


# ---------------------------------------------------------------------- LaTeX

def tex_p(p):
    return "$<$0.001" if p < 5e-4 else "%.3f" % p


ARM_TEX = {"naive": r"\textsc{naive}", "test": r"\textsc{test}",
           "completion": r"\textsc{completion}"}

CAP1 = r"""Outcome of the target experiment on the evaluation set. Every instance is run
with five random seeds under each policy. An instance counts as \emph{solved} when at least
three of its five seeds reach a feasible point with $c^{\top}x \le U$ within the time limit
(the outcome is the median over seeds of the success indicator); \emph{pairs} is the number of
(instance, seed) pairs that reach such a point, out of the $5N$ available. The target is
$U = z_{\mathrm{best}} + a\,(\zinc - z_{\mathrm{best}})$ and $w$ is the ``rounding moat''
as a fraction of $U - \zlp$:
%(arms)s. At $a=0.5$ the \textsc{test} policy is evaluated at $w=0.02$, an exploratory choice
(the tuning rule picked $w=0$, which is \textsc{naive}). Subsets: benchmark instances (the
primary test set) and non-benchmark ones; pure 0--1
instances ($n_{\mathrm{cont}}=0$) and mixed ones ($n_{\mathrm{cont}}>0$)."""

CAP2 = r"""Paired per-instance comparisons. W/T/L is the number of instances on which the
first policy wins, ties, or loses against the second on the \emph{outcome}, i.e.\ on the
per-instance median success defined in Table~\ref{tab:target-outcome}; $p$ is the exact
two-sided sign test on the non-ties; $p_{\mathrm{Holm}}$ is the Holm correction over the 12
declared tests, namely 2 values of $a$ $\times$ 2 families (benchmark, non-benchmark) $\times$
3 comparisons --- the \emph{all} rows are reported for information only and are not part of the
Holm family. \emph{Faster} counts, among the instances solved by both policies, how many times
the first policy's median time to success is lower than the second's by at least 5\%, how many
times the two tie within that tolerance, and how many times the second's is lower."""

ARMS_SENTENCE = (r"policy \textsc{naive} imposes a static cutoff constraint in the model, while "
                 r"\textsc{test} and \textsc{completion} impose an inner constraint at "
                 r"$U' = U - w\,(U - \zlp)$ and recover a point for the true target "
                 r"by a direct feasibility test and by FGL's LP completion, respectively")


def write_outcome(data, path):
    L = [r"\begin{table}[t]", r"\centering",
         r"\caption{%s}" % (CAP1 % {"arms": ARMS_SENTENCE}),
         r"\label{tab:target-outcome}", r"\small",
         r"\setlength{\tabcolsep}{4pt}",
         r"\begin{tabular}{lr rr rr rr}", r"\toprule",
         r"& & \multicolumn{2}{c}{\textsc{naive}} & \multicolumn{2}{c}{\textsc{test}}"
         r" & \multicolumn{2}{c}{\textsc{completion}} \\",
         r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(lr){7-8}",
         r"Subset & $N$ & solved & pairs & solved & pairs & solved & pairs \\"]
    for a, _ in ALPHAS:
        d = data[a]
        ws = ", ".join(r"$w=%s$ for %s" % (d["w"][m], ARM_TEX[m]) for m in ("test", "completion"))
        L += [r"\midrule",
              r"\multicolumn{8}{l}{$a=%s$ \quad (%s)} \\" % (a, ws),
              r"\addlinespace[1pt]"]
        for lab, _, _ in SUBSETS:
            cells = []
            for arm in ARMS:
                s, ok, tot = d["outcome"][(lab, arm)]
                cells += ["%d" % s, "%d/%d" % (ok, tot)]
            L.append(r"\quad %s & %d & %s \\" % (lab.replace("0-1", "0--1"),
                                                 len(d["subsets"][lab]), " & ".join(cells)))
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    write(path, L)


def write_paired(data, path):
    L = [r"\begin{table}[t]", r"\centering", r"\caption{%s}" % CAP2,
         r"\label{tab:target-paired}", r"\small",
         r"\setlength{\tabcolsep}{5pt}",
         r"\begin{tabular}{lrcrrc}", r"\toprule",
         r"Comparison & $N$ & W/T/L & $p$ & $p_{\mathrm{Holm}}$ & faster W/T/L \\"]
    for a, _ in ALPHAS:
        for fam_lab, _ in FAMILIES:
            L += [r"\midrule",
                  r"\multicolumn{6}{l}{$a=%s$ --- %s} \\" % (a, fam_lab),
                  r"\addlinespace[1pt]"]
            for e in [x for x in data[a]["paired"] if x["family"] == fam_lab]:
                L.append(paired_row(e))
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    write(path, L)


def paired_row(e):
    """Una riga di confronto: bracci, N, W/T/L (meglio-pari-peggio, come nel resto del
    paper), p, p_Holm, faster W/T/L."""
    ph = tex_p(e["p_holm"]) if "p_holm" in e else "--"
    return (r"\quad %s vs.\ %s & %d & %d/%d/%d & %s & %s & %d/%d/%d \\"
            % (ARM_TEX[e["A"]], ARM_TEX[e["B"]], e["n"], e["w"], e["t"], e["l"],
               tex_p(e["p"]), ph, e["faster"][0], e["faster"][2], e["faster"][1]))


def write(path, lines):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("scritto %s (%d righe)" % (path, len(lines)))


# ----------------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(prog="mk_tab_target.py",
                                description="tabelle LaTeX della campagna target")
    p.add_argument("--outdir", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--no-write", action="store_true", help="solo controllo a video")
    args = p.parse_args(argv)

    data = collect()
    print_text(data)
    bad = check(data)
    if bad:
        print("")
        print("MI FERMO: %d controlli non tornano, le tabelle NON sono state scritte." % bad)
        return 1
    if not args.no_write:
        print("")
        write_outcome(data, os.path.join(args.outdir, "tab_target_outcome.tex"))
        write_paired(data, os.path.join(args.outdir, "tab_target_paired.tex"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
