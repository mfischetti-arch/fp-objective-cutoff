#!/usr/bin/env python3
"""Aggregatore della campagna FATTORIALE (job21_factorial.sh), disegnato sull'audit
adversariale esterno (AUDIT/audit_adversarial_fpcutoff_v2_MPC.md, §8 e §13-D).

    python3 agg_fact.py results_fact.txt                # markdown
    python3 agg_fact.py results_fact.txt --latex        # tabelle booktabs
    python3 agg_fact.py results_fact.txt --valid validated.txt   # incrocia col solchecker

Regole (le differenze da agg_e1.py sono TUTTE risposte a un rilievo dell'audit):

 * L'UNITA' INFERENZIALE E' L'ISTANZA (§8.1). Ogni confronto appaiato e' fatto
   sulla mediana per istanza (sui semi appaiabili), i p-value sono test dei
   segni per istanza, e i conteggi per run sono descrittivi e stanno a parte.
 * NESSUNA SELEZIONE SULL'ESITO (§7.2). Tutte le istanze entrano; la corsa
   `filter` (pilot: braccio bare, seme 0, meta' budget) serve solo a
   STRATIFICARE in E1 (il pilot trova una soluzione) ed E2 (non la trova), e
   la stratificazione si dichiara con i denominatori.
 * INVARIANTI FATALI (§4.4): un primale sotto z_LP - tol ferma tutto. Con
   --valid, un run la cui soluzione non e' feasible al solchecker, o il cui
   obiettivo ricalcolato differisce da quello dichiarato, ferma tutto.
 * MOLTEPLICITA' (§8.3): un endpoint primario dichiarato (gap finale per
   istanza, appaiato) e correzione di Holm sui confronti della famiglia.
 * `neither` SEMPRE VISIBILE (§8.5) nei confronti found/not-found.
 * COSTO DEL COMPLETAMENTO (§7.7): chiamate, feasible, infeasible, nlpiter,
   giri, per braccio.

Gap finale gamma = 100 |z - z_LP| / max(|z|,|z_LP|), 100 se senza soluzione o
di segno opposto (convenzioni dichiarate, come in agg_e1.py). Per il primal
integral si usa `print` prolungato all'orizzonte comune (pin = print + gamma
* max(TL - t, 0)).
"""
import argparse
import math
import statistics as st
import sys
from collections import defaultdict

NOSOL = 1e19
ARMS = ["bare", "cut50", "cut50_fb", "recbare", "rec50", "rec50_fb", "rec75",
        "rec90", "rec95", "recbare_f", "rec50_f", "rec95_f"]
NONARM = ("SKIP", "probe", "filter", "NOTE")
TEX = {"bare": r"\plain", "cut50": r"\cutoff", "cut50_fb": r"\cutoff$_{\mathrm{fb}}$",
       "recbare": r"\recover", "rec50": r"\cutrec", "rec50_fb": r"\cutrec$_{\mathrm{fb}}$",
       "rec75": r"\cutrec$_{0.75}$", "rec90": r"\cutrec$_{0.90}$", "rec95": r"\cutrec$_{0.95}$",
       "recbare_f": r"\recover$^{\mathrm{FGL}}$", "rec50_f": r"\cutrec$^{\mathrm{FGL}}$",
       "rec95_f": r"\cutrec$_{0.95}^{\mathrm{FGL}}$"}


def gamma(primal, ref):
    if primal is None:
        return 100.0
    if primal == 0.0 and ref == 0.0:
        return 0.0
    if primal * ref < 0.0:
        return 100.0
    d = max(abs(primal), abs(ref))
    return 100.0 * abs(primal - ref) / d if d > 0 else 0.0


