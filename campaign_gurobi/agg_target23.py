#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregatore dei log della campagna "target" su GUROBI (job23_gurobi.sh + fp_target.py).

Un log per task SLURM, logs/t23_<jobid>_<task>.log. Righe utili:

  RES|<inst>|<mode>|<coppie chiave=valore>     un run (mode = naive|test|completion)
  RES|<inst>|SKIP|<motivo>                     istanza non eleggibile
  RES|<inst>|FAIL|<motivo>                     task morto prima dei bracci
  == [<i>] <inst> eleggibile: zinc=.. zlp=..   ricognizione (fase recon)
  == [<i>] <inst> set=.. bench=.. nodo=..      intestazione del task

Le coppie chiave=valore sono lette in modo GENERICO (un dict per riga): l'ordine e
il numero dei campi non contano, e una chiave nuova (p.es. `validated`) non rompe
nulla -- se manca, e' semplicemente assente.

Sottocomandi:
  recon   quante istanze sono eleggibili e perche' le altre no
  tune    scelta di WT e WC dalle righe set=tune
  eval    tabelle, confronti appaiati e invarianti sulle righe set=eval

Solo stdlib + numpy (il venv del cluster e' minimale): il test del segno binomiale
esatto e' scritto a mano con math.comb.
"""

import argparse
import glob
import math
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np

ARMS = ("naive", "test", "completion")
GRID_ARMS = ("test", "completion")
SKIP_REASONS = ("unsupported", "nopilot", "slow", "at_best", "best_below_lp", "zero_gap")
NA = "-"
NAN = float("nan")

# tolleranza relativa sui tempi nel confronto appaiato per istanza
TIME_TOL = 0.05
# tolleranza relativa sulle identita' numeriche (U, U', tl)
EPS = 1e-9


# --------------------------------------------------------------------- utilita'

def fnum(kv, key):
    """Valore numerico di una chiave, o None se assente/'-'/non numerica."""
    v = kv.get(key)
    if v is None:
        return None
    v = v.strip()
    if v in ("", NA, "None", "nan"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def inum(kv, key):
    v = fnum(kv, key)
    return None if v is None else int(round(v))


def med(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return NAN if not xs else float(np.median(np.asarray(xs, dtype=float)))


def f3(x, width=10):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return NA.rjust(width)
    return ("%.3f" % x).rjust(width)


def close(a, b, eps=EPS):
    if a is None or b is None:
        return False
    scale = max(1.0, abs(a), abs(b))
    return abs(a - b) <= eps * scale


def binom_sign_p(k, n):
    """Test del segno binomiale ESATTO a due code: X ~ Bin(n, 1/2), osservati k."""
    if n <= 0:
        return 1.0
    tot = float(1 << n) if n < 1024 else 2.0 ** n
    lower = sum(math.comb(n, i) for i in range(0, k + 1)) / tot
    upper = sum(math.comb(n, i) for i in range(k, n + 1)) / tot
    return min(1.0, 2.0 * min(lower, upper))


def holm(pvals):
    """Correzione di Holm-Bonferroni, restituita nell'ordine di ingresso."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * pvals[i])
        adj[i] = min(1.0, running)
    return adj


# ---------------------------------------------------------------------- parsing

RE_HDR = re.compile(r"^==\s*\[(\d+)\]\s+(\S+)\s+(.*)$")


def parse_kv(tokens):
    """Coppie chiave=valore -> dict. Il valore puo' contenere '=' (error=...)."""
    out = {}
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            k = k.strip()
            if k:
                out[k] = v.strip()
    return out


class Row(object):
    """Una riga RES di run, gia' decodificata."""

    __slots__ = ("inst", "mode", "kv", "src")

    def __init__(self, inst, mode, kv, src):
        self.inst = inst
        self.mode = mode
        self.kv = kv
        self.src = src

    # accessi comodi -----------------------------------------------------
    @property
    def w(self):
        v = fnum(self.kv, "w")
        return 0.0 if v is None else v

    @property
    def w_str(self):
        return self.kv.get("w", "0")

    @property
    def seed(self):
        return inum(self.kv, "seed")

    @property
    def dataset(self):
        return self.kv.get("set", NA)

    @property
    def bench(self):
        v = inum(self.kv, "bench")
        return 0 if v is None else v

    @property
    def ok(self):
        """Successo = target_ok E, se la chiave c'e', validated (la conferma di
        Gurobi a tolleranza assoluta). Un target_ok=1 con validated=0 e' un falso
        successo (tolleranza relativa di feasible() troppo larga su righe con RHS
        enorme: glass4, 03/09/2026) e vale come fallimento: viene elencato a parte."""
        v = inum(self.kv, "target_ok")
        if v is None or not v:
            return 0
        w = inum(self.kv, "validated")
        return 0 if (w is not None and w == 0) else 1

    @property
    def downgraded(self):
        v = inum(self.kv, "target_ok")
        w = inum(self.kv, "validated")
        return bool(v) and (w is not None and w == 0)

    @property
    def tl(self):
        return fnum(self.kv, "tl")

    @property
    def tts(self):
        return fnum(self.kv, "time_to_success")

    @property
    def t_cens(self):
        """Tempo censurato: time_to_success se successo, altrimenti il TL."""
        tl = self.tl
        if self.ok:
            t = self.tts
            if t is None:
                t = fnum(self.kv, "time_total")
            if t is None:
                t = tl
            return t
        return tl

    @property
    def key(self):
        return (self.inst, self.mode, round(self.w, 12), self.seed)


class Logs(object):
    """Tutto quel che serve, estratto dai file di log."""

    def __init__(self):
        self.rows = []                      # righe RES di run
        self.skips = []                     # (inst, motivo)
        self.fails = []                     # (inst, motivo)
        self.elig = {}                      # inst -> dict della riga "eleggibile"
        self.meta = {}                      # inst -> {'set':..,'bench':..} da intestazione
        self.a_seen = set()
        self.n_files = 0
        self.n_lines = 0


def expand(paths):
    """Espande glob e cartelle (PowerShell non espande i glob al posto nostro)."""
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "*.log"))))
        elif any(c in p for c in "*?["):
            out.extend(sorted(glob.glob(p)))
        else:
            out.append(p)
    seen, uniq = set(), []
    for p in out:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            uniq.append(p)
    return uniq


