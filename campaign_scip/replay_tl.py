#!/usr/bin/env python3
"""Rigioca la campagna E1 a un orizzonte piu' corto, senza rieseguire nulla.

I log di SCIP salvati in out/wide/ contengono la tabella di display, che stampa
una riga a ogni nuovo incumbent con il tempo e il primal bound. Il primal bound
al tempo T' <= TL e' quindi leggibile dal log: il run e' deterministico e fino a
T' si e' comportato esattamente cosi'. Troncare a T' e' una replica esatta, non
una simulazione.

    python replay_tl.py results_wide.txt --factor 0.1 > results_wide_tl10.txt

produce un file di RES nello stesso formato, con tl, primal e primal integral
ricalcolati, che si da' in pasto ad agg_e1.py senza modificarlo.

Il PI e' reintegrato dalla traiettoria con la stessa gamma di agg_e1.py --- NON
e' il `primal-ref` di SCIP, che usa la sua funzione di gap. Per questo il
confronto fra orizzonti va fatto fra due file prodotti entrambi da qui:

    python replay_tl.py results_wide.txt --factor 1.0 > results_wide_r100.txt
    python replay_tl.py results_wide.txt --factor 0.1 > results_wide_r010.txt

I bracci senza `tryrounded` (bare, cut50) consegnano la soluzione a SCIP solo
all'uscita dal loop, cioe' al time limit: troncare il loro orizzonte misura il
momento in cui il run RIPORTA la soluzione, non quello in cui la trova. Il
replay e' valido solo sui tre bracci con recupero.
"""
import argparse
import os
import re
import sys

NOSOL = 1e19


def gamma(primal, ref):
    """La stessa di agg_e1.py, cosi' i due script parlano la stessa lingua."""
    if primal is None or abs(primal) > NOSOL:
        return 100.0
    if primal == 0.0 and ref == 0.0:
        return 0.0
    if primal * ref < 0.0:
        return 100.0
    d = max(abs(primal), abs(ref))
    return 100.0 * abs(primal - ref) / d if d > 0 else 0.0


def integral(tr, horizon, zlp):
    """Primal integral su [0, horizon]: gamma costante a tratti fra un
    incumbent e il successivo, 100 prima del primo."""
    pi, tprev, best = 0.0, 0.0, None
    for t, pb in tr:
        t = min(t, horizon)
        if t > tprev:
            pi += gamma(best, zlp) * (t - tprev)
            tprev = t
        if tprev >= horizon:
            break
        if abs(pb) < NOSOL:
            best = pb if best is None else min(best, pb)
    if tprev < horizon:
        pi += gamma(best, zlp) * (horizon - tprev)
    return pi, best


def traj(path, hdr_cache={}):
    """[(t, primal)] dal log di SCIP; None se il file non c'e' o non ha tabella."""
    if not os.path.exists(path):
        return None
    out, ipb, itime = [], None, 0
    with open(path, errors="replace") as f:
        for ln in f:
            if "|" not in ln:
                continue
            if ipb is None:
                if "primalbound" in ln:
                    cols = [c.strip() for c in ln.split("|")]
                    try:
                        ipb = cols.index("primalbound")
                    except ValueError:
                        ipb = None
                continue
            cols = ln.split("|")
            if len(cols) <= ipb:
                continue
            tm = cols[itime].strip()
            m = re.match(r"^[*a-zA-Z ]*?([0-9.]+)s$", tm)
            if not m:
                continue
            pb = cols[ipb].strip()
            if pb in ("", "--", "-"):
                continue
            try:
                out.append((float(m.group(1)), float(pb)))
            except ValueError:
                continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--factor", type=float, default=0.1,
                    help="orizzonte nuovo = factor * tl (0.1 = da 100x t_LP a 10x)")
    ap.add_argument("--logdir", default="out/wide")
    ap.add_argument("--floor", type=float, default=0.0,
                    help="orizzonte minimo in secondi (0 = nessuno)")
    ap.add_argument("--ceil", type=float, default=0.0,
                    help="orizzonte massimo in secondi (0 = nessuno)")
    ap.add_argument("--tlp", default=None,
                    help="file 'nome t_LP' per riga: l'orizzonte diventa "
                         "clamp(mult*t_LP, floor, ceil) invece di factor*tl")
    ap.add_argument("--mult", type=float, default=20.0,
                    help="moltiplicatore di t_LP quando si usa --tlp")
    ap.add_argument("--stats", action="store_true",
                    help="su stderr: quanti run cambiano e quanti log mancano")
    a = ap.parse_args()

    tlp = {}
    if a.tlp:
        for ln in open(a.tlp, errors="replace"):
            p = ln.split()
            if len(p) == 2:
                try:
                    tlp[p[0]] = float(p[1])
                except ValueError:
                    pass

    nmiss = nchg = ntot = nnosol = nlong = 0
    for ln in open(a.results, errors="replace"):
        if not ln.startswith("RES|"):
            continue
        f = ln.rstrip("\n").split("|")
        d = {}
        for p in f[3:]:
            if "=" in p:
                k, v = p.split("=", 1)
                d[k] = v
        name, tag = f[1], f[2]
        if tag in ("filter", "SKIP", "probe") or "seed" not in d:
            continue
        ntot += 1
        try:
            tl, sd = float(d["tl"]), int(d["seed"])
            pri = float(d["primal"])
        except (KeyError, ValueError):
            continue
        if tlp:
            if name not in tlp:
                nmiss += 1
                continue
            tnew = a.mult * tlp[name]
        else:
            tnew = a.factor * tl
        tnew = max(tnew, a.floor)
        if a.ceil > 0:
            tnew = min(tnew, a.ceil)
        if tnew > tl + 1e-9:
            # non si puo' allungare un run gia' fatto: si tiene l'orizzonte
            # vero e si dichiara quante volte e' successo.
            nlong += 1
            tnew = tl
        tr = traj(os.path.join(a.logdir, "%s__%s_s%d.log" % (name, tag, sd)))
        if tr is None:
            nmiss += 1
            continue
        # righe senza z_LP: il pilota `filter` del fattoriale non lo porta, e
        # senza riferimento non si puo' reintegrare il primal integral.
        try:
            zlpv = float(d["zlp"])
        except (KeyError, TypeError, ValueError):
            nmiss += 1
            continue
        pi, best = integral(tr, tnew, zlpv)
        if best is None:
            best = 1e20
            nnosol += 1
        if abs(best - pri) > 1e-9 * max(1.0, abs(pri)):
            nchg += 1
        d["tl"] = "%g" % tnew
        d["primal"] = "%.10g" % best
        d["print"] = "%.6g" % pi
        d["pdint"] = "%.6g" % pi
        # il PI qui sopra copre gia' [0, tnew]: si dichiara time = tl perche'
        # agg_e1.py non gli riaggiunga la coda (pin = pi + gap*(tl - t)).
        d["time"] = "%g" % tnew
        print("RES|%s|%s|%s" % (name, tag,
                                "|".join("%s=%s" % (k, v) for k, v in d.items())))
    if a.stats:
        sys.stderr.write("run: %d, log mancanti: %d, primal cambiato: %d, "
                         "senza soluzione al nuovo orizzonte: %d, "
                         "orizzonte richiesto piu' lungo del run: %d\n"
                         % (ntot, nmiss, nchg, nnosol, nlong))


if __name__ == "__main__":
    main()