def fl(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def sign_test(a, b):
    n = a + b
    if n == 0:
        return 1.0
    return min(1.0, 2.0 * sum(math.comb(n, k) for k in range(min(a, b) + 1)) / 2.0 ** n)


def holm(pvals):
    """Correzione di Holm; ritorna i p aggiustati nell'ordine dato."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    adj = [0.0] * m
    run = 0.0
    for rank, i in enumerate(idx):
        run = max(run, (m - rank) * pvals[i])
        adj[i] = min(1.0, run)
    return adj


def load(path):
    runs = defaultdict(dict)   # inst -> (arm, seed) -> rec
    pilot = {}                 # inst -> True/False (pilot found a solution)
    notes = defaultdict(list)
    below = []
    dropped = {}               # inst -> {motivi} delle righe non utilizzabili
    for ln in open(path, errors="replace"):
        if ln.startswith("NOTE|"):
            p = ln.rstrip("\n").split("|")
            notes[p[1]].append(p[2])
            continue
        if not ln.startswith("RES|"):
            continue
        p = ln.rstrip("\n").split("|")
        if len(p) < 3:
            continue
        inst, tag = p[1], p[2]
        d = {}
        for f in p[3:]:
            if "=" in f:
                k, v = f.split("=", 1)
                d[k] = v
        if tag == "filter":
            pr = fl(d.get("primal"), 1e20)
            pilot[inst] = pr is not None and abs(pr) < NOSOL
            continue
        if tag in NONARM:
            continue
        try:
            rec = dict(tl=float(d["tl"]), zlp=float(d["zlp"]), t=float(d["time"]),
                       pi=float(d["print"]), primal=float(d["primal"]),
                       seed=int(d["seed"]), nsol=int(d.get("nsol", 0)),
                       tfirst=fl(d.get("tfirst")), nloops=int(d.get("nloops", 0)),
                       nlpiter=int(d.get("nlpiter", 0)), ifound=int(d.get("ifound", 0)),
                       lpfix=int(d.get("lpfix", 0)), lpfixfeas=int(d.get("lpfixfeas", 0)),
                       lpfixinf=int(d.get("lpfixinf", 0)), err=d.get("err", "0"),
                       sol=d.get("sol", "none"))
        except (KeyError, ValueError):
            # riga senza un campo numerico obbligatorio: o z_LP e' "-" (LP di
            # radice non risolto nel probe) o il run e' morto senza statistiche.
            # NON si scarta in silenzio: si annota, e main() esclude l'istanza
            # intera dichiarandola.
            why = "zlp" if d.get("zlp", "-") == "-" else "run senza statistiche"
            dropped.setdefault(inst, set()).add(why)
            continue
        if abs(rec["primal"]) > NOSOL:
            rec["primal"] = None
        if rec["primal"] is not None and rec["primal"] < rec["zlp"] - 1e-6 * max(1.0, abs(rec["zlp"])):
            below.append((inst, tag, rec["seed"], rec["primal"], rec["zlp"]))
        rec["gap"] = gamma(rec["primal"], rec["zlp"])
        rec["pin"] = rec["pi"] + rec["gap"] * max(rec["tl"] - rec["t"], 0.0)
        runs[inst][(tag, rec["seed"])] = rec
    return runs, pilot, notes, below, dropped


def complete_instances(runs, seeds, arms=None):
    """Le istanze con la griglia bracci x semi COMPLETA: le uniche che entrano
    nell'analisi appaiata. E' la stessa regola di main(), esposta perche'
    mk_tabs_fact.py conti esattamente le stesse istanze."""
    arms = arms or [x for x in ARMS if any((x, s) in r for r in runs.values() for s in range(seeds))]
    return sorted(i for i in runs
                  if all((x, s) in runs[i] for x in arms for s in range(seeds))), arms


def load_valid(path):
    """VALID|inst|arm|seed=s|feasible=..|obj=..|claimed=..|delta=..
    Ritorna (fatali, migliori): le righe che invalidano i dati e quelle in cui il
    valore ricalcolato sull'originale e' migliore di quello dichiarato."""
    bad = []
    better = []
    for ln in open(path, errors="replace"):
        if not ln.startswith("VALID|"):
            continue
        p = ln.rstrip("\n").split("|")
        d = {}
        for f in p[3:]:
            if "=" in f:
                k, v = f.split("=", 1)
                d[k] = v
        if d.get("feasible") == "0":
            bad.append((p[1], p[2], p[3], "infeasible"))
        elif d.get("feasible") == "1":
            ob = fl(d.get("obj"))
            cl = fl(d.get("claimed"))
            if ob is None or cl is None:
                continue
            # `obj` viene dalla riga di display di SCIP: SEI cifre significative,
            # quindi lo scarto va letto RELATIVO. E il segno conta: un valore
            # ricalcolato PEGGIORE di quello dichiarato e' un claim gonfiato ed e'
            # fatale; uno MIGLIORE non gonfia nulla (succede quando una variabile
            # intera a 1-1e-15 nel trasformato, ammissibile entro tolleranza,
            # mappa nell'originale su un vettore che vale un po' meno) e viene
            # riportato senza fermare l'analisi.
            scale = max(1.0, abs(ob), abs(cl))
            if (ob - cl) / scale > 1e-5:
                bad.append((p[1], p[2], p[3], "ricalcolato PEGGIORE: obj=%s claimed=%s" % (d.get("obj"), d.get("claimed"))))
            elif (cl - ob) / scale > 1e-5:
                better.append((p[1], p[2], p[3], ob, cl))
    return bad, better


def med(v):
    return st.median(v) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--latex", action="store_true")
    ap.add_argument("--valid", default=None)
    ap.add_argument("--tol", type=float, default=1e-6)
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()

    runs, pilot, notes, below, dropped = load(a.results)
    out = []
    p = out.append

    # ------------------------------------------------------- invarianti fatali
    if below:
        print("FATALE: %d run con primale SOTTO il bound LP; i dati non sono utilizzabili. Esempi:"
              % len(below), file=sys.stderr)
        for r in below[:8]:
            print("  %s/%s/s%d  primal=%g < zlp=%g" % r, file=sys.stderr)
        sys.exit(2)
    if a.valid:
        bad, better = load_valid(a.valid)
        if bad:
            print("FATALE: %d soluzioni respinte dal solchecker o con obiettivo ricalcolato PEGGIORE di quello dichiarato:"
                  % len(bad), file=sys.stderr)
            for r in bad[:8]:
                print("  %s" % (r,), file=sys.stderr)
            sys.exit(2)
        p("## Validazione indipendente (%s)" % a.valid)
        p("- soluzioni inammissibili sul modello originale: 0")
        p("- soluzioni con obiettivo ricalcolato peggiore di quello dichiarato: 0")
        p("- soluzioni con obiettivo ricalcolato MIGLIORE di quello dichiarato (il run si e' sottostimato): %d" % len(better))
        for r in better[:12]:
            p("  %s/%s/%s  ricalcolato=%g dichiarato=%g" % r)
        p("")

    # ------------------------------------------------ esclusioni, DICHIARATE
    # Un'istanza entra nell'analisi solo con la griglia completa bracci x semi:
    # un fattoriale appaiato con celle vuote non e' piu' appaiato. Chi manca e'
    # elencato qui con il motivo, cosi' il paper puo' dirlo invece di tacerlo.
    arms_all = [x for x in ARMS if any((x, s) in r for r in runs.values() for s in range(a.seeds))]
    full, partial = [], {}
    for i in sorted(set(runs) | set(dropped)):
        have = sum(1 for x in arms_all for s in range(a.seeds) if (x, s) in runs.get(i, {}))
        if have == len(arms_all) * a.seeds:
            full.append(i)
        else:
            partial[i] = (have, len(arms_all) * a.seeds, "/".join(sorted(dropped.get(i, {"griglia incompleta"}))))
    nozlp = [i for i, (h, n, w) in partial.items() if h == 0 and "zlp" in w]
    other = {i: v for i, v in partial.items() if i not in nozlp}
    p("## Esclusioni dichiarate")
    p("- istanze con il pilota: %d" % len(pilot))
    p("- escluse perche' il primo LP non e' risolto entro il limite del probe (z_LP = '-'): %d" % len(nozlp))
    p("  " + " ".join(nozlp))
    p("- escluse perche' la griglia bracci x semi non e' completa: %d" % len(other))
    for i, (h, n, w) in sorted(other.items()):
        p("  %s: %d/%d run utilizzabili (%s)" % (i, h, n, w))
    p("- **istanze analizzate (griglia completa): %d**" % len(full))
    p("")
    insts = full
    arms = arms_all
    strata = {"E1 (pilot finds a solution)": [i for i in insts if pilot.get(i)],
              "E2 (pilot finds nothing)": [i for i in insts if i in pilot and not pilot[i]],
              "no pilot": [i for i in insts if i not in pilot]}

    def inst_med(i, arm, key):
        v = [runs[i][(arm, s)][key] for s in range(a.seeds) if (arm, s) in runs[i]]
        return med(v)

    def paired_seeds(i, x, y):
        return [s for s in range(a.seeds) if (x, s) in runs[i] and (y, s) in runs[i]]

    p("# Campagna fattoriale -- %s" % a.results)
    p("istanze con almeno un run: %d; pilot disponibile su %d; bracci: %s"
      % (len(insts), len(pilot), " ".join(arms)))
    for k, v in strata.items():
        p("- %s: %d istanze" % (k, len(v)))
    zero = [i for i, ns in notes.items() if any("gap di integralita" in n for n in ns)]
    p("- istanze con gap di integralita' nullo alla radice (registrate, non escluse): %d" % len(zero))
    p("")

    # ------------------------------------------------ T1: per braccio, per strato
    for sname, sl in strata.items():
        if not sl:
            continue
        p("## T1 -- %s: %d istanze, per braccio" % (sname, len(sl)))
        p("| variant | inst. with sol. | runs with sol. | median gap | median PI/TL | median t_first | "
          "median rounds | median LP iter | ifound/run | compl. calls | compl. feas | compl. infeas |")
        p("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for arm in arms:
            recs = [runs[i][(arm, s)] for i in sl for s in range(a.seeds) if (arm, s) in runs[i]]
            if not recs:
                continue
            wi = sum(1 for i in sl if any((arm, s) in runs[i] and runs[i][(arm, s)]["primal"] is not None
                                         for s in range(a.seeds)))
            wr = sum(1 for r in recs if r["primal"] is not None)
            g = med([inst_med(i, arm, "gap") for i in sl if inst_med(i, arm, "gap") is not None])
            # pin e' gia' in (punti percentuali x secondi): diviso TL da' il gap
            # medio sull'orizzonte, in punti percentuali
            pit = med([inst_med(i, arm, "pin") / (inst_med(i, arm, "tl") or 1.0)
                       for i in sl if inst_med(i, arm, "pin") is not None])
            tf = med([r["tfirst"] for r in recs if r["tfirst"] is not None])
            nl = med([r["nloops"] for r in recs]); it = med([r["nlpiter"] for r in recs])
            ifd = sum(r["ifound"] for r in recs) / max(1, len(recs))
            c1 = sum(r["lpfix"] for r in recs); c2 = sum(r["lpfixfeas"] for r in recs)
            c3 = sum(r["lpfixinf"] for r in recs)
            p("| `%s` | %d/%d | %d/%d | %.2f%% | %.1f%% | %s | %.0f | %.0f | %.2f | %d | %d | %d |"
              % (arm, wi, len(sl), wr, len(recs), g, pit, ("%.2f" % tf) if tf is not None else "--",
                 nl, it, ifd, c1, c2, c3))
        p("")

    # -------------------------- T2: confronti appaiati per ISTANZA, endpoint primario
    def paired(sl, x, y, key="gap"):
        b = t = w = 0
        for i in sl:
            ss = paired_seeds(i, x, y)
            if not ss:
                continue
            mx = med([runs[i][(x, s)][key] for s in ss]); my = med([runs[i][(y, s)][key] for s in ss])
            if mx < my - a.tol: b += 1
            elif mx > my + a.tol: w += 1
            else: t += 1
        return b, t, w

    fam = [("recbare", "bare", "direct check vs none, no cutoff"),
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
    for sname, sl in strata.items():
        if not sl:
            continue
        p("## T2 -- %s: paired per INSTANCE on the final gap (primary endpoint), Holm-corrected"
          % sname)
        rows = []
        for x, y, lab in fam:
            if x not in arms or y not in arms:
                continue
            b, t, w = paired(sl, x, y)
            rows.append((x, y, lab, b, t, w, sign_test(b, w)))
        adj = holm([r[6] for r in rows]) if rows else []
        p("| comparison | better / tie / worse | sign test p | Holm p |")
        p("|---|---|---|---|")
        for r, pa in zip(rows, adj):
            p("| `%s` vs `%s` (%s) | %d / %d / %d | %.4f | %.4f |" % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], pa))
        p("")

    # ------------------------------ T3: found / not found, with NEITHER visible
    for sname, sl in strata.items():
        if not sl:
            continue
        p("## T3 -- %s: found/not found, paired per run, all four cells" % sname)
        p("| comparison | X only | base only | both | neither | inst. X only | inst. base only |")
        p("|---|---|---|---|---|---|---|")
        for x, y, lab in fam:
            if x not in arms or y not in arms:
                continue
            A = B = C = D = 0; IA = IB = 0
            for i in sl:
                fx = fy = False
                for s in paired_seeds(i, x, y):
                    px = runs[i][(x, s)]["primal"] is not None; py = runs[i][(y, s)]["primal"] is not None
                    fx |= px; fy |= py
                    if px and not py: A += 1
                    elif py and not px: B += 1
                    elif px and py: C += 1
                    else: D += 1
                if fx and not fy: IA += 1
                if fy and not fx: IB += 1
            p("| `%s` vs `%s` | %d | %d | %d | %d | %d | %d |" % (x, y, A, B, C, D, IA, IB))
        p("")

    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