def read_logs(paths, a_filter=None):
    L = Logs()
    files = expand(paths)
    if not files:
        sys.exit("nessun file di log: controlla il pattern (i glob vanno espansi da questo script, "
                 "ma la cartella deve esistere)")
    for path in files:
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError as e:
            print("== log illeggibile, saltato: %s (%s)" % (path, e))
            continue
        L.n_files += 1
        base = os.path.basename(path)
        with fh:
            for ln, line in enumerate(fh, 1):
                line = line.strip()
                L.n_lines += 1
                if not line:
                    continue
                if line.startswith("RES|"):
                    parts = line.split("|")
                    if len(parts) < 3:
                        continue
                    inst, mode = parts[1], parts[2]
                    if mode == "SKIP":
                        L.skips.append((inst, parts[3] if len(parts) > 3 else "?"))
                    elif mode == "FAIL":
                        L.fails.append((inst, parts[3] if len(parts) > 3 else "?"))
                    else:
                        kv = parse_kv(parts[3:])
                        if "a" in kv:
                            L.a_seen.add(kv["a"])
                        L.rows.append(Row(inst, mode, kv, "%s:%d" % (base, ln)))
                    continue
                if line.startswith("=="):
                    m = RE_HDR.match(line)
                    if not m:
                        continue
                    inst, rest = m.group(2), m.group(3)
                    if rest.startswith("eleggibile:"):
                        L.elig[inst] = parse_kv(rest[len("eleggibile:"):].split())
                    elif "bench=" in rest:
                        kv = parse_kv(rest.split())
                        d = L.meta.setdefault(inst, {})
                        for k in ("set", "bench"):
                            if k in kv:
                                d[k] = kv[k]
    if a_filter is not None:
        keep = []
        for r in L.rows:
            v = fnum(r.kv, "a")
            if v is not None and close(v, a_filter, 1e-9):
                keep.append(r)
        L.rows = keep
    return L


def warn_multi_a(L, a_filter):
    if len(L.a_seen) > 1 and a_filter is None:
        print("!! ATTENZIONE: piu' di un valore di a nei log: %s -- i bracci non sono confrontabili."
              % ", ".join(sorted(L.a_seen)))
        print("!! usa --a <valore> per filtrare una sola campagna.")
        print("")


