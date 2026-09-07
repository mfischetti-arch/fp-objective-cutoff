"""Quanto prima arriva il primo arrotondato ammissibile e migliorante SOPRA il cutoff (quello
che il test accetta e la pompa a scatola chiusa scarta) rispetto al primo punto SOTTO il cutoff
(l'unico che la pompa a scatola chiusa consegna). I numeri del capoverso di §2 dopo la Figura 2.

Dati: censimento from-scratch a lambda_v2 = 0.5, seme 0 da grid/ e semi 1-2 da grid_s12/ (a 0.5
le due convenzioni dei nomi coincidono), csv per giro + json (z_ref, ub). Classi come in fp.py
(TOL = 1e-6): perso = ammissibile, c'x > U, c'x < z_ref; sotto U = ammissibile, c'x <= U.
Per istanza: mediana sui semi del giro (e del tempo) del primo evento di ciascun tipo.

Uso: python chk_moat_time.py            (da fpc/; stampa la tabella per istanza e i riepiloghi)
"""
import csv, glob, json, os, statistics as st

here = os.path.dirname(os.path.abspath(__file__))
TOL = 1e-6
DETAIL = ("scpnrh3", "cap6000", "harp2", "neos-1337307", "seymour", "glass-sc")

runs = {}
for d, seeds in (("grid", ("0",)), ("grid_s12", ("1", "2"))):
    for p in glob.glob(os.path.join(here, d, "*__cutoff_lam0.5_s[012].csv")):
        b = os.path.basename(p)
        inst, s = b.split("__")[0], b[-5]
        if s not in seeds:
            continue
        js = json.load(open(p[:-4] + ".json"))
        zr, U = js["z_ref"], js["ub"]
        band = zr - U
        rows = [r for r in csv.DictReader(open(p)) if r["ub_free"] == "0"]
        lost1 = acc1 = None
        best_before = None
        for r in rows:
            if r["feas"] != "1":
                continue
            cz = float(r["cz_round"]); it = int(r["it"]); t = float(r["t"])
            if cz <= U + TOL:
                if acc1 is None:
                    acc1 = (it, t)
            elif cz < zr - TOL:
                pos = (cz - U) / band
                if lost1 is None:
                    lost1 = (it, t, pos)
                if acc1 is None and (best_before is None or pos < best_before):
                    best_before = pos
        runs[(inst, s)] = dict(lost1=lost1, acc1=acc1, best_before=best_before, iters=len(rows))


def med(v):
    return st.median(v) if v else float("nan")


insts = sorted({k[0] for k in runs})
print(f"{'istanza':22s} {'semi':>4s} | {'1o perso: giro':>14s} {'pos':>6s} {'s':>6s} | "
      f"{'1o sotto U: giro':>16s} {'s':>6s} | {'mai sotto U':>11s} {'miglior pos prima':>17s}")
agg = []
for i in insts:
    R = [runs[(i, s)] for s in "012" if (i, s) in runs]
    L = [r["lost1"] for r in R if r["lost1"]]
    A = [r["acc1"] for r in R if r["acc1"]]
    never = sum(1 for r in R if r["acc1"] is None)
    bb = [r["best_before"] for r in R if r["best_before"] is not None]
    gl, tl, pl = med([x[0] for x in L]), med([x[1] for x in L]), med([x[2] for x in L])
    ga, ta = med([x[0] for x in A]), med([x[1] for x in A])
    print(f"{i:22s} {len(R):4d} | {gl:14.0f} {pl:6.3f} {tl:6.1f} | {ga:16.0f} {ta:6.1f} | "
          f"{never:>4d}/{len(R):<6d} {med(bb):17.3f}")
    agg.append(dict(inst=i, gl=gl, ga=ga, never=never, n=len(R), nl=len(L)))

both = [a for a in agg if a["gl"] == a["gl"] and a["ga"] == a["ga"]]
print(f"\nistanze: {len(agg)}; con un perso in almeno un seme: {sum(1 for a in agg if a['nl'])}")
print(f"istanze con entrambi gli eventi: {len(both)}; il primo perso precede il primo sotto U: "
      f"{sum(1 for a in both if a['gl'] < a['ga'])}")
print(f"rapporto giri (primo sotto U / primo perso), mediana sulle istanze con entrambi: "
      f"{st.median([a['ga'] / max(a['gl'], 1) for a in both]):.1f}")
never_all = [a["inst"] for a in agg if a["never"] == a["n"]]
print(f"istanze mai sotto U in nessun seme: {len(never_all)} ({', '.join(never_all)}); "
      f"di queste con un perso: {sum(1 for a in agg if a['never'] == a['n'] and a['nl'])}")

print("\ndettaglio per seme (giro, posizione nella fascia, secondi):")
for i in DETAIL:
    for s in "012":
        r = runs.get((i, s))
        if not r:
            continue
        l, a = r["lost1"], r["acc1"]
        ls = f"perso al giro {l[0]} (pos {l[2]:.3f}, {l[1]:.1f} s)" if l else "nessun perso"
        as_ = f"sotto U al giro {a[0]} ({a[1]:.1f} s)" if a else f"mai sotto U in {r['iters']} giri"
        bb = f", miglior perso prima: {r['best_before']:.3f}" if r["best_before"] is not None else ""
        print(f"  {i:14s} seme {s}: {ls}; {as_}{bb}")
