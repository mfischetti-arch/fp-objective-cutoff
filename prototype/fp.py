#!/usr/bin/env python3
"""
Feasibility Pump con cutoff sull'obiettivo — versione strumentata.

Scopo: NON battere nessuno. Misurare che cosa fa il vincolo c'x <= UB alle due
sequenze del pump (l'iterato LP e il suo arrotondamento), e contare quante volte
un arrotondamento AMMISSIBILE viene scartato solo perche' viola il cutoff.

Convenzione di segno (fissata da MF, 31/08/2026):

    d = c'x - UB     positivo  =  dalla parte sbagliata (viola il cutoff)

Attese: d ~ 0 sull'iterato LP quando il cutoff e' attivo (d < 0 se e' lasco),
d > 0 sull'arrotondamento, e questo secondo d NON scende a zero.

Solo istanze con tutte le variabili binarie (--allow-cont per accettare anche
continue: entrano nei vincoli ma non nella distanza, e in quel caso il test di
ammissibilita' dell'arrotondamento e' incompleto e viene marcato come tale).

Riferimenti di impianto:
  Fischetti, Glover, Lodi (2005)      il pump con obiettivo e il cutoff
  Fischetti, Salvagnin (FP 2.0)       perturbazione, restart
  Achterberg, Berthold (2007)         alpha geometrico, entrambi i termini
                                      normalizzati in norma euclidea
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import gurobipy as gp
from gurobipy import GRB

TOL = 1e-6


# --------------------------------------------------------------------------
# lettura e preparazione
# --------------------------------------------------------------------------

def load(path, allow_cont, threads=1, method=1):
    """Legge il modello, lo normalizza a minimizzazione, ne estrae il
    rilassamento continuo e le matrici per il test di ammissibilita'."""
    env = gp.Env(params={"OutputFlag": 0})
    m = gp.read(path, env=env)

    vars_ = m.getVars()
    vtype = np.array([v.VType for v in vars_])
    # Molti MPS (tutta miplib2003) dichiarano le binarie come INTEGER con bound
    # [0,1]: vanno trattate come binarie, altrimenti si scartano istanze buone.
    is_bin = np.array([t == GRB.BINARY or
                       (t == GRB.INTEGER and v.LB >= -1e-9 and v.UB <= 1 + 1e-9)
                       for v, t in zip(vars_, vtype)])
    n_int = int(np.sum((vtype == GRB.INTEGER) & ~is_bin))
    if n_int:
        raise SystemExit(f"[skip] {path}: {n_int} variabili intere generali, non gestite")
    n_cont = int(np.sum(~is_bin))
    if n_cont and not allow_cont:
        raise SystemExit(f"[skip] {path}: {n_cont} variabili continue (usa --allow-cont)")

    # normalizzazione a min: il segno resta nel fattore, i valori riportati
    # sono sempre quelli del problema originale
    sign = 1.0 if m.ModelSense == GRB.MINIMIZE else -1.0
    c = sign * np.array(m.getAttr("Obj", vars_), dtype=float)

    A = m.getA().tocsr()
    rhs = np.array(m.getAttr("RHS", m.getConstrs()), dtype=float)
    sense = np.array(m.getAttr("Sense", m.getConstrs()))

    r = m.relax()
    r.Params.OutputFlag = 0
    # dual simplex: e' l'unico che riusa la base fra un LP e il successivo, ed
    # e' quello che ci serve, perche' fra un'iterazione e l'altra cambia solo
    # l'obiettivo (e il RHS del cutoff). Method=-1 (concurrent) userebbe piu'
    # core ma butterebbe via il warm start.
    r.Params.Method = method
    r.Params.Threads = threads

    return dict(env=env, orig=m, lp=r, c=c, sign=sign, is_bin=is_bin,
                A=A, rhs=rhs, sense=sense, n=len(vars_),
                name=os.path.basename(path))