def bench_of(L, inst):
    """bench dell'istanza: dalle righe RES se ci sono, altrimenti dall'intestazione."""
    for r in L.rows:
        if r.inst == inst:
            return r.bench
    v = L.meta.get(inst, {}).get("bench")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ sottocomando recon

def cmd_recon(L, args):
    print("RICOGNIZIONE  (%d file, %d righe lette)" % (L.n_files, L.n_lines))
    print("")
    elig = sorted(L.elig)
    skip_by = defaultdict(list)
    for inst, why in L.skips:
        skip_by[why].append(inst)
    fail_by = defaultdict(list)
    for inst, why in L.fails:
        fail_by[why].append(inst)

    def nbench(names):
        b = [bench_of(L, n) for n in names]
        return sum(1 for x in b if x == 1), sum(1 for x in b if x is None)

    seen = set(elig) | {i for i, _ in L.skips} | {i for i, _ in L.fails} | set(L.meta)
    eb, eu = nbench(elig)
    print("istanze viste nei log ......... %4d" % len(seen))
    print("ELEGGIBILI .................... %4d   (benchmark=%d%s)"
          % (len(elig), eb, ", bench ignoto=%d" % eu if eu else ""))
    print("")
    tot_skip = len(L.skips)
    print("SKIP (non eleggibili) ......... %4d" % tot_skip)
    order = list(SKIP_REASONS) + sorted(set(skip_by) - set(SKIP_REASONS))
    for why in order:
        names = skip_by.get(why, [])
        if not names:
            continue
        b, _ = nbench(names)
        print("    %-16s %4d   (benchmark=%d)" % (why, len(names), b))
    print("")
    print("FAIL (task morto) ............. %4d" % len(L.fails))
    for why in sorted(fail_by):
        print("    %-16s %4d" % (why, len(fail_by[why])))
    dup_skip = [n for n, c in Counter(i for i, _ in L.skips).items() if c > 1]
    if dup_skip:
        print("")
        print("!! %d istanze con piu' di una riga SKIP (log rilanciati?): %s"
              % (len(dup_skip), ", ".join(sorted(dup_skip)[:8])))

    if args.list:
        print("")
        print("--- ELENCHI ---")
        print("")
        print("eleggibili (%d):" % len(elig))
        print_names(elig)
        for why in order:
            names = skip_by.get(why, [])
            if names:
                print("")
                print("SKIP %s (%d):" % (why, len(names)))
                print_names(sorted(set(names)))
        for why in sorted(fail_by):
            print("")
            print("FAIL %s (%d):" % (why, len(fail_by[why])))
            print_names(sorted(set(fail_by[why])))
    return 0


def print_names(names, per_line=4, width=24):
    for i in range(0, len(names), per_line):
        print("    " + "".join(n.ljust(width) for n in names[i:i + per_line]).rstrip())


# ------------------------------------------------------------------- sottocomando tune

def per_instance(rows):
    """rows -> {inst: [Row, ...]}"""
    d = defaultdict(list)
    for r in rows:
        d[r.inst].append(r)
    return d


def cell_rows(rows, arm, w):
    """Righe della cella (braccio, w) della griglia: w=0 e' il naive, per entrambi."""
    if close(w, 0.0):
        return [r for r in rows if r.mode == "naive"]
    return [r for r in rows if r.mode == arm and close(r.w, w, 1e-12)]


def cell_stats(rows):
    """Statistiche di una cella (istanza x seme)."""
    by_inst = per_instance(rows)
    n_pairs = len({(r.inst, r.seed) for r in rows})
    # successi contati per COPPIA (istanza, seme), non per riga: se una cella e'
    # stata rifatta (righe duplicate, p.es. il naive rilanciato con una griglia
    # extra) una coppia riuscita vale uno, non due
    n_ok = len({(r.inst, r.seed) for r in rows if r.ok})
    tts_ok = [r.tts for r in rows if r.ok and r.tts is not None]
    ist_ok = 0
    med_cens_per_inst = []
    for inst, rr in by_inst.items():
        vals = [r.ok for r in rr]
        if med(vals) > 0.5:
            ist_ok += 1
        med_cens_per_inst.append(med([r.t_cens for r in rr]))
    return {
        "n_rows": len(rows),
        "n_pairs": n_pairs,
        "n_ok": n_ok,
        "n_inst": len(by_inst),
        "ist_ok": ist_ok,
        "med_tts": med(tts_ok),
        "med_cens": med(med_cens_per_inst),
    }


