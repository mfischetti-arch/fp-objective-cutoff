#!/usr/bin/env python3
"""
fp_react.py -- la REACTIVE CUTOFF PUMP contro la feasibility pump di FGL (MF, 06/09/2026).

Domanda: si puo' sostituire la RANDOMIZZAZIONE della pompa (flip debole sullo
stallo, restart casuale sui cicli) con un CUTOFF MOBILE sull'obiettivo che
"tiene al guinzaglio" il punto LP? E' il ritorno alla tabu search da cui la
pompa e' nata (FP-history.md): tabu non una mossa, ma il COSTO.

Tre pompe, stessa struttura (primo LP = min c'x; arrotondamento; recupero di
FGL 2005 sez. 3.2 = test diretto di x^ sui vincoli originali + LP di
completamento con le intere fissate; LP di proiezione a distanza pura sulle
binarie; uscita alla PRIMA soluzione ammissibile del modello ORIGINALE):

  --pump fgl      la pompa del pilota di E3 (fp_target.py --mode pilot
                  --pilot-completion): flip TT~U[T/2,3T/2] sullo stallo, restart
                  rho~U[-0.3,0.7] sui cicli (finestra 3) e forzato ogni 100
                  giri. Con --seed 9999 riproduce il pilota giro per giro.
  --pump react    ZERO casualita'. Memoria H di TUTTI gli arrotondamenti visti.
                  Quando l'arrotondamento e' gia' in H (stallo o ciclo di
                  qualunque lunghezza) si tira il GUINZAGLIO: una riga
                  sull'obiettivo nell'LP di proiezione che il punto LP corrente
                  VIOLA, cosi' il prossimo punto LP e' costretto a muoversi.
                      down:  c'x <= U,  U = cx - tau (cx - z_LP)
                      up:    c'x >= L,  L = cx + tau (z_HI - cx)
                  con cx = c'x del punto LP corrente, z_LP = min c'x su P,
                  z_HI = max c'x su P (un LP in piu' all'inizio). REATTIVO alla
                  Battiti-Tecchiolli: tau <- min(1, gamma tau) a ogni
                  ripetizione, tau <- max(tau0, decay tau) a ogni giro che
                  avanza. Il guinzaglio in una direzione e' FINITO (a U = z_LP
                  il punto LP sta sulla faccia ottima, e il suo arrotondamento
                  e' x^_0, quello del giro 0): --leash osc cambia direzione
                  all'esaurimento (strategic oscillation: giu' fino al bound,
                  su fino a z_HI, giu' di nuovo con la memoria cresciuta),
                  --leash down|up si arrende ("exhausted").
                  --tenure hold: la riga resta e la pompa continua nel poliedro
                  ristretto (il cutoff "vero"); kick: la riga si rilascia
                  appena compare un arrotondamento nuovo (tabu su una mossa).
  --pump hybrid   come react (down, hold), ma all'esaurimento un RESTART
                  casuale di FGL invece di arrendersi: il caso solo in fondo.

Esiti nel JSON: success (= punto ammissibile del modello originale trovato e
RIVALIDATO da Gurobi con validate() di fp_target.py, fuori dal budget),
t_first_feasible, z_first_feasible, n_iter, n_lp, n_pull (strattoni),
n_exhaust, n_sweep (cambi di direzione), n_repeat, tau_max, level_first (dove
stava il punto LP, in [0,1] fra z_LP e z_HI, quando e' arrivata la prima
soluzione), status in target|timelimit|exhausted|error.

Riusa da fp_target.py -- SENZA modificarlo -- load(), feasible(), complete(),
validate(), _key(), inst_name(), emit(): stesso modello, stessa tolleranza,
stesso recupero del pilota di E3.
"""

import argparse
import collections
import os
import sys
import time

import numpy as np
import gurobipy as gp
from gurobipy import GRB

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fp_target import (load, feasible, complete, validate, _key, inst_name,  # noqa: E402
                       emit, Skip, TOL)

BIG = 1e30          # RHS "spento" quando z_HI non e' finito


