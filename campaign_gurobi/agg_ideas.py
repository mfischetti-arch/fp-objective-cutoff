#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregatore dei log della campagna "idee" (job24_ideas.sh + fp_target.py --pressure).

Un log per task SLURM, logs/t24_<jobid>_<task>.log. Il PARSING e' quello di
agg_target23.py, importato di peso: stesse righe RES, stesso dizionario
chiave=valore, stessa classe Row (e quindi la stessa definizione di successo --
target_ok confermato da validated), stessa mediana, stesso test del segno
binomiale esatto. Cambia una cosa sola, ed e' il campo che in job23 era il
"modo": qui e' il BRACCIO INTERO, cioe' modo + pressione, per esempio

    naive        completion:cut:0.05        completion:reflect:0.02+lb:0.1

e i bracci non sono tre e fissi ma quanti ne dice ARMS. Da qui le due
differenze rispetto ad agg_target23:

  * i confronti appaiati non sono fra tre bracci a coppie, ma di OGNI braccio
    contro DUE riferimenti: il naive (che non ha nessuna riga interna) e
    completion:cut:0.05 (la fascia che ha vinto la campagna a = 0.9). Il primo
    dice se la pressione serve, il secondo se serve piu' della fascia di oggi;
  * il confronto e' SUL SOLO ESITO. In agg_target23 un pareggio di esito veniva
    rotto dal tempo, e quel criterio premia il braccio piu' veloce sulle istanze
    facili, dove tutti riescono. Qui il tempo si guarda a parte, e solo fra le
    istanze che ENTRAMBI i bracci risolvono.

    python agg_ideas.py logs/t24_*.log [--a 0.9] [--csv f.csv] [--force]