def cmd_tune(L, args):
    rows = [r for r in L.rows if r.dataset == "tune"]
    if not rows:
        sys.exit("nessuna riga set=tune nei log indicati")
    print("TARATURA  (righe set=tune: %d; istanze: %d; semi: %s)"
          % (len(rows), len({r.inst for r in rows}),
             ",".join(str(s) for s in sorted({r.seed for r in rows if r.seed is not None}))))
    print("")

    grid = {}
    for arm in GRID_ARMS:
        ws = sorted({round(r.w, 12) for r in rows if r.mode == arm and r.w > 0})
        grid[arm] = [0.0] + ws
    wstr = {}
    for r in rows:
        wstr.setdefault(round(r.w, 12), r.w_str)
    wstr.setdefault(0.0, "0")

    choice = {}
    for arm in GRID_ARMS:
        print("BRACCIO %-10s  (w=0 e' il naive, incluso come punto della griglia)" % arm)
        print("    %-8s %7s %7s %7s %9s %11s %11s"
              % ("w", "righe", "ok", "coppie", "ist>=3/5", "med_tts_ok", "med_t_cens"))
        best = None
        for w in grid[arm]:
            st = cell_stats(cell_rows(rows, arm, w))
            print("    %-8s %7d %7d %7d %9d %s %s"
                  % (wstr.get(round(w, 12), "%.3g" % w), st["n_rows"], st["n_ok"], st["n_pairs"],
                     st["ist_ok"], f3(st["med_tts"], 11), f3(st["med_cens"], 11)))
            cand = (st["n_ok"], -(st["med_cens"] if not math.isnan(st["med_cens"]) else 1e18), w)
            if best is None or cand > best[0]:
                best = (cand, w, st)
        choice[arm] = best
        w, st = best[1], best[2]
        tag = " (= naive: questo braccio non ha fascia)" if close(w, 0.0) else ""
        print("    scelta: w=%s  con %d coppie riuscite, mediana del tempo censurato %s%s"
              % (wstr.get(round(w, 12), "%.3g" % w), st["n_ok"], f3(st["med_cens"], 1).strip(), tag))
        print("")

    check_grid(rows, grid, wstr)

    wt = wstr.get(round(choice["test"][1], 12), "%.3g" % choice["test"][1])
    wc = wstr.get(round(choice["completion"][1], 12), "%.3g" % choice["completion"][1])
    print("")
    print("WT=%s WC=%s" % (wt, wc))
    return 0


def check_grid(rows, grid, wstr):
    """Ogni (istanza, seme, braccio, w) deve avere UNA riga: duplicati e buchi."""
    insts = sorted({r.inst for r in rows})
    seeds = sorted({r.seed for r in rows if r.seed is not None})
    cells = [("naive", 0.0)]
    for arm in GRID_ARMS:
        for w in grid[arm]:
            if not close(w, 0.0):
                cells.append((arm, w))
    cnt = Counter(r.key for r in rows)
    dups, holes = [], []
    for inst in insts:
        for sd in seeds:
            for mode, w in cells:
                k = (inst, mode, round(w, 12), sd)
                c = cnt.get(k, 0)
                if c == 0:
                    holes.append(k)
                elif c > 1:
                    dups.append((k, c))
    extra = [k for k in cnt
             if k[0] in insts and (k[1], k[2]) not in {(m, round(w, 12)) for m, w in cells}]
    exp = len(insts) * len(seeds) * len(cells)
    print("CONTROLLO GRIGLIA: attese %d righe (%d istanze x %d semi x %d celle), viste %d"
          % (exp, len(insts), len(seeds), len(cells), len(rows)))
    if dups:
        print("  !! DUPLICATI (%d):" % len(dups))
        for (inst, mode, w, sd), c in dups[:20]:
            print("       %-24s %-11s w=%-6s seed=%-3s righe=%d"
                  % (inst, mode, wstr.get(w, "%.3g" % w), sd, c))
        if len(dups) > 20:
            print("       ... e altri %d" % (len(dups) - 20))
    if holes:
        print("  !! BUCHI (%d):" % len(holes))
        for (inst, mode, w, sd) in holes[:20]:
            print("       %-24s %-11s w=%-6s seed=%s"
                  % (inst, mode, wstr.get(w, "%.3g" % w), sd))
        if len(holes) > 20:
            print("       ... e altri %d" % (len(holes) - 20))
    if extra:
        print("  !! CELLE FUORI GRIGLIA (%d): %s"
              % (len(extra), ", ".join("%s/%s/w=%g/s=%s" % k for k in extra[:6])))
    if not dups and not holes and not extra:
        print("  griglia completa: nessun duplicato, nessun buco.")