def new_summary(args, path):
    return dict(
        inst=inst_name(path), file=os.path.basename(path),
        pump=args.pump, leash=args.leash, tenure=args.tenure, every=args.every, eq=int(args.eq),
        tau0=args.tau0, gamma=args.gamma, decay=args.decay, seed=args.seed,
        time_limit=args.time_limit, maximize=None,
        zlp=None, tlp=None, zhi=None, thi=None, zhi_unbounded=None,
        c_zero=None,
        success=0, validated=None, validate_status=None, validate_obj=None,
        validate_time=None,
        t_first_feasible=None, z_first_feasible=None, level_first=None,
        best_obj=None,
        n_iter=0, n_lp=0, n_perturb=0, n_restart=0, n_restart_forced_flip=0,
        n_pull=0, n_exhaust=0, n_sweep=0, n_repeat=0, n_refine=0, tau_max=None,
        n_feas=0, n_recovered=0,
        n_completion_lp=0, n_completion_infeasible=0,
        n_completion_timelimit=0, n_completion_other=0,
        n_completion_rejected=0, completion_status_other=None,
        n_var=None, n_bin=None, n_cont=None, n_cons=None,
        time_load=None, time_total=0.0, status="error", error=None,
        pulls=[],          # i primi MAXTRACE strattoni: [giro, dir, tau, livello]
        # --pump portfolio: fase che ha prodotto l'esito e riassunto della fase 1
        phase=None, p1_status=None, p1_time=None, p1_n_iter=None, p1_n_pull=None,
        pf_cap=args.pf_cap, pf_every=args.pf_every, pf_gate=int(args.pf_gate),
        pf_first=args.pf_first,
        # --pump alternate
        alt_k=args.alt_k, alt_keep=int(args.alt_keep), n_phase_switch=0, found_in=None,
    )


MAXTRACE = 300