Solo stdlib + numpy, come agg_target23 (il venv del cluster e' minimale).
"""

import argparse
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agg_target23 import (                                        # noqa: E402
    EPS, NA, TIME_TOL, binom_sign_p, close, f3, fnum, inum, med,
    read_logs, warn_multi_a,
)

# il braccio di riferimento "storico": la fascia scelta in taratura ad a = 0.9
CUT_REF = "completion:cut:0.05"
# un'istanza conta come RISOLTA da un braccio se la mediana di target_ok sui
# semi e' >= 0.5, cioe' se il braccio ce l'ha fatta su META' dei semi o piu'
OUT_OK = 0.5 - 1e-12
KINDS = ("tutte", "pure", "miste")


# --------------------------------------------------------------------- utilita'

def arm_sort_key(a):
    """naive primo, poi il riferimento cut, poi in ordine alfabetico: cosi' le
    due colonne di paragone stanno in cima a ogni tabella."""
    return (0 if a == "naive" else 1 if a.startswith("completion:cut:") else 2, a)


def pick_cut_ref(arms):
    """Il secondo riferimento: completion:cut:0.05 se c'e', altrimenti il primo
    completion:cut:* presente, altrimenti nessuno."""
    if CUT_REF in arms:
        return CUT_REF
    cand = sorted(a for a in arms if a.startswith("completion:cut:"))
    return cand[0] if cand else None


def w_of(r):
    """U' della riga sull'obiettivo, misurato come il w di sempre: la frazione
    del gap G = U - z_LP di cui la riga sta sotto il bersaglio,

        w = (U - uprime_final) / (U - z_LP)

    None dove la riga non c'e' (naive, lb, sgn, card, nogood da sole) o dove il
    gap non e' positivo."""
    up = fnum(r.kv, "uprime_final")
    U, zlp = fnum(r.kv, "U"), fnum(r.kv, "zlp")
    if up is None or U is None or zlp is None:
        return None
    G = U - zlp
    return None if G <= 0 else (U - up) / G


def inst_summary(rr):
    """Riassunto di (istanza, braccio) sui semi."""
    ok = [r.ok for r in rr]
    tts = [r.tts for r in rr if r.ok and r.tts is not None]
    return {
        "n_seed": len(rr),
        "n_ok": sum(ok),
        "outcome": med(ok),
        "med_cens": med([r.t_cens for r in rr]),
        "med_tts": med(tts),
        "med_w": med([w_of(r) for r in rr]),
        # lbmove: quante volte il centro della palla di local branching si e'
        # spostato. Assente (e quindi vuoto) per ogni altro braccio.
        "med_moves": med([fnum(r.kv, "n_center_moves") for r in rr]),
    }


def build(rows):
    """{(inst, braccio): riassunto}, e l'anagrafica per istanza."""
    by = defaultdict(list)
    for r in rows:
        by[(r.inst, r.mode)].append(r)
    summ = {k: inst_summary(v) for k, v in by.items()}
    info = {}
    for r in rows:
        d = info.setdefault(r.inst, {"bench": r.bench, "n_cont": None, "n_bin": None,
                                     "tl": r.tl, "U": fnum(r.kv, "U"),
                                     "zlp": fnum(r.kv, "zlp"), "zinc": fnum(r.kv, "zinc"),
                                     "zbest": fnum(r.kv, "zbest"), "set": r.dataset})
        for k, key in (("n_cont", "n_cont"), ("n_bin", "n_bin")):
            if d[k] is None:
                d[k] = inum(r.kv, key)
    return summ, info


def select(info, kind):
    out = []
    for inst, d in info.items():
        nc = d["n_cont"]
        if kind == "pure" and not (nc is not None and nc == 0):
            continue
        if kind == "miste" and not (nc is not None and nc > 0):
            continue
        out.append(inst)
    return sorted(out)


def solved(s):
    return s is not None and s["outcome"] is not None \
        and not math.isnan(s["outcome"]) and s["outcome"] >= OUT_OK


def speed(s):
    """Il tempo con cui si confrontano due bracci che hanno ENTRAMBI risolto
    l'istanza: la mediana di time_to_success sui semi riusciti, e se manca il
    tempo censurato."""
    t = s["med_tts"]
    if t is None or math.isnan(t):
        t = s["med_cens"]
    return None if t is None or math.isnan(t) else t


# ------------------------------------------------------------------- invarianti

def check_invariants(rows, arms):
    """Le tre cose senza le quali il confronto non e' un confronto: lo STESSO
    bersaglio U e lo STESSO budget TL per tutti i bracci di un'istanza, e
    nessuna corsa morta di errore (una riga di pressione scritta male, un
    incumbent di un'altra istanza: sono errori di campagna, non risultati)."""
    bad = []
    by_inst = defaultdict(list)
    for r in rows:
        by_inst[r.inst].append(r)
    for inst in sorted(by_inst):
        rr = by_inst[inst]
        us = {round(u, 12) for u in (fnum(r.kv, "U") for r in rr) if u is not None}
        if len(us) > 1:
            bad.append("%s: U diverso fra i bracci (%s)"
                       % (inst, ", ".join("%.12g" % u for u in sorted(us))))
        elif not us:
            bad.append("%s: nessuna riga con U" % inst)
        tls = {round(t, 9) for t in (r.tl for r in rr) if t is not None}
        if len(tls) > 1:
            bad.append("%s: tl diverso fra i bracci (%s)"
                       % (inst, ", ".join("%g" % t for t in sorted(tls))))
        for r in rr:
            U, zlp = fnum(r.kv, "U"), fnum(r.kv, "zlp")
            if U is not None and zlp is not None and U < zlp - EPS * max(1.0, abs(U), abs(zlp)):
                bad.append("%s/%s/seed=%s: U=%.12g < zlp=%.12g [%s]"
                           % (inst, r.mode, r.seed, U, zlp, r.src))
            if r.kv.get("status") == "error":
                bad.append("%s/%s/seed=%s: status=error (%s) [%s]"
                           % (inst, r.mode, r.seed,
                              str(r.kv.get("error", NA))[:70], r.src))
        # un braccio per (istanza, seme), non due
        by_seed = defaultdict(Counter)
        for r in rr:
            by_seed[r.seed][r.mode] += 1
        for sd in sorted(by_seed, key=lambda x: (x is None, x)):
            dup = [a for a, n in by_seed[sd].items() if n > 1]
            if dup:
                bad.append("%s/seed=%s: bracci duplicati: %s"
                           % (inst, sd, ",".join("%s x%d" % (a, by_seed[sd][a]) for a in dup)))
    return bad


def report_incomplete(summ, info, arms):
    """Istanze a cui manca qualche braccio: NON e' fatale (una campagna puo'
    essere ancora in corso, o un braccio puo' essere stato aggiunto dopo), ma i
    confronti appaiati useranno solo le istanze dove entrambi i bracci ci sono,
    e conviene saperlo."""
    holes = defaultdict(list)
    for inst in sorted(info):
        for a in arms:
            if (inst, a) not in summ:
                holes[a].append(inst)
    if not holes:
        return
    print("!! istanze INCOMPLETE (il braccio manca del tutto): i confronti che le")
    print("!! riguardano usano solo le istanze presenti in entrambi i bracci.")
    for a in sorted(holes, key=arm_sort_key):
        names = holes[a]
        print("     %-34s %3d istanze: %s%s"
              % (a, len(names), ", ".join(names[:5]), " ..." if len(names) > 5 else ""))
    print("")


# ---------------------------------------------------------------------- tabelle

def print_head(L, rows, arms, info, cutref):
    seeds = sorted({r.seed for r in rows if r.seed is not None})
    print("CAMPAGNA IDEE -- righe di pressione nell'LP di proiezione")
    print("(%d file, %d righe lette; %d righe RES di run; %d istanze; semi %s)"
          % (L.n_files, L.n_lines, len(rows), len(info),
             ",".join(str(s) for s in seeds)))
    print("")
    print("COME SI LEGGE")
    print("  braccio      <modo>[:<pressione>], la riga di comando di fp_target.py:")
    print("               naive = riga statica c'x <= U dentro il modello, nessuna")
    print("               pressione; cut:w = la fascia di sempre; reflect/lb/sgn/")
    print("               card/nogood = le righe di pressione nuove (vedi la")
    print("               docstring di fp_target.py).")
    print("  N_ist        istanze con almeno una riga per quel braccio.")
    print("  ist_ok       istanze RISOLTE: mediana di target_ok sui semi >= 0.5,")
    print("               cioe' riuscite su meta' dei semi o piu'. target_ok = esiste")
    print("               un punto ammissibile per i vincoli ORIGINALI con c'x <= U,")
    print("               e Gurobi lo conferma a tolleranza assoluta (validated).")
    print("  coppie_ok    coppie (istanza, seme) riuscite su quelle eseguite.")
    print("  med_t_cens   mediana, sulle istanze, del tempo CENSURATO mediano sui")
    print("               semi: time_to_success se riuscito, il TL altrimenti.")
    print("  med_tts_ok   mediana del tempo dei soli successi (ignora i fallimenti:")
    print("               un braccio che riesce di rado e in fretta sembra veloce).")
    print("  w_eff        (U - uprime_final) / (U - z_LP): dove sta la riga")
    print("               sull'obiettivo, in unita' di gap. Vuoto dove quella riga")
    print("               non esiste (naive, lb, sgn, card, nogood da soli).")
    print("  mosse_c      n_center_moves: quante volte il centro della palla di")
    print("               local branching si e' spostato sul miglior punto trovato")
    print("               dal recupero. Solo lbmove; vuoto per tutti gli altri.")
    print("  pure/miste   pure = nessuna variabile continua (n_cont = 0), dove il")
    print("               completamento di FGL coincide col test diretto; miste =")
    print("               n_cont > 0, le uniche dove il recupero puo' fare la")
    print("               differenza.")
    print("  W/L/T        vittorie / sconfitte / pareggi del BRACCIO contro il")
    print("               riferimento, SUL SOLO ESITO; p = test del segno esatto a")
    print("               due code su n_eff = W + L. Il tempo e' un conto a parte,")
    print("               fatto solo fra le istanze che ENTRAMBI risolvono, con")
    print("               tolleranza relativa del %d%%." % int(TIME_TOL * 100))
    print("")
    print("bracci (%d): %s" % (len(arms), "  ".join(arms)))
    print("riferimenti: naive%s" % ("  e  " + cutref if cutref else
                                    "  (nessun braccio completion:cut:*: solo il naive)"))
    print("")


def print_arms(summ, info, arms):
    print("(a) ESITI PER BRACCIO")
    print("")
    hdr = ("%-6s %-34s %6s %7s %11s %11s %11s %9s %9s"
           % ("tipo", "braccio", "N_ist", "ist_ok", "coppie_ok", "med_t_cens",
              "med_tts_ok", "w_eff", "mosse_c"))
    print(hdr)
    print("-" * len(hdr))
    for kind in KINDS:
        insts = select(info, kind)
        if not insts:
            continue
        for arm in arms:
            ss = [summ[(i, arm)] for i in insts if (i, arm) in summ]
            if not ss:
                continue
            print("%-6s %-34s %6d %7d %11s %s %s %s %s"
                  % (kind, arm, len(ss), sum(1 for s in ss if solved(s)),
                     "%d/%d" % (sum(s["n_ok"] for s in ss),
                                sum(s["n_seed"] for s in ss)),
                     f3(med([s["med_cens"] for s in ss]), 11),
                     f3(med([s["med_tts"] for s in ss]), 11),
                     f3(med([s["med_w"] for s in ss]), 9),
                     f3(med([s["med_moves"] for s in ss]), 9)))
        print("")


def paired(summ, insts, arm, ref):
    """Il braccio contro il riferimento, su un insieme di istanze.
    Ritorna (n_ist, W, L, T, p) sull'ESITO e (n_ent, Wt, Lt, Tt, pt) sul TEMPO
    fra le sole istanze che ENTRAMBI risolvono."""
    both = [i for i in insts if (i, arm) in summ and (i, ref) in summ]
    w = l = t = 0
    for i in both:
        a, b = summ[(i, arm)], summ[(i, ref)]
        oa, ob = a["outcome"], b["outcome"]
        if oa is None or ob is None or math.isnan(oa) or math.isnan(ob) or abs(oa - ob) <= 1e-12:
            t += 1
        elif oa > ob:
            w += 1
        else:
            l += 1
    ent = [i for i in both if solved(summ[(i, arm)]) and solved(summ[(i, ref)])]
    wt = lt = tt = 0
    for i in ent:
        ta, tb = speed(summ[(i, arm)]), speed(summ[(i, ref)])
        if ta is None or tb is None or \
                abs(ta - tb) <= TIME_TOL * max(abs(ta), abs(tb), 1e-12):
            tt += 1
        elif ta < tb:
            wt += 1
        else:
            lt += 1
    return ((len(both), w, l, t, binom_sign_p(w, w + l)),
            (len(ent), wt, lt, tt, binom_sign_p(wt, wt + lt)))


def print_paired(summ, info, arms, refs):
    print("(b) CONFRONTI APPAIATI PER ISTANZA, contro ogni riferimento")
    print("    [W = vittorie del BRACCIO. Esito = mediana di target_ok sui semi,")
    print("     nessun pareggio rotto dal tempo. Tempo = solo fra le istanze che")
    print("     ENTRAMBI risolvono, tolleranza %d%%.]" % int(TIME_TOL * 100))
    print("")
    hdr = ("%-6s %-34s %5s %4s %4s %4s %8s   %5s %4s %4s %4s %8s"
           % ("tipo", "braccio", "N", "W", "L", "T", "p_esito",
              "N_ent", "W", "L", "T", "p_tempo"))
    for ref in refs:
        print("riferimento: %s" % ref)
        print(hdr)
        print("-" * len(hdr))
        for kind in KINDS:
            insts = select(info, kind)
            if not insts:
                continue
            for arm in arms:
                if arm == ref:
                    continue
                (n, w, l, t, p), (ne, wt, lt, tt, pt) = paired(summ, insts, arm, ref)
                if n == 0:
                    continue
                print("%-6s %-34s %5d %4d %4d %4d %s   %5d %4d %4d %4d %s"
                      % (kind, arm, n, w, l, t, f3(p, 8), ne, wt, lt, tt, f3(pt, 8)))
            print("")


def print_skips(L):
    print("SKIP e FAIL (contati a parte, non entrano in nessuna tabella)")
    if not L.skips and not L.fails:
        print("    nessuno.")
        print("")
        return
    by = defaultdict(set)
    for inst, why in L.skips:
        by[why].add(inst)
    for why in sorted(by):
        names = sorted(by[why])
        print("    SKIP %-16s %4d   %s%s"
              % (why, len(names), ", ".join(names[:4]),
                 " ..." if len(names) > 4 else ""))
    byf = defaultdict(set)
    for inst, why in L.fails:
        byf[why].add(inst)
    for why in sorted(byf):
        print("    FAIL %-16s %4d   %s" % (why, len(byf[why]),
                                           ", ".join(sorted(byf[why])[:4])))
    print("")


def write_csv(path, summ, info, arms):
    cols = ("inst", "arm", "set", "bench", "n_bin", "n_cont", "n_seed", "n_ok",
            "outcome", "med_t_cens", "med_tts_ok", "w_eff", "n_center_moves",
            "U", "zlp", "zinc",
            "zbest", "tl")

    def g(x):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return ""
        return "%.6g" % x if isinstance(x, float) else str(x)

    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(cols) + "\n")
        for inst in sorted(info):
            d = info[inst]
            for arm in arms:
                s = summ.get((inst, arm))
                if s is None:
                    continue
                fh.write(",".join([
                    inst, arm, str(d["set"]), g(d["bench"]), g(d["n_bin"]),
                    g(d["n_cont"]), g(s["n_seed"]), g(s["n_ok"]), g(s["outcome"]),
                    g(s["med_cens"]), g(s["med_tts"]), g(s["med_w"]),
                    g(s["med_moves"]),
                    g(d["U"]), g(d["zlp"]), g(d["zinc"]), g(d["zbest"]), g(d["tl"]),
                ]) + "\n")