# ------------------------------------------------------------------- sottocomando eval

def arm_w(rows, arm):
    ws = sorted({round(r.w, 12) for r in rows if r.mode == arm})
    return ws


def inst_summary(rows_of_inst):
    """Riassunto per (istanza, braccio): esito e tempi mediani sui semi."""
    ok = [r.ok for r in rows_of_inst]
    cens = [r.t_cens for r in rows_of_inst]
    tts = [r.tts for r in rows_of_inst if r.ok and r.tts is not None]
    return {
        "n_seed": len(rows_of_inst),
        "n_ok": sum(ok),
        "outcome": med(ok),
        "med_cens": med(cens),
        "med_tts": med(tts),
    }


def build_summary(rows):
    """{(inst, arm): riassunto} + anagrafica per istanza."""
    by = defaultdict(list)
    for r in rows:
        by[(r.inst, r.mode)].append(r)
    summ = {k: inst_summary(v) for k, v in by.items()}
    info = {}
    for r in rows:
        d = info.setdefault(r.inst, {"bench": r.bench, "n_cont": None, "n_bin": None,
                                     "tl": r.tl, "U": fnum(r.kv, "U"), "zlp": fnum(r.kv, "zlp"),
                                     "zinc": fnum(r.kv, "zinc"), "zbest": fnum(r.kv, "zbest")})
        if d["n_cont"] is None:
            d["n_cont"] = inum(r.kv, "n_cont")
        if d["n_bin"] is None:
            d["n_bin"] = inum(r.kv, "n_bin")
    return summ, info


def select(info, family, kind):
    out = []
    for inst, d in info.items():
        if family == "primario" and d["bench"] != 1:
            continue
        if family == "secondario" and d["bench"] != 0:
            continue
        nc = d["n_cont"]
        if kind == "puro" and not (nc is not None and nc == 0):
            continue
        if kind == "misto" and not (nc is not None and nc > 0):
            continue
        out.append(inst)
    return sorted(out)


def cmd_eval(L, args):
    rows = [r for r in L.rows if r.dataset == "eval"]
    if not rows:
        sys.exit("nessuna riga set=eval nei log indicati")
    bad = check_invariants(rows)
    if bad:
        print("INVARIANTI VIOLATE: l'aggregato NON e' affidabile, mi fermo.")
        print("")
        for msg in bad[:40]:
            print("  !! " + msg)
        if len(bad) > 40:
            print("  ... e altre %d violazioni" % (len(bad) - 40))
        return 1
    dg = [r for r in rows if r.downgraded]
    if dg:
        print("DECLASSATI a fallimento (target_ok=1 ma Gurobi NON conferma il punto, validated=0): %d run su %d successi dichiarati"
              % (len(dg), sum(1 for r in rows if inum(r.kv, "target_ok"))))
        for r in dg[:20]:
            print("  !! %s/%s/seed=%s  best_obj=%s U=%s [%s]" % (r.inst, r.mode, r.seed, r.kv.get("best_obj", NA), r.kv.get("U", NA), r.src))
        print("")

    summ, info = build_summary(rows)
    ws = {a: arm_w(rows, a) for a in ARMS}
    print("VALUTAZIONE  (righe set=eval: %d; istanze: %d; semi: %s)"
          % (len(rows), len(info),
             ",".join(str(s) for s in sorted({r.seed for r in rows if r.seed is not None}))))
    print("bracci: " + "  ".join("%s w=%s" % (a, ",".join("%g" % w for w in ws[a]) or NA)
                                 for a in ARMS))
    print("invarianti: tutte verificate.")
    print("")
    print_eval_tables(summ, info)
    print("")
    print_paired(summ, info)
    if args.csv:
        write_csv(args.csv, summ, info, rows)
        print("")
        print("CSV scritto in %s (una riga per istanza x braccio)" % args.csv)
    return 0