def pump(P, args, rng, S):
    lp = P["lp"]
    lpv = lp.getVars()
    c, objcon = P["c"], P["objcon"]
    bidx = P["bidx"]
    nb = P["n_bin"]
    nrm_d = np.sqrt(nb) or 1.0
    reactive = args.pump in ("react", "hybrid", "flipleash", "alternate")
    t0 = time.perf_counter()

    def left():
        return max(1e-3, args.time_limit - (time.perf_counter() - t0))

    def cost(x):
        return float(c @ x) + objcon

    # --- primo LP: min c'x sul rilassamento nudo -> z_LP e primo iterato
    lp.setAttr("Obj", lpv, c.tolist())
    lp.Params.TimeLimit = left()
    t = time.perf_counter()
    lp.optimize()
    S["tlp"] = time.perf_counter() - t
    if lp.Status == GRB.TIME_LIMIT:
        S["status"] = "timelimit"
        S["time_total"] = time.perf_counter() - t0
        return
    if lp.Status != GRB.OPTIMAL:
        S["status"], S["error"] = "error", f"rilassamento non ottimo (status {lp.Status})"
        S["time_total"] = time.perf_counter() - t0
        return
    z_lo = float(lp.ObjVal)
    S["zlp"] = z_lo
    x_t = np.array(lp.getAttr("X", lpv), dtype=float)
    S["c_zero"] = int(not np.any(c != 0.0))
    # base ottima del primo LP: si rimette prima della prima proiezione, cosi'
    # la pompa reattiva parte dallo stesso punto e dalla stessa base di fgl
    vbasis = lp.getAttr("VBasis", lpv)
    cbasis = lp.getAttr("CBasis", lp.getConstrs())

    # --- z_HI = max c'x su P, e le due righe del guinzaglio (spente): SOLO per
    #     le pompe reattive. La pompa fgl resta identica al pilota, righe
    #     comprese (una riga ridondante puo' cambiare il cammino del simplesso).
    z_hi = None
    rowU = rowL = None
    U_off = L_off = None
    if reactive:
        lp.setAttr("Obj", lpv, (-c).tolist())
        # TETTO al tempo di questo LP: massimizzare c'x su P puo' costare molto
        # piu' del minimo (chromaticindex512-7, circ10-3: l'intero budget). Se
        # scade, z_HI resta ignoto e la direzione "up" non e' disponibile
        # (zhi_unbounded = 2); la corsa continua.
        cap = (1e-3 if args.zhi_cap <= 0 else          # 0 = salta l'LP di z_HI
               min(left(), max(args.zhi_cap * S["tlp"], 2.0), 0.25 * args.time_limit))
        lp.Params.TimeLimit = cap
        t = time.perf_counter()
        lp.optimize()
        S["thi"] = time.perf_counter() - t
        if lp.Status == GRB.OPTIMAL:
            z_hi = -float(lp.ObjVal)
            S["zhi"], S["zhi_unbounded"] = z_hi, 0
        elif lp.Status == GRB.TIME_LIMIT:
            S["zhi_unbounded"] = 2        # scaduto il tetto: niente up
        else:
            S["zhi_unbounded"] = 1        # UNBOUNDED / INF_OR_UNBD: niente up
        # righe "spente" = RHS infinito di Gurobi (riga libera). Un 1e30 finito
        # rendeva l'LP di proiezione INFEASIBLE per scaling su glass4
        # (z_LP = 8e8, max c'x illimitato).
        L_off = -GRB.INFINITY
        U_off = GRB.INFINITY
        if args.pf_gate and z_hi is None:
            # CANCELLO del portfolio (intel del 06/09: con z_HI ignoto il
            # guinzaglio non ha mai vinto, 0 su 7): si lascia il campo a FGL
            S["status"] = "gated"
            S["time_total"] = time.perf_counter() - t0
            return
        rowU = lp.addConstr(gp.LinExpr(c.tolist(), lpv) <= U_off - objcon, name="leashU")
        rowL = lp.addConstr(gp.LinExpr(c.tolist(), lpv) >= L_off - objcon, name="leashL")
        lp.update()
        # Il punto di partenza resta x_t, l'ottimo del primo LP, e la base torna
        # quella del primo LP (le due righe nuove entrano con lo slack in base).
        # Prima qui c'era un TERZO LP (min c'x ri-risolto dalla base del massimo)
        # che su 25 istanze della campagna paper non finiva nel budget: 150 run
        # in errore (audit del 07/09, rilievo M5).
        lp.setAttr("VBasis", lpv, vbasis)
        lp.setAttr("CBasis", lp.getConstrs(), list(cbasis) + [0, 0])
        lp.setAttr("Obj", lpv, c.tolist())
        lp.update()

    eps_lo = 1e-7 * max(1.0, abs(z_lo))
    eps_hi = 1e-7 * max(1.0, abs(z_hi)) if z_hi is not None else None
    span = (z_hi - z_lo) if z_hi is not None else None

    def level(v):
        """Posizione in [0,1] fra z_LP e z_HI (None se z_HI e' ignoto)."""
        if span is None or span <= 0:
            return None
        return (v - z_lo) / span

    def lvkey(v):
        """Livello per la chiave dello stato (ciclo morto): con z_HI ignoto usa
        una scala di ripiego, altrimenti ogni (x^, direzione) ripetuto a un
        livello DIVERSO passerebbe per ciclo morto."""
        lv = level(v)
        if lv is None:
            lv = (v - z_lo) / max(1.0, abs(z_lo))
        return round(lv, 9)

    # --- stato del guinzaglio
    U, L = U_off, L_off           # RHS correnti (spenti = ridondanti)
    active = False                # una riga e' tirata?
    direction = "up" if args.leash == "up" else "down"
    tau0 = args.tau0              # si dimezza (--refine) a ogni ciclo morto
    tau = tau0
    seen_states = set()           # (chiave x^, direzione, livello) -> ciclo morto
    # H: tutti gli arrotondamenti visti -> costo della loro proiezione (None
    # finche' non e' stata calcolata). Serve alla riga per mordere anche sui
    # cicli lunghi (MF, 06/09 sera): sullo stallo a 1 il punto LP corrente e'
    # l'ottimo non vincolato del prossimo LP, ma su un ciclo l'obiettivo di
    # distanza cambia e la proiezione libera di x^ puo' stare gia' sotto U.
    H = {}
    cref = None                   # costo di riferimento per lo strattone corrente
    stall_run = 0                 # flipleash: stalli a 1 consecutivi (flip deboli)
    k_target = None
    recent = collections.deque(maxlen=max(1, args.cycle_window))   # fgl
    x_hat_prev = None
    last_restart = 0
    best_obj = best_x = None
    t_first = z_first = None
    status = "maxiter"

    def set_rows():
        rowU.RHS = U - objcon
        rowL.RHS = L - objcon
        if args.eq:
            # --eq: la riga tirata e' un'UGUAGLIANZA (il punto LP sta sulla
            # fetta di costo a ogni giro); quella spenta resta una disuguaglianza
            rowU.Sense = GRB.EQUAL if (active and direction == "down") else GRB.LESS_EQUAL
            rowL.Sense = GRB.EQUAL if (active and direction == "up") else GRB.GREATER_EQUAL

    def release():
        nonlocal U, L, active
        U, L, active = U_off, L_off, False
        set_rows()

    def pull(it, t=None):
        """Tira il guinzaglio nella direzione corrente dal punto LP corrente,
        di una frazione t del range residuo (default: il tau reattivo).
        Ritorna True se la riga si e' mossa, False se la direzione e' esaurita."""
        nonlocal U, L, active
        if t is None:
            t = tau
        cx = cost(x_t)
        if cref is not None and np.isfinite(cref):
            # oltre il punto LP corrente E oltre la proiezione nota di x^
            cx = min(cx, cref) if direction == "down" else max(cx, cref)
        if direction == "down":
            g = cx - z_lo
            Un = cx - t * g
            if g <= eps_lo or Un < z_lo + eps_lo:
                return False
            U = min(U, Un) if active else Un
            active = True
        else:
            if z_hi is None:
                # z_HI ignoto (LP illimitato o oltre il tetto): unita' di
                # ripiego = gap dal bound, e l'esaurimento lo dichiara l'LP
                # (INFEASIBLE dopo lo strattone -> si torna indietro).
                g = max(cx - z_lo, 1e-3 * max(1.0, abs(cx)))
                Ln = cx + t * g
            else:
                g = z_hi - cx
                Ln = cx + t * g
                if g <= eps_hi or Ln > z_hi - eps_hi:
                    return False
            L = max(L, Ln) if active else Ln
            active = True
        set_rows()
        S["n_pull"] += 1
        if len(S["pulls"]) < MAXTRACE:
            lv = level(U if direction == "down" else L)
            S["pulls"].append([it, direction, round(t, 4),
                               None if lv is None else round(lv, 6)])
        return True

    def fgl_restart(x_hat, frac_gap, cand, top):
        """Il restart di FGL 2005 alla lettera (copiato da fp_target.pump)."""
        rho = rng.random(nb) - 0.3
        sel = np.flatnonzero(frac_gap + np.maximum(rho, 0.0) > 0.5)
        if sel.size == 0:
            TT = int(rng.integers(args.flip // 2, 3 * args.flip // 2 + 1))
            if cand.size:
                sel = top(TT)
            elif nb:
                sel = rng.choice(nb, size=max(1, min(TT, nb)), replace=False)
            else:
                sel = np.empty(0, dtype=int)
            S["n_restart_forced_flip"] += 1
        x_hat[bidx[sel]] = 1.0 - x_hat[bidx[sel]]
        S["n_restart"] += 1

    for it in range(args.max_iter):
        S["n_iter"] = it + 1
        x_hat = x_t.copy()
        x_hat[bidx] = np.abs(np.round(x_t[bidx]))
        frac_gap = np.abs(x_t[bidx] - x_hat[bidx])
        cand = np.flatnonzero(frac_gap > args.frac_min)

        def _top(k_max):
            k = max(1, min(int(k_max), cand.size))
            return cand[np.argsort(-frac_gap[cand], kind="stable")[:k]]

        # --pump alternate (MF, 07/09 notte): si parte con FGL e ci si alterna
        # col guinzaglio ogni --alt-k giri, nella STESSA corsa (stesso x^,
        # stessa memoria H). Nei giri FGL le righe sono rilasciate
        # (--alt-keep le tiene: FGL esplora la fetta di costo del guinzaglio).
        use_fgl = not reactive
        if args.pump == "alternate":
            regime = "fgl" if (it // args.alt_k) % 2 == 0 else "react"
            use_fgl = regime == "fgl"
            if it > 0 and it % args.alt_k == 0:
                S["n_phase_switch"] += 1
                if use_fgl:
                    last_restart = it          # la fase FGL riparte fresca
                    if active and not args.alt_keep:
                        release()
        if use_fgl:
            # ---------------------------------------------- FGL (= pilota E3)
            if reactive:
                H.setdefault(_key(x_hat[bidx]), None)   # memoria condivisa
            do_restart = False
            if it - last_restart >= args.restart_every:
                do_restart = True
            elif x_hat_prev is not None and np.array_equal(x_hat[bidx], x_hat_prev):
                if cand.size:
                    TT = int(rng.integers(args.flip // 2, 3 * args.flip // 2 + 1))
                    sel = _top(TT)
                    x_hat[bidx[sel]] = 1.0 - x_hat[bidx[sel]]
                    S["n_perturb"] += 1
                else:
                    do_restart = True
            elif _key(x_hat[bidx]) in recent:
                do_restart = True
            if do_restart:
                fgl_restart(x_hat, frac_gap, cand, _top)
                last_restart = it
            recent.append(_key(x_hat[bidx]))
            x_hat_prev = x_hat[bidx].copy()
            if reactive:
                H.setdefault(_key(x_hat[bidx]), None)   # anche l'x^ perturbato
                k_target = _key(x_hat[bidx])
        else:
            # ------------------------------------------ REACTIVE CUTOFF PUMP
            k = _key(x_hat[bidx])
            if (args.pump == "flipleash" and x_hat_prev is not None
                    and np.array_equal(x_hat[bidx], x_hat_prev) and cand.size
                    and stall_run < args.restart_every):
                # flipleash (MF, 06/09 sera): sullo stallo a 1 il flip debole di
                # FGL, com'e' sempre stato (casuale solo nel NUMERO di flip);
                # il guinzaglio prende il posto del restart, cioe' scatta sui
                # cicli (arrotondamento gia' in memoria). L'x^ ribaltato entra
                # in memoria: se ci si ritorna, e' un ciclo.
                TT = int(rng.integers(args.flip // 2, 3 * args.flip // 2 + 1))
                sel = _top(TT)
                x_hat[bidx[sel]] = 1.0 - x_hat[bidx[sel]]
                S["n_perturb"] += 1
                H.setdefault(_key(x_hat[bidx]), None)
                stall_run += 1        # glass4: 6 584 flip di fila senza un ciclo;
                                      # dopo restart_every stalli tocca al guinzaglio
            elif k in H:
                S["n_repeat"] += 1
                stall_run = 0
                cref = H.get(k)
                if S["n_repeat"] > 1:
                    tau = min(1.0, tau * args.gamma)
                S["tau_max"] = max(S["tau_max"] or 0.0, tau)
                # ciclo morto: stesso arrotondamento, stessa direzione, stesso
                # livello della riga -> la traiettoria deterministica si ripete
                st = (k, direction, lvkey(U if direction == "down" else L))
                dead = st in seen_states
                seen_states.add(st)
                if dead and args.refine > 1 and tau0 / args.refine >= args.tau_min:
                    # RAFFINAMENTO deterministico: passi piu' fini, livelli
                    # nuovi, stessa memoria H; nessun numero casuale.
                    tau0 /= args.refine
                    tau = tau0
                    S["n_refine"] += 1
                    seen_states.clear()
                    release()
                    dead = False
                moved = (not dead) and pull(it)
                if not moved and not dead and args.leash == "osc":
                    # range esaurito: cambio di direzione, righe rilasciate,
                    # tau da capo; se anche di la' non si muove (il riferimento
                    # di x^ sta gia' al bordo), si riprova senza riferimento
                    S["n_exhaust"] += 1
                    direction = "up" if direction == "down" else "down"
                    S["n_sweep"] += 1
                    release()
                    tau = tau0
                    moved = pull(it)
                    if not moved:
                        cref = None
                        moved = pull(it)
                if (not moved and not dead
                        and args.refine > 1 and tau0 / args.refine >= args.tau_min):
                    # fine corsa in tutte le direzioni: si rilascia la riga e si
                    # riparte a passi piu' fini (livelli nuovi, stessa memoria)
                    tau0 /= args.refine
                    tau = tau0
                    S["n_refine"] += 1
                    seen_states.clear()
                    release()
                    cref = None
                    moved = pull(it)
                if not moved:
                    S["n_exhaust"] += 1
                    if not moved:
                        if args.pump in ("hybrid", "flipleash", "alternate"):
                            # ultima risorsa: il restart casuale di FGL, contato
                            release()
                            tau = tau0
                            fgl_restart(x_hat, frac_gap, cand, _top)
                            last_restart = it
                            H.setdefault(_key(x_hat[bidx]), None)
                        else:
                            status = "exhausted"
                            S["exhaust_reason"] = ("dead_cycle" if dead else
                                                   f"{direction}_range_exhausted")
                            break
            else:
                H[k] = None
                stall_run = 0
                tau = max(tau0, tau * args.decay)
                if active and args.tenure == "kick":
                    release()
                if args.every > 0:
                    # --every: la riga si muove a OGNI giro di un passo piccolo,
                    # anche senza stallo (soglia tabu che scorre); sugli stalli
                    # vale lo strattone reattivo qui sopra. Range finito ->
                    # cambio di direzione (osc) o si aspetta lo stallo.
                    if not pull(it, args.every) and args.leash == "osc":
                        direction = "up" if direction == "down" else "down"
                        S["n_sweep"] += 1
                        release()
                        tau = tau0
                        pull(it, args.every)
            cref = None
            x_hat_prev = x_hat[bidx].copy()
            k_target = _key(x_hat[bidx])     # l'x^ che entra nell'obiettivo

        # ---- recupero (FGL sez. 3.2): test diretto + completamento
        got = []
        # guardia: un punto con componenti non finite (neos-5107597-kakapo col
        # vecchio RHS 1e30: continue a ~1e28, costo inf) passava feasible()
        # perche' i confronti con nan sono falsi. Qui si scarta e basta.
        finite = bool(np.all(np.isfinite(x_hat)))
        if finite and feasible(P, x_hat, args.feas_tol) and np.isfinite(cost(x_hat)):
            S["n_feas"] += 1
            got.append((cost(x_hat), x_hat.copy()))
        v, xc = (None, None) if not finite else complete(P, x_hat, S, args.feas_tol, left())
        if v is not None and np.isfinite(v) and bool(np.all(np.isfinite(xc))):
            got.append((v, xc))
        now = time.perf_counter() - t0
        if got:
            S["n_recovered"] += 1
            v, xv = min(got, key=lambda p: p[0])
            if t_first is None:
                t_first, z_first = now, v
                S["level_first"] = level(cost(x_t))
            if best_obj is None or v < best_obj:
                best_obj, best_x = v, xv
            status = "target"
            if args.pump == "alternate":
                S["found_in"] = "fgl" if use_fgl else "react"
            break
        if now > args.time_limit:
            status = "timelimit"
            break

        # ---- LP di proiezione: distanza pura sulle binarie, con le righe
        w = np.zeros(P["n"])
        w[bidx] = (1.0 - 2.0 * x_hat[bidx]) / nrm_d
        lp.setAttr("Obj", lpv, w.tolist())
        lp.Params.TimeLimit = left()
        lp.optimize()
        if lp.Status == GRB.TIME_LIMIT:
            status = "timelimit"
            break
        if (lp.Status in (GRB.INFEASIBLE, GRB.INF_OR_UNBD) and reactive
                and active and direction == "up" and z_hi is None):
            # la salita alla cieca ha superato il massimo: range esaurito.
            # Si rilascia la riga; al giro dopo lo stesso x_t da' lo stesso
            # x^ (gia' in H) e lo strattone riparte nella nuova direzione.
            S["n_exhaust"] += 1
            release()
            if args.leash == "osc":
                direction = "down"
                S["n_sweep"] += 1
                tau = tau0
            elif args.pump != "hybrid":
                status = "exhausted"
                S["exhaust_reason"] = "up_range_exhausted"
                break
            continue
        if lp.Status != GRB.OPTIMAL:
            status = "error"
            S["error"] = (f"LP di proiezione non ottimo (status {lp.Status}); "
                          f"U={U} L={L} z_LP={z_lo} z_HI={z_hi} dir={direction}")
            break
        S["n_lp"] += 1
        x_t = np.array(lp.getAttr("X", lpv), dtype=float)
        if reactive and H.get(k_target) is None:
            H[k_target] = cost(x_t)          # la proiezione di quell'x^ costa cosi'

    S["status"] = status
    S["best_obj"] = best_obj
    S["t_first_feasible"] = t_first
    S["z_first_feasible"] = z_first
    S["time_total"] = time.perf_counter() - t0
    S["success"] = int(best_obj is not None)
    S["leash_final"] = dict(U=None if U == U_off else U, L=None if L == L_off else L,
                            dir=direction, tau=tau, active=active) if reactive else None
    if S["success"] and best_x is not None and not args.no_validate:
        validate(args.mps, best_x, best_obj, S, threads=args.threads)


def main():
    p = argparse.ArgumentParser(description="Reactive cutoff pump vs FGL pump.")
    p.add_argument("mps")
    p.add_argument("--pf-cap", type=float, default=0.5,
                   help="portfolio: frazione del budget alla fase reattiva")
    p.add_argument("--pf-every", type=float, default=0.01,
                   help="portfolio: --every della fase reattiva (eoh)")
    p.add_argument("--pf-gate", action="store_true", default=False,
                   help="portfolio: con z_HI ignoto salta la fase reattiva")
    p.add_argument("--pf-first", choices=["react", "fgl"], default="react",
                   help="portfolio: fase 1 reattiva (default) o FGL (controllo del riavvio: "
                        "fase 2 = FGL con seme + 100)")
    p.add_argument("--alt-k", type=int, default=50,
                   help="alternate: giri per fase (FGL, poi guinzaglio, poi FGL, ...)")
    p.add_argument("--alt-keep", action="store_true", default=False,
                   help="alternate: nei giri FGL le righe del guinzaglio restano")
    p.add_argument("--pump", choices=["fgl", "react", "hybrid", "flipleash", "portfolio", "alternate"],
                   required=True,
                   help="flipleash = flip debole di FGL sullo stallo, guinzaglio sui cicli, "
                        "restart casuale solo come ultima risorsa (MF)")
    p.add_argument("--eq", action="store_true",
                   help="la riga tirata e' un'uguaglianza c'x = U (o = L)")
    p.add_argument("--leash", choices=["down", "up", "osc"], default="osc",
                   help="direzione del guinzaglio (react); hybrid e' sempre down")
    p.add_argument("--tenure", choices=["hold", "kick"], default="hold")
    p.add_argument("--tau0", type=float, default=0.05)
    p.add_argument("--gamma", type=float, default=2.0, help="escalation di tau a ogni ripetizione")
    p.add_argument("--decay", type=float, default=0.9, help="rientro di tau a ogni giro che avanza")
    p.add_argument("--refine", type=float, default=2.0,
                   help="al ciclo morto tau0 <- tau0/refine e si riparte (1 = spento)")
    p.add_argument("--tau-min", type=float, default=1e-4, help="sotto questo tau0 non si raffina piu'")
    p.add_argument("--zhi-cap", type=float, default=10.0,
                   help="tetto al tempo dell'LP di z_HI, in multipli di t_LP (mai sotto 2 s, "
                        "mai sopra un quarto del budget)")
    p.add_argument("--every", type=float, default=0.0,
                   help="variante a ogni giro: la riga si muove di questa frazione del range "
                        "residuo a OGNI iterazione (0 = solo sugli stalli); forza --tenure hold")
    p.add_argument("--time-limit", type=float, default=300.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=None)
    p.add_argument("--flip", type=int, default=20)
    p.add_argument("--frac-min", type=float, default=1e-6)
    p.add_argument("--cycle-window", type=int, default=3)
    p.add_argument("--restart-every", type=int, default=100)
    p.add_argument("--max-iter", type=int, default=100_000_000)
    p.add_argument("--feas-tol", type=float, default=1e-6)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--lp-method", type=int, default=1)
    p.add_argument("--no-validate", action="store_true")
    args = p.parse_args()
    if args.pump == "hybrid":
        args.leash, args.tenure = "down", "hold"
    if args.every > 0:
        args.tenure = "hold"
    if not (0 < args.tau0 <= 1) or args.gamma < 1 or not (0 < args.decay <= 1):
        print("BadOption: tau0 in (0,1], gamma >= 1, decay in (0,1]", file=sys.stderr)
        return 2

    def phase(a, seed):
        """Un'esecuzione completa della pompa su un modello fresco."""
        Sp = new_summary(a, a.mps)
        t = time.perf_counter()
        P = load(a.mps, "pilot", None, True, threads=a.threads,
                 method=a.lp_method, time_limit=a.time_limit)
        Sp["time_load"] = time.perf_counter() - t
        Sp.update(maximize=bool(P["maximize"]), n_var=int(P["n"]),
                  n_bin=int(P["n_bin"]), n_cont=int(P["n_cont"]),
                  n_cons=int(P["n_cons"]))
        pump(P, a, np.random.default_rng(seed), Sp)
        for m in (P.get("lp"), P.get("clone")):
            if m is not None:
                m.dispose()
        P["env"].dispose()
        return Sp

    S = new_summary(args, args.mps)
    try:
        if args.pump != "portfolio":
            S = phase(args, args.seed)
        else:
            # PORTFOLIO (MF, 06/09 notte): fase 1 = pompa reattiva eoh (osc,
            # hold, --every) con budget pf_cap*TL e cancello su z_HI; se non
            # trova, fase 2 = FGL da capo col budget residuo. L'esito e' della
            # fase che l'ha prodotto; i tempi della fase 2 sono traslati.
            a1 = argparse.Namespace(**vars(args))
            if args.pf_first == "fgl":
                # CONTROLLO: fase 1 = FGL stesso (seme s), fase 2 = FGL con un
                # altro seme. Se guadagna quanto il guinzaglio, il merito e'
                # del riavvio, non del guinzaglio.
                a1.pump, a1.pf_gate = "fgl", False
            else:
                a1.pump, a1.leash, a1.tenure, a1.every = "react", "osc", "hold", args.pf_every
            a1.time_limit = args.pf_cap * args.time_limit
            S1 = phase(a1, args.seed)
            used = float(S1.get("time_total") or 0.0)
            if S1.get("success") == 1 and S1.get("validated") == 1:
                S = S1
                S.update(pump="portfolio", phase=("react" if args.pf_first == "react" else "fgl1"))
            else:
                a2 = argparse.Namespace(**vars(args))
                a2.pump, a2.every, a2.pf_gate = "fgl", 0.0, False
                a2.time_limit = max(1e-3, args.time_limit - used)
                S = phase(a2, args.seed + (100 if args.pf_first == "fgl" else 0))
                S.update(pump="portfolio", phase="fgl", time_limit=args.time_limit)
                for k in ("t_first_feasible", "time_total"):
                    if S.get(k) is not None:
                        S[k] = float(S[k]) + used
            S.update(p1_status=S1.get("status"), p1_time=used, p1_n_iter=S1.get("n_iter"),
                     p1_n_pull=S1.get("n_pull"), zhi=S1.get("zhi"),
                     zhi_unbounded=S1.get("zhi_unbounded"), thi=S1.get("thi"))
    except Skip as e:
        S["status"], S["error"] = "error", f"skip: {e}"
    except Exception as e:                                   # noqa: BLE001
        S["status"], S["error"] = "error", f"{type(e).__name__}: {e}"
    emit(S, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