# --------------------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="agg_ideas.py",
        description="Aggregatore della campagna idee su Gurobi (job24_ideas.sh).")
    p.add_argument("logs", nargs="+")
    p.add_argument("--a", type=float, default=None,
                   help="filtra le righe sul campo a (default: tutte, con avviso "
                        "se ce n'e' piu' d'uno)")
    p.add_argument("--csv", default=None,
                   help="scrive una riga per (istanza, braccio)")
    p.add_argument("--force", action="store_true",
                   help="stampa le tabelle anche con invarianti violate (che pero'"
                        " restano scritte in testa: l'aggregato NON e' affidabile)")
    args = p.parse_args(argv)

    L = read_logs(args.logs, args.a)
    warn_multi_a(L, args.a)
    rows = list(L.rows)
    if not rows:
        sys.exit("nessuna riga RES di run nei log indicati (solo SKIP/FAIL?)")
    arms = sorted({r.mode for r in rows}, key=arm_sort_key)
    summ, info = build(rows)
    cutref = pick_cut_ref(arms)

    bad = check_invariants(rows, arms)
    print_head(L, rows, arms, info, cutref)
    if bad:
        print("INVARIANTI VIOLATE (%d): l'aggregato NON e' affidabile." % len(bad))
        print("")
        for msg in bad[:40]:
            print("  !! " + msg)
        if len(bad) > 40:
            print("  ... e altre %d violazioni" % (len(bad) - 40))
        print("")
        if not args.force:
            print("mi fermo. Con --force le tabelle si stampano lo stesso.")
            return 1
    else:
        print("invarianti: tutte verificate (U e tl uguali fra i bracci, "
              "nessuno status=error, nessun braccio duplicato).")
        print("")

    dg = [r for r in rows if r.downgraded]
    if dg:
        n_dich = sum(1 for r in rows if inum(r.kv, "target_ok"))
        print("DECLASSATI a fallimento (target_ok=1 ma Gurobi NON conferma il punto,"
              " validated=0): %d run su %d successi dichiarati" % (len(dg), n_dich))
        for r in dg[:20]:
            print("  !! %s/%s/seed=%s  best_obj=%s U=%s [%s]"
                  % (r.inst, r.mode, r.seed, r.kv.get("best_obj", NA),
                     r.kv.get("U", NA), r.src))
        if len(dg) > 20:
            print("  ... e altri %d" % (len(dg) - 20))
        print("")

    print_skips(L)
    report_incomplete(summ, info, arms)
    print_arms(summ, info, arms)
    print("")
    print_paired(summ, info, arms, [a for a in ("naive", cutref) if a in arms])
    if args.csv:
        write_csv(args.csv, summ, info, arms)
        print("CSV scritto in %s (una riga per istanza x braccio)" % args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