def print_eval_tables(summ, info):
    print("(a) ESITI PER BRACCIO   [ist_ok = istanze con mediana di target_ok = 1, cioe' >= 3/5 semi]")
    print("")
    hdr = ("%-11s %-6s %-11s %6s %7s %11s %11s %11s"
           % ("famiglia", "tipo", "braccio", "N_ist", "ist_ok", "coppie_ok", "med_t_cens", "med_tts_ok"))
    print(hdr)
    print("-" * len(hdr))
    for family in ("primario", "secondario", "tutte"):
        for kind in ("tutte", "puro", "misto"):
            insts = select(info, family, kind)
            if not insts:
                continue
            for arm in ARMS:
                ss = [summ[(i, arm)] for i in insts if (i, arm) in summ]
                if not ss:
                    continue
                n_ok = sum(s["n_ok"] for s in ss)
                n_pair = sum(s["n_seed"] for s in ss)
                ist_ok = sum(1 for s in ss if s["outcome"] > 0.5)
                print("%-11s %-6s %-11s %6d %7d %11s %s %s"
                      % (family, kind, arm, len(ss), ist_ok, "%d/%d" % (n_ok, n_pair),
                         f3(med([s["med_cens"] for s in ss]), 11),
                         f3(med([s["med_tts"] for s in ss]), 11)))
            print("")


def compare_inst(a, b):
    """+1 se il braccio A e' meglio, -1 se B, 0 pareggio. Esito, poi tempo (+-5%)."""
    if a["outcome"] > b["outcome"] + 1e-12:
        return 1
    if b["outcome"] > a["outcome"] + 1e-12:
        return -1
    ta, tb = a["med_cens"], b["med_cens"]
    if ta is None or tb is None or math.isnan(ta) or math.isnan(tb):
        return 0
    if abs(ta - tb) <= TIME_TOL * max(abs(ta), abs(tb), 1e-12):
        return 0
    return 1 if ta < tb else -1


def print_paired(summ, info):
    print("(b) CONFRONTI APPAIATI PER ISTANZA   [W = vittorie del PRIMO braccio; esito, poi")
    print("    tempo censurato mediano con tolleranza relativa del 5%; test del segno esatto]")
    print("")
    pairs = (("naive", "test"), ("naive", "completion"), ("test", "completion"))
    res, praw = [], []
    for family in ("primario", "secondario"):
        insts = select(info, family, "tutte")
        for A, B in pairs:
            both = [i for i in insts if (i, A) in summ and (i, B) in summ]
            w = l = t = 0
            for i in both:
                c = compare_inst(summ[(i, A)], summ[(i, B)])
                if c > 0:
                    w += 1
                elif c < 0:
                    l += 1
                else:
                    t += 1
            n = w + l
            p = binom_sign_p(w, n)
            res.append((family, A, B, len(both), w, l, t, n, p))
            praw.append(p)
    padj = holm(praw) if praw else []
    hdr = ("%-11s %-24s %6s %5s %5s %5s %6s %10s %10s"
           % ("famiglia", "confronto", "N_ist", "W", "L", "T", "n_eff", "p_grezzo", "p_Holm"))
    print(hdr)
    print("-" * len(hdr))
    for (family, A, B, nb, w, l, t, n, p), pa in zip(res, padj):
        print("%-11s %-24s %6d %5d %5d %5d %6d %s %s"
              % (family, "%s vs %s" % (A, B), nb, w, l, t, n, f3(p, 10), f3(pa, 10)))
    print("")
    print("Holm su %d test (3 confronti x 2 famiglie)." % len(res))


# ---------------------------------------------------------------- invarianti (fatali)

