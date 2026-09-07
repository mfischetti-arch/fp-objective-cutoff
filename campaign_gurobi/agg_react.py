#!/usr/bin/env python3
"""agg_react.py -- aggregato della campagna reactive (job26_react.sh).

    python agg_react.py logs/r26_<jobid>_*.log [--primary oh] [--md out.md]

Legge le righe RES, controlla gli invarianti (FATALI su stderr), e stampa:
  T1  istanze risolte per braccio (tutte / pilota found / pilota failed /
      pure / miste), run riusciti, mediana di t_first e n_iter sulle risolte;
  T2  confronto appaiato per istanza contro fgl: esito (risolta / non risolta,
      fgl = mediana dei semi, cioe' risolta se >= 3 semi su 5), test del segno
      esatto, Holm sui bracci confrontati; il braccio --primary e' dichiarato;
  T3  tempo alla prima soluzione dove entrambi riescono (mediana dei semi per
      fgl/hyb), vinte/pari/perse e test del segno;
  T4  dove sta il punto LP quando arriva la prima soluzione (level_first, in
      [0,1] fra z_LP e z_HI) per i bracci reattivi, e i contatori del guinzaglio.
Nessun numero e' scritto a mano: tutto viene dalle righe RES."""
import argparse
import collections
import glob
import math
import statistics
import sys

RAND_ARMS = ("fgl", "hyb")