def violation(P, x):
    """Violazione dei vincoli originali, SENZA cutoff. Ritorna (max, somma)."""
    row = P["A"] @ x
    rhs, sense = P["rhs"], P["sense"]
    scale = np.maximum(1.0, np.abs(rhs))
    v = np.zeros_like(row)
    le = sense == "<"
    ge = sense == ">"
    eq = sense == "="
    v[le] = np.maximum(0.0, row[le] - rhs[le])
    v[ge] = np.maximum(0.0, rhs[ge] - row[ge])
    v[eq] = np.abs(row[eq] - rhs[eq])
    v = v / scale
    return (float(v.max()) if len(v) else 0.0), float(v.sum())


# --------------------------------------------------------------------------
# il pump
# --------------------------------------------------------------------------

def fp(P, args, rng):
    lp, c, is_bin = P["lp"], P["c"], P["is_bin"]
    lpv = lp.getVars()
    nb = int(is_bin.sum())
    bidx = np.flatnonzero(is_bin)
    bvars = [lpv[j] for j in bidx]

    # --- LP di partenza, senza cutoff: da' z_LP e il primo x tilde
    lp.setAttr("Obj", lpv, list(c))
    lp.optimize()
    if lp.Status != GRB.OPTIMAL:
        raise SystemExit(f"[skip] {P['name']}: rilassamento non ottimo (status {lp.Status})")
    z_lp = float(lp.ObjVal)
    x_t = np.array(lp.getAttr("X", lpv), dtype=float)

    # --- UB di riferimento. Lo scenario e' quello realistico: un incumbent
    #     esiste gia' (da un'altra euristica o dal solver) e il pump viene
    #     usato per migliorarlo. z_ref e' quel valore.
    #     Se z_ref manca siamo nella passata di ricognizione (fase A): niente
    #     cutoff, niente contatori, si cerca solo la prima soluzione.
    recon = args.z_ref is None
    if recon:
        z_ref, g, UB = None, 1.0, z_lp
    else:
        z_ref = P["sign"] * args.z_ref
        g = z_ref - z_lp                   # gap di integralita' assoluto
        if g <= TOL:
            raise SystemExit(f"[skip] {P['name']}: gap di integralita' nullo (z_ref=z_lp)")
        # Convenzione v2 (MF, 01/09/2026): lam=1 -> UB=z_ref (l'incumbent),
        # lam=0 -> UB=z_lp. E' l'opposto della v1 usata nei run in grid/, dove
        # lam pesava z_lp: i json senza il campo lam_conv sono in v1 e vanno
        # letti con lam_v2 = 1 - lam. Vedi grid/CONVENZIONE.md.
        UB = z_lp + args.lam * g

    # --- il vincolo di cutoff sta sempre nel modello: cambia solo il suo RHS,
    #     cosi' le tre modalita' girano sullo stesso LP e sono confrontabili
    cut = lp.addConstr(gp.LinExpr(c, lpv) <= GRB.INFINITY, name="objcut")
    lp.update()

    nrm_c = float(np.linalg.norm(c)) or 1.0
    nrm_d = np.sqrt(nb) or 1.0

    rows = []
    seen = set()
    x_hat_prev = None
    alpha = args.alpha0
    delta_hist = []
    ub_eff = GRB.INFINITY                  # il cutoff davvero imposto all'LP
    stall = n_reset = n_reopen = 0         # stallo; reset della fascia; ripartenze da intero
    # contatori del risultato M2
    n_feas = n_killed = n_killed_improving = 0
    z_best = None                          # incumbent trovato dal pump, cutoff IGNORATO
    t0 = time.time()
    status_end = "maxiter"

    for it in range(args.max_iter):
        # ---- arrotondamento dell'iterato corrente
        x_hat = x_t.copy()
        x_hat[bidx] = np.round(x_t[bidx])

        # ---- anti-ciclo (FGL 2005): se ripeto l'arrotondamento, ribalto le
        #      componenti su cui l'LP e' piu' in disaccordo
        key = x_hat[bidx].tobytes()
        if x_hat_prev is not None and np.array_equal(x_hat[bidx], x_hat_prev):
            frac_gap = np.abs(x_t[bidx] - x_hat[bidx])
            T = max(1, int(rng.integers(args.flip // 2, 3 * args.flip // 2 + 1)))
            flip = np.argsort(-frac_gap)[:T]
            x_hat[bidx[flip]] = 1.0 - x_hat[bidx[flip]]
            key = x_hat[bidx].tobytes()
        elif key in seen:
            # ciclo lungo: restart randomizzato
            frac_gap = np.abs(x_t[bidx] - x_hat[bidx])
            p = frac_gap + np.maximum(rng.random(nb) - 0.3, 0.0)
            flip = p > 0.5
            x_hat[bidx[flip]] = 1.0 - x_hat[bidx[flip]]
            key = x_hat[bidx].tobytes()
        seen.add(key)
        x_hat_prev = x_hat[bidx].copy()

        # ---- LE MISURE
        cz_t = float(c @ x_t)
        cz_h = float(c @ x_hat)
        vmax_h, vsum_h = violation(P, x_hat)
        feas_h = vmax_h <= args.feas_tol
        dist = float(np.abs(x_t[bidx] - x_hat[bidx]).sum())
        frac = float(np.minimum(x_t[bidx], 1.0 - x_t[bidx]).sum())
        delta = cz_h - cz_t                       # gap di rounding
        delta_hist.append(delta)

        # ---- il conteggio che e' la nota (M2): l'arrotondamento e' ammissibile
        #      per il problema ORIGINALE, cutoff escluso?
        improving = False
        if feas_h:
            n_feas += 1
            if z_best is None or cz_h < z_best - TOL:
                z_best = cz_h
                improving = True
                stall = 0
            if not recon and cz_h > UB + TOL:
                n_killed += 1                     # il cutoff la scarta
                if cz_h < z_ref - TOL:
                    n_killed_improving += 1       # ...ed era un MIGLIORAMENTO

        rows.append(dict(
            it=it, alpha=alpha,
            cz_lp=cz_t, cz_round=cz_h,
            d_lp=cz_t - UB, d_round=cz_h - UB,      # d = c'x - UB, positivo = viola
            d_lp_n=(cz_t - UB) / g, d_round_n=(cz_h - UB) / g,
            delta=delta, delta_n=delta / g,
            frac=frac, dist=dist,
            viol_max=vmax_h, viol_sum=vsum_h,
            feas=int(feas_h), improving=int(improving),
            ub=UB, ub_eff=(0.0 if ub_eff >= GRB.INFINITY else ub_eff),
            ub_free=int(ub_eff >= GRB.INFINITY),
            z_best=(0.0 if z_best is None else z_best), stall=stall,
            t=time.time() - t0))
        stall += 1

        if recon and feas_h:                       # fase A: basta la prima soluzione
            status_end = "firstsol"
            break
        if dist <= TOL:                            # l'LP era gia' intero
            # Trovare un punto intero non e' la fine: lo scenario e' migliorare
            # un incumbent, non trovare la prima soluzione. Si riparte (l'anti
            # ciclo perturba, e nella progressiva la fascia intanto si abbassa)
            # finche' il budget non e' esaurito. Vale per TUTTE le modalita':
            # se si fermassero qui solo le altre, il confronto misurerebbe
            # "continuare contro fermarsi", non le politiche di cutoff.
            n_reopen += 1
            if z_best is None or args.stop_at_integral:
                status_end = "integral"
                break
        if time.time() - t0 > args.time_limit:
            status_end = "timelimit"
            break

        # ---- il cutoff, nelle tre modalita'
        if args.cut_mode == "none":
            ub_eff = GRB.INFINITY
        elif args.cut_mode == "cutoff":
            ub_eff = UB
        elif args.cut_mode == "moat":               # moat statico: UB' = UB - delta
            k = min(len(delta_hist), args.moat_k)
            d_hat = float(np.median(delta_hist[-k:])) if k else 0.0
            ub_eff = min(UB, max(z_lp + args.moat_eps * g, UB - d_hat))
        else:
            # --- rounding-moat progressiva (idea di MF, 31/08/2026) ---------
            # Si parte SENZA cutoff. Appena esiste un incumbent si apre una
            # fascia sotto di lui, larga quanto il peggioramento tipico del
            # rounding: l'arrotondamento, che peggiora sempre di ~delta, cade
            # cosi' sotto z_inc e MIGLIORA l'incumbent invece di essere
            # scartato. La fascia poi scende insieme all'incumbent, portando UB
            # verso z_LP da sola: nessun lambda da scegliere a priori.
            if z_best is None:
                ub_eff = GRB.INFINITY               # fase libera
            else:
                gg = max(z_best - z_lp, TOL)
                k = min(len(delta_hist), args.moat_k)
                w = float(np.median(delta_hist[-k:])) if k else 0.0
                w = max(w, args.moat_wmin * gg)     # larghezza della fascia
                floor_ = z_lp + args.moat_eps * gg  # non si scende sotto z_LP
                ub_eff = max(floor_, z_best - w)
                # Reset: se la fascia non produce miglioramenti per un po', si
                # rialza a caso fra UB' e z_inc. Serve a rompere i cicli, come
                # il restart del pump, ma agisce sul poliedro invece che sul
                # punto.
                if stall >= args.reset_after:
                    ub_eff = max(floor_, z_best - w * float(rng.random()))
                    stall, n_reset = 0, n_reset + 1
        cut.RHS = ub_eff

        # ---- obiettivo del pump: distanza + costo, entrambi normalizzati in
        #      norma euclidea (Achterberg-Berthold)
        w = np.zeros(P["n"])
        w[bidx] = (1.0 - 2.0 * x_hat[bidx]) * (1.0 - alpha) / nrm_d
        w += c * alpha / nrm_c
        lp.setAttr("Obj", lpv, list(w))
        lp.optimize()
        if lp.Status != GRB.OPTIMAL:
            status_end = f"lp_{lp.Status}"          # cutoff che svuota l'LP: e' un esito
            break
        x_t = np.array(lp.getAttr("X", lpv), dtype=float)
        alpha *= args.alpha_decay

    summary = dict(
        inst=P["name"], seed=args.seed, cut_mode=args.cut_mode, lam=args.lam,
        lam_conv="v2",
        threads=args.threads, lp_method=args.lp_method,
        alpha0=args.alpha0, n=P["n"], nbin=nb, ncons=len(P["rhs"]),
        z_lp=P["sign"] * z_lp, z_ref=args.z_ref, ub=P["sign"] * UB, gap_int=g,
        iters=len(rows), status=status_end, secs=time.time() - t0,
        n_reset=n_reset, n_reopen=n_reopen,
        n_feas=n_feas, n_killed=n_killed, n_killed_improving=n_killed_improving,
        z_best=None if z_best is None else P["sign"] * z_best,
        delta_med=float(np.median(delta_hist)) if delta_hist else None,
        delta_med_n=float(np.median(delta_hist)) / g if delta_hist else None,
        # T3: il moat puo' esistere solo dove delta <= UB - z_lp
        moat_ok_frac=float(np.mean([d <= UB - z_lp for d in delta_hist])) if delta_hist else None,
    )
    return rows, summary


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("mps")
    p.add_argument("--z-ref", type=float, default=None,
                   help="incumbent di partenza; se omesso lo trova il pump stesso (fase A)")
    p.add_argument("--recon-iter", type=int, default=300,
                   help="tetto di iterazioni della fase A")
    p.add_argument("--stop-at-integral", action="store_true",
                   help="ferma il pump al primo iterato intero (comportamento del FP classico, "
                        "che qui falsa il confronto fra modalita')")
    p.add_argument("--cut-mode", choices=["none", "cutoff", "moat", "progressive"],
                   default="cutoff",
                   help="progressive = rounding-moat che scende con l'incumbent")
    p.add_argument("--lam", type=float, default=0.5,
                   help="convenzione v2: UB = z_lp + lam*(z_ref - z_lp); "
                        "lam=1 -> UB all'incumbent, lam=0 -> UB a z_lp")
    p.add_argument("--alpha0", type=float, default=0.0,
                   help="peso iniziale del costo nell'obiettivo del pump")
    p.add_argument("--alpha-decay", type=float, default=0.9)
    p.add_argument("--moat-k", type=int, default=10, help="finestra della mediana di delta")
    p.add_argument("--moat-eps", type=float, default=0.02,
                   help="UB' non scende sotto z_lp + eps*gap")
    p.add_argument("--moat-wmin", type=float, default=0.05,
                   help="progressive: larghezza minima della fascia, in frazione del gap")
    p.add_argument("--reset-after", type=int, default=50,
                   help="progressive: iterazioni senza miglioramenti prima di rialzare UB'")
    p.add_argument("--flip", type=int, default=20)
    p.add_argument("--max-iter", type=int, default=200)
    p.add_argument("--time-limit", type=float, default=600.0)
    p.add_argument("--feas-tol", type=float, default=1e-6)
    p.add_argument("--allow-cont", action="store_true")
    p.add_argument("--threads", type=int, default=4, help="thread del solver LP")
    p.add_argument("--lp-method", type=int, default=1,
                   help="Gurobi Method: 1 dual simplex (warm start), -1 concurrent")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=None, help="prefisso: scrive .csv (per iterazione) e .json")
    p.add_argument("--summary-only", action="store_true",
                   help="solo il .json: il dettaglio per iterazione serve alle figure, "
                        "non a tutti i 1600 run della griglia")
    args = p.parse_args()

    P = load(args.mps, args.allow_cont, args.threads, args.lp_method)

    z_src = "dato"
    if args.z_ref is None:
        # Fase A. Il pump senza cutoff si trova da solo l'incumbent di partenza.
        # E' lo scenario che vogliamo misurare -- il cutoff viene poi applicato a
        # una soluzione che il pump *sa raggiungere* -- e rende l'esperimento
        # autosufficiente: nessuna tabella di best-known di cui fidarsi.
        a0 = argparse.Namespace(**vars(args))
        a0.cut_mode, a0.max_iter = "none", args.recon_iter
        _, s0 = fp(P, a0, np.random.default_rng(args.seed))
        if s0["z_best"] is None:
            print(json.dumps(dict(inst=P["name"], seed=args.seed, cut_mode=args.cut_mode,
                                  status="no_firstsol", iters=s0["iters"],
                                  z_lp=s0["z_lp"], secs=s0["secs"])), flush=True)
            return 0
        args.z_ref = s0["z_best"]
        z_src = f"firstsol@it{s0['iters']}"
        c0 = P["lp"].getConstrByName("objcut")     # via il vincolo della fase A
        if c0 is not None:
            P["lp"].remove(c0)
            P["lp"].update()

    # Seed diverso da quello della fase A, e per una ragione di metodo: con lo
    # stesso seed la fase B in modalita' `none` ripercorrerebbe passo per passo
    # la fase A, quindi non potrebbe che ritrovare la stessa soluzione. Il
    # confronto fra modalita' risulterebbe truccato a favore di quelle che
    # cambiano traiettoria (cutoff, moat), che di passi identici non ne fanno.
    rows, summary = fp(P, args, np.random.default_rng(args.seed + 7919))
    summary["z_ref_src"] = z_src

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        cols = list(rows[0].keys())
        if not args.summary_only:
            with open(args.out + ".csv", "w") as f:
                f.write(",".join(cols) + "\n")
                for r in rows:
                    f.write(",".join(f"{r[k]:.10g}" if isinstance(r[k], float) else str(r[k])
                                     for k in cols) + "\n")
        with open(args.out + ".json", "w") as f:
            json.dump(summary, f, indent=1)

    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    sys.exit(main())