def check_invariants(rows):
    bad = []
    by_inst = per_instance(rows)
    for inst in sorted(by_inst):
        rr = by_inst[inst]
        # U identico fra i bracci della stessa istanza
        us = {round(u, 12) for u in (fnum(r.kv, "U") for r in rr) if u is not None}
        if len(us) > 1:
            bad.append("%s: U diverso fra i bracci (%s)"
                       % (inst, ", ".join("%.12g" % u for u in sorted(us))))
        elif not us:
            bad.append("%s: nessuna riga con U" % inst)
        # tl identico fra i bracci
        tls = {round(t, 9) for t in (r.tl for r in rr) if t is not None}
        if len(tls) > 1:
            bad.append("%s: tl diverso fra i bracci (%s)"
                       % (inst, ", ".join("%g" % t for t in sorted(tls))))
        for r in rr:
            U, zlp, Up = fnum(r.kv, "U"), fnum(r.kv, "zlp"), fnum(r.kv, "Uprime")
            if U is not None and zlp is not None and U < zlp - EPS * max(1.0, abs(U), abs(zlp)):
                bad.append("%s/%s/seed=%s: U=%.12g < zlp=%.12g [%s]"
                           % (inst, r.mode, r.seed, U, zlp, r.src))
            if U is not None and zlp is not None and Up is not None:
                want = U - r.w * (U - zlp)
                if not close(Up, want):
                    bad.append("%s/%s/seed=%s: Uprime=%.12g != U-w(U-zlp)=%.12g (w=%s) [%s]"
                               % (inst, r.mode, r.seed, Up, want, r.w_str, r.src))
            if r.kv.get("status") == "error":
                bad.append("%s/%s/seed=%s: status=error (%s) [%s]"
                           % (inst, r.mode, r.seed, r.kv.get("error", NA)[:60], r.src))
            # target_ok=1 con validated=0 NON e' fatale: Row.ok lo declassa a
            # fallimento e la valutazione lo elenca (vedi stampa dopo gli invarianti)
        # esattamente i tre bracci per (istanza, seme)
        by_seed = defaultdict(Counter)
        for r in rr:
            by_seed[r.seed][r.mode] += 1
        for sd in sorted(by_seed, key=lambda x: (x is None, x)):
            c = by_seed[sd]
            missing = [a for a in ARMS if c[a] == 0]
            dup = [a for a in ARMS if c[a] > 1]
            other = [m for m in c if m not in ARMS]
            if missing:
                bad.append("%s/seed=%s: bracci mancanti: %s" % (inst, sd, ",".join(missing)))
            if dup:
                bad.append("%s/seed=%s: bracci duplicati: %s"
                           % (inst, sd, ",".join("%s x%d" % (a, c[a]) for a in dup)))
            if other:
                bad.append("%s/seed=%s: bracci inattesi: %s" % (inst, sd, ",".join(other)))
    return bad


# ---------------------------------------------------------------------------- csv

def write_csv(path, summ, info, rows):
    wof = defaultdict(set)
    for r in rows:
        wof[(r.inst, r.mode)].add(r.w_str)
    cols = ("inst", "arm", "w", "bench", "n_bin", "n_cont", "n_seed", "n_ok",
            "outcome", "med_t_cens", "med_tts_ok", "U", "zlp", "zinc", "zbest", "tl")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(cols) + "\n")
        for inst in sorted(info):
            d = info[inst]
            for arm in ARMS:
                s = summ.get((inst, arm))
                if s is None:
                    continue

                def g(x):
                    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else \
                        ("%.6g" % x if isinstance(x, float) else str(x))
                fh.write(",".join([
                    inst, arm, "|".join(sorted(wof[(inst, arm)])), g(d["bench"]),
                    g(d["n_bin"]), g(d["n_cont"]), g(s["n_seed"]), g(s["n_ok"]),
                    g(s["outcome"]), g(s["med_cens"]), g(s["med_tts"]),
                    g(d["U"]), g(d["zlp"]), g(d["zinc"]), g(d["zbest"]), g(d["tl"]),
                ]) + "\n")


# --------------------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="agg_target23.py",
        description="Aggregatore dei log della campagna target su Gurobi (job23_gurobi.sh).")
    p.add_argument("--a", type=float, default=None,
                   help="filtra le righe sul campo a (default: tutte, con avviso se piu' d'uno)")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("recon", help="istanze eleggibili e motivi degli SKIP/FAIL")
    q.add_argument("logs", nargs="+")
    q.add_argument("--list", action="store_true", help="elenca i nomi per motivo")

    q = sub.add_parser("tune", help="scelta di WT e WC dalle righe set=tune")
    q.add_argument("logs", nargs="+")

    q = sub.add_parser("eval", help="tabelle, confronti appaiati e invarianti (set=eval)")
    q.add_argument("logs", nargs="+")
    q.add_argument("--csv", default=None, help="scrive una riga per (istanza, braccio)")

    args = p.parse_args(argv)
    L = read_logs(args.logs, args.a)
    warn_multi_a(L, args.a)
    if args.a is not None:
        print("filtro a=%g: %d righe RES di run" % (args.a, len(L.rows)))
        print("")
    return {"recon": cmd_recon, "tune": cmd_tune, "eval": cmd_eval}[args.cmd](L, args)


if __name__ == "__main__":
    sys.exit(main())