def parse(paths):
    runs = {}
    for p in paths:
        for line in open(p, errors="replace"):
            if not line.startswith("RES|"):
                continue
            f = line.rstrip("\n").split("|")
            if len(f) < 6 or f[2] == "FAIL":
                print(f"[FAIL] {line.strip()[:160]}", file=sys.stderr)
                continue
            inst, arm = f[1], f[2]
            kv = {}
            for tok in f[3:]:
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    kv[k] = v
            seed = int(kv.get("seed", "0"))
            runs[(inst, arm, seed)] = kv
    return runs


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sign_test(w, l):
    """p bilaterale esatto del test del segno (pareggi esclusi)."""
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def holm(pvals):
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    adj = [0.0] * m
    run = 0.0
    for r, i in enumerate(idx):
        run = max(run, (m - r) * pvals[i])
        adj[i] = min(1.0, run)
    return adj


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--primary", default="oh")
    ap.add_argument("--md", default=None)
    a = ap.parse_args()
    paths = []
    for g in a.logs:
        paths += glob.glob(g)
    runs = parse(paths)
    if not runs:
        sys.exit("nessuna riga RES")

    insts = sorted({k[0] for k in runs})
    arms = sorted({k[1] for k in runs}, key=lambda x: (x not in RAND_ARMS, x))
    seeds = {arm: sorted({k[2] for k in runs if k[1] == arm}) for arm in arms}
    meta = {}
    for (inst, arm, seed), kv in runs.items():
        meta.setdefault(inst, kv)

    # ---------------------------------------------------------------- invarianti
    fatal = 0
    for (inst, arm, seed), kv in runs.items():
        if kv.get("success") == "1" and kv.get("validated") != "1":
            print(f"FATALE: {inst} {arm} s{seed}: success=1 ma validated={kv.get('validated')}",
                  file=sys.stderr); fatal += 1
        if kv.get("rc") not in (None, "0"):
            print(f"FATALE: {inst} {arm} s{seed}: rc={kv.get('rc')}", file=sys.stderr); fatal += 1
        if kv.get("status") in ("error", "nojson"):
            print(f"AVVISO: {inst} {arm} s{seed}: status={kv.get('status')} error={kv.get('error')}",
                  file=sys.stderr)
    missing = 0
    for inst in insts:
        for arm in arms:
            for s in seeds[arm]:
                if (inst, arm, s) not in runs:
                    missing += 1
    print(f"istanze {len(insts)}, bracci {len(arms)}, run {len(runs)}, mancanti {missing}, "
          f"invarianti fatali {fatal}")

    # ------------------------------------------------- esito per (istanza, braccio)
    def ok(kv):
        """Run riuscito = soluzione trovata E rivalidata da Gurobi."""
        return kv.get("success") == "1" and kv.get("validated") == "1"

    def solved(inst, arm):
        """1 se risolta (bracci casuali: mediana dei semi, >= meta' + 1)."""
        ss = [runs[(inst, arm, s)] for s in seeds[arm] if (inst, arm, s) in runs]
        if not ss:
            return None
        k = sum(ok(kv) for kv in ss)
        return int(k * 2 > len(ss)) if len(ss) > 1 else int(k == 1)

    def tfirst(inst, arm):
        ts = [fnum(runs[(inst, arm, s)].get("t_first_feasible")) for s in seeds[arm]
              if (inst, arm, s) in runs]
        ts = [t for t in ts if t is not None]
        if len(seeds[arm]) > 1:
            return med(ts) if len(ts) * 2 > len(seeds[arm]) else None
        return ts[0] if ts else None

    def niter(inst, arm):
        ns = [fnum(runs[(inst, arm, s)].get("n_iter")) for s in seeds[arm]
              if (inst, arm, s) in runs and runs[(inst, arm, s)].get("success") == "1"]
        return med(ns)

    groups = {
        "tutte": insts,
        "pilota found": [i for i in insts if meta[i].get("pilot") == "found"],
        "pilota failed": [i for i in insts if meta[i].get("pilot") == "failed"],
        "pure": [i for i in insts if fnum(meta[i].get("ncont")) == 0],
        "miste": [i for i in insts if (fnum(meta[i].get("ncont")) or 0) > 0],
    }
    out = []
    P = out.append
    P(f"Campagna reactive: {len(insts)} istanze, {len(runs)} run, bracci {' '.join(arms)}; "
      f"fgl/hyb su semi {seeds.get('fgl')}.")
    P("")
    P("**T1.Istanze risolte per braccio.** Risolta = una soluzione ammissibile del modello "
      "originale, rivalidata da Gurobi, entro TL = clamp(20 t_LP, 20, 300) s; per fgl e hyb "
      "l'istanza conta come risolta se lo e' in piu' della meta' dei semi. «run» = coppie "
      "(istanza, seme) riuscite su totali. t_first = mediana (s) alla prima soluzione sulle "
      "risolte; giri = mediana di n_iter sui run riusciti.")
    P("")
    P("| braccio | " + " | ".join(f"{g} ({len(v)})" for g, v in groups.items())
      + " | run | t_first | giri |")
    P("|---|" + "---|" * (len(groups) + 3))
    for arm in arms:
        cells = []
        for g, v in groups.items():
            cells.append(str(sum(solved(i, arm) or 0 for i in v)))
        nrun = sum(1 for k in runs if k[1] == arm)
        nok = sum(1 for k, kv in runs.items() if k[1] == arm and ok(kv))
        ts = [tfirst(i, arm) for i in insts if solved(i, arm)]
        its = [niter(i, arm) for i in insts if solved(i, arm)]
        P(f"| {arm} | " + " | ".join(cells) + f" | {nok}/{nrun} | "
          f"{med(ts):.2f} | {med(its):.0f} |" if ts else
          f"| {arm} | " + " | ".join(cells) + f" | {nok}/{nrun} | - | - |")
    P("")

    # --------------------------------------------------------- T2: esito vs fgl
    ref = "fgl" if "fgl" in arms else arms[0]
    comp = [arm for arm in arms if arm != ref]
    P(f"**T2.Esito appaiato per istanza contro {ref}.** vinte = istanze che il braccio "
      f"risolve e {ref} no; perse = il contrario; pari = stesso esito. p = test del segno "
      f"esatto bilaterale sui discordanti; Holm sui {len(comp)} confronti; il braccio "
      f"primario dichiarato prima del lancio e' `{a.primary}`.")
    P("")
    P("| braccio | vinte | pari | perse | p grezzo | Holm | vinte su pilota failed | perse su pilota found |")
    P("|---|---|---|---|---|---|---|---|")
    rows = []
    for arm in comp:
        w = l = t = 0
        wf = lf = 0
        for i in insts:
            x, y = solved(i, arm), solved(i, ref)
            if x is None or y is None:
                continue
            if x > y:
                w += 1; wf += meta[i].get("pilot") == "failed"
            elif x < y:
                l += 1; lf += meta[i].get("pilot") == "found"
            else:
                t += 1
        rows.append((arm, w, t, l, sign_test(w, l), wf, lf))
    adj = holm([r[4] for r in rows]) if rows else []
    for r, h in zip(rows, adj):
        mark = " **(primario)**" if r[0] == a.primary else ""
        P(f"| {r[0]}{mark} | {r[1]} | {r[2]} | {r[3]} | {r[4]:.4f} | {h:.4f} | {r[5]} | {r[6]} |")
    P("")

    # ----------------------------------------------------- T3: tempo dove entrambi
    P(f"**T3.Tempo alla prima soluzione dove sia il braccio sia {ref} riescono.** "
      f"Per fgl/hyb il tempo e' la mediana dei semi riusciti. vinte = piu' veloce di {ref} "
      f"(oltre il 5 %), pari = entro il 5 %; p = test del segno esatto.")
    P("")
    P("| braccio | comuni | vinte | pari | perse | p | mediana rapporto t/t_ref |")
    P("|---|---|---|---|---|---|---|")
    for arm in comp:
        w = l = t = 0
        ratios = []
        for i in insts:
            if not (solved(i, arm) and solved(i, ref)):
                continue
            ta, tr = tfirst(i, arm), tfirst(i, ref)
            if ta is None or tr is None:
                continue
            ratios.append((ta + 1e-3) / (tr + 1e-3))
            if ta < 0.95 * tr:
                w += 1
            elif ta > 1.05 * tr:
                l += 1
            else:
                t += 1
        n = w + l + t
        P(f"| {arm} | {n} | {w} | {t} | {l} | {sign_test(w, l):.4f} | "
          f"{(med(ratios) if ratios else float('nan')):.2f} |")
    P("")

    # -------------------------------------------- T3b: qualita' dove entrambi
    def zfirst(inst, arm):
        zs = [fnum(runs[(inst, arm, s)].get("z_first_feasible")) for s in seeds[arm]
              if (inst, arm, s) in runs and ok(runs[(inst, arm, s)])]
        zs = [z for z in zs if z is not None]
        if len(seeds[arm]) > 1:
            return med(zs) if len(zs) * 2 > len(seeds[arm]) else None
        return zs[0] if zs else None

    P(f"**T3b. Qualita' della prima soluzione dove sia il braccio sia {ref} riescono.** "
      f"(MF: il cutoff su c'x serve anche a trovare soluzioni buone.) Costo nel senso di "
      f"minimo; per fgl/hyb la mediana dei semi riusciti. migliore = costo sotto quello di "
      f"{ref} oltre 1e-6 relativo; p = test del segno esatto sui discordanti; delta = mediana di "
      f"(z_ref - z)/max(1,|z_ref|), positiva se il braccio e' migliore.")
    P("")
    P("| braccio | comuni | migliore | pari | peggiore | p | delta mediano |")
    P("|---|---|---|---|---|---|---|")
    for arm in comp:
        w = l = t = 0
        deltas = []
        for i in insts:
            if not (solved(i, arm) and solved(i, ref)):
                continue
            za, zr = zfirst(i, arm), zfirst(i, ref)
            if za is None or zr is None:
                continue
            sc = max(1.0, abs(zr))
            deltas.append((zr - za) / sc)
            if za < zr - 1e-6 * sc:
                w += 1
            elif za > zr + 1e-6 * sc:
                l += 1
            else:
                t += 1
        n = w + l + t
        P(f"| {arm} | {n} | {w} | {t} | {l} | {sign_test(w, l):.4f} | "
          f"{(med(deltas) if deltas else float('nan')):+.4f} |")
    P("")

    # ------------------------------------------------ T4: diagnostica del guinzaglio
    P("**T4.Il guinzaglio.** Sui run riusciti: level_first = posizione del punto LP in "
      "[0,1] fra z_LP (0) e z_HI (1) quando arriva la prima soluzione (mediana). Sui run "
      "senza soluzione: status (timelimit = budget esaurito, exhausted = ciclo morto anche "
      "dopo i raffinamenti), mediana di strattoni, sweep, raffinamenti e tempo speso.")
    P("")
    P("| braccio | level_first (risolte) | falliti: timelimit / exhausted / altro | strattoni | sweep | raffinamenti | tempo speso (s) |")
    P("|---|---|---|---|---|---|---|")
    for arm in arms:
        good = [kv for k, kv in runs.items() if k[1] == arm and ok(kv)]
        ko = [kv for k, kv in runs.items() if k[1] == arm and not ok(kv)]
        lv = med([fnum(kv.get("level_first")) for kv in good])
        st = collections.Counter(kv.get("status") for kv in ko)
        other = sum(v for s, v in st.items() if s not in ("timelimit", "exhausted"))
        P(f"| {arm} | {lv if lv is None else round(lv, 3)} | "
          f"{st.get('timelimit', 0)} / {st.get('exhausted', 0)} / {other} | "
          f"{med([fnum(kv.get('n_pull')) for kv in ko])} | "
          f"{med([fnum(kv.get('n_sweep')) for kv in ko])} | "
          f"{med([fnum(kv.get('n_refine')) for kv in ko])} | "
          f"{(med([fnum(kv.get('time_total')) for kv in ko]) or 0):.1f} |")
    P("")
    czero = [i for i in insts if meta[i].get("c_zero") == "1"
             or any(kv.get("c_zero") == "1" for k, kv in runs.items() if k[0] == i)]
    P(f"Istanze con obiettivo nullo (nessun guinzaglio possibile): {len(czero)} "
      f"{czero[:10]}")

    text = "\n".join(out)
    print(text)
    if a.md:
        open(a.md, "w", encoding="utf-8").write(text + "\n")


if __name__ == "__main__":
    main()
