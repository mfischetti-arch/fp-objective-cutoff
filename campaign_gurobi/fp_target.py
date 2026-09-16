#!/usr/bin/env python3
"""
fp_target.py -- la Feasibility Pump davanti a un BERSAGLIO di costo.

Scenario. L'utente ha gia' una soluzione di valore z_inc (trovata dalla pompa
"pilota") e ne vuole una di costo <= U, con

    U = z_best + a (z_inc - z_best),     a in (0,1),    SENSO DI MINIMO

dove z_best e' il miglior valore noto di MIPLIB. Come si chiede alla pompa di
arrivarci? TRE bracci di valutazione -- naive, test, completion -- tutti con la
STESSA pompa (quella di FGL 2005, vedi pump()), stesso seme e quindi stessa
sequenza casuale, distanza PURA (nessun termine pesato sull'obiettivo: e' fp.py
con alpha = 0), stesso time limit. Tutti e tre ESCONO appena l'obiettivo e'
raggiunto: il tempo speso prima di uscire e' l'esito che ci interessa.

ATTENZIONE: "test con w = 0" NON e' un quarto braccio. Con U' = U la riga
interna dell'LP di proiezione taglia esattamente lo stesso poliedro della riga
statica di naive, e la regola di uscita e' la stessa: e' naive lettera per
lettera, e l'unica differenza osservabile sarebbe il vertice scelto dal
simplesso. naive E' il punto w = 0 della griglia, per test come per completion;
il runner non lo esegue due volte.

  --mode pilot
      la pompa pulita, senza alcun vincolo sull'obiettivo. Si ferma alla prima
      soluzione ammissibile e ne riporta il valore (zinc), insieme a z_LP (zlp)
      e al tempo del primo LP (tlp). E' la corsa che GENERA lo scenario: il
      runner calcola U e U' dai suoi numeri (e da z_best del file .solu, che va
      negato se il modello era di massimo: per questo il JSON riporta anche
      "maximize"). La campagna lo lancia con --pilot-completion (il recupero di
      FGL sez. 3.2: massimizza il numero di istanze che sopravvivono) e con un
      seme FUORI da quelli di valutazione (0-4) e di taratura (10-14), cosi'
      nessuna replica riparte dalla sequenza casuale che ha prodotto z_inc.
      --tlp-max T fa uscire il pilota SUBITO DOPO il primo LP, con status
      "slow", se t_LP > T: un'istanza troppo lenta costa un LP e non l'intero
      budget del pilota.

  --mode naive
      il modo ovvio: la riga c'x <= U viene aggiunta al MODELLO, PRIMA e FUORI
      dalla pompa (m.addConstr), poi la pompa gira sul modello ristretto come
      una scatola chiusa, senza sapere nulla di U.
      Nessun incumbent di partenza: la soluzione del pilota viola il vincolo,
      quindi non e' un punto di partenza ammissibile.
      Il riconoscimento della soluzione e' quello di fp.py con cut_mode=none: a
      ogni giro l'arrotondamento x^ viene testato contro TUTTE le righe del
      modello -- qui: le originali PIU' la riga del bersaglio -- e contro i
      bound. Poiche' c'x <= U e' una riga come le altre, x^ la deve soddisfare
      per essere dichiarato ammissibile: e' esattamente qui che il braccio
      naive fatica.

  --mode test
      il modello resta ORIGINALE. La riga c'x <= U' vive solo dentro l'LP di
      proiezione, con U' = U - w (U - z_LP), w >= 0 FISSO per tutta la corsa:
      una fascia (il rounding-moat) sotto il bersaglio, che non insegue mai
      l'incumbent e non si muove. L'iterato LP e' cosi' tenuto sotto U', e il
      suo arrotondamento -- che il rounding peggiora sempre un po' -- cade sotto
      U invece che sopra. A ogni giro x^ viene testato contro i vincoli
      ORIGINALI (la riga del bersaglio NON fa parte del test) e i bound; si esce
      appena esiste un punto ammissibile di costo <= U.

  --mode completion
      come test, ma il recupero e' quello di FGL 2005, sez. 3.2: invece di
      limitarsi a testare x^, si fissano le variabili intere a x^ in un CLONE
      continuo del modello originale (senza alcuna riga sull'obiettivo) e si
      minimizza c'x. Se il clone e' ammissibile la sua soluzione e' un punto
      ammissibile del problema originale, di costo non peggiore di quello di x^.
      Sulle istanze pure-binarie il clone non ha variabili libere e il
      completamento coincide col test -- a meno del costo dell'LP, che qui viene
      comunque pagato a ogni giro: e' il costo onesto della procedura di FGL.

  --mode test-adapt | completion-adapt      (Q3 del referee MPC, 16/09/2026)
      come test / completion, ma la fascia NON e' una frazione fissa w del gap
      G = U - z_LP: e' scalata, istanza per istanza e run per run, sul
      ROUNDING GAP OSSERVATO delta_k = c'x^_k - c'x~_k (sez. 2 del paper: di
      quanto l'arrotondamento peggiora il costo), misurato a OGNI giro
      sull'arrotondamento puro dell'iterato LP, PRIMA del flip debole o del
      restart. La regola, con K = --adapt-k (default 5):
        * giri 1..K: riga interna c'x <= U, cioe' w = 0 (e' naive, con la riga
          nell'LP di proiezione e il recupero del braccio);
        * dal giro K+1 in poi: U' = U - m, con m = mediana dei delta osservati,
          e due sotto-regole (--adapt-rule):
              freeze    m = mediana dei PRIMI K delta, congelata: U' cambia una
                        volta sola (regola PRIMARIA, dichiarata prima della
                        campagna);
              running   m = mediana di TUTTI i delta osservati finora,
                        ricalcolata a ogni giro: U' si muove con la corsa
                        (sotto-variante secondaria);
              abs       m = mediana di |delta| sui primi K giri, congelata:
                        sotto-variante ESPLORATIVA aggiunta dopo lo smoke test
                        del 16/09, che ha mostrato delta NEGATIVO nel 97% dei
                        giri (l'iterato LP sta sulla riga c'x <= U e
                        l'arrotondamento abbassa il costo): con la regola
                        letterale di Q3 la fascia e' nulla, e 'abs' scala la
                        fascia sulla GRANDEZZA del rounding gap osservato;
        * m viene troncato in [0, G(1 - eps)]: se la mediana e' <= 0
          (l'arrotondamento in media non peggiora il costo) la fascia resta
          nulla, e la riga non scende mai sotto z_LP + eps G, con
          eps = --adapt-eps (default 1e-3), cosi' l'LP di proiezione non si
          svuota mai per colpa della fascia.
      Tutto il resto -- pompa, perturbazioni, recupero, uscita, budget,
      validazione -- e' identico a test / completion. Nel JSON compaiono le
      chiavi adapt_rule, adapt_k, n_delta (giri con delta misurato), moat (l'm
      applicato alla fine, 0 se mai applicato), uprime_final, uprime_min,
      n_uprime_changes, delta_med_all (mediana di tutti i delta della corsa,
      diagnostica), delta_frac_pos (frazione dei delta > 0), e w_eff = moat / G
      e' la fascia effettiva in unita' di gap, confrontabile col w fisso.
      --Uprime e --pressure non valgono per questi modi (BadOption).
      VINCOLO DI IDENTITA': i modi naive/test/completion non sono toccati (le
      chiavi nuove esistono solo nei modi adapt).

Convenzioni.
  * SENSO DI MINIMO sempre. Un modello di massimo viene convertito subito dopo
    la lettura (ModelSense e coefficienti dell'obiettivo negati, costante
    compresa) e TUTTI i valori riportati -- zlp, zinc, best_obj, U, U' -- sono
    quelli del modello convertito. Il runner passa U e U' gia' in quel senso.
  * U e U' NON si spostano MAI durante la corsa.
  * ESITO, UNA REGOLA SOLA PER TUTTI I BRACCI:
        success = target_ok = 1  sse  esiste un punto ammissibile per i vincoli
        ORIGINALI con c'x <= U + 1e-6*max(1,|U|)
    e la corsa esce con status "target" appena questo accade. Niente regola
    speciale per naive (prima bastava un punto ammissibile del modello
    ristretto, che e' un metro piu' largo di quello degli altri bracci). Per il
    pilota, che non ha U, success = 1 sse una soluzione e' stata trovata.
  * VALIDAZIONE INDIPENDENTE del punto di successo (validated). Il test interno
    feasible() eredita da fp.py una tolleranza RELATIVA AL SOLO rhs, che su una
    riga con rhs grande e' piu' larga della FeasibilityTol assoluta di Gurobi.
    Percio', quando la corsa dichiara successo, il modello viene RILETTO
    dall'MPS, TUTTE le variabili fissate al punto trovato e risolto coi default
    di Gurobi: validated=1 se lo status e' OPTIMAL e il valore coincide con
    best_obj entro 1e-6 relativo. Il tempo di questo LP NON entra ne' in
    time_to_success ne' in time_total: sta a parte in validate_time. Nei
    confronti fra bracci si usano target_ok e validated -- MAI n_feas o
    n_recovered, che per naive contano gli x^ ammissibili per il modello
    RISTRETTO (riga del bersaglio compresa) e per gli altri quelli ammissibili
    per il modello originale: sono due cose diverse e non sono confrontabili.
  * i tempi sono time.perf_counter e partono dall'inizio della POMPA: la lettura
    del modello e' esclusa (la si trova in time_load), il primo LP e' incluso.
  * il budget e' il TEMPO: --max-iter esiste solo come rete di sicurezza. Prima
    di OGNI optimize() -- primo LP, LP di proiezione, LP di completamento -- il
    TimeLimit di Gurobi viene rimesso al budget RESIDUO, max(1e-3, TL -
    trascorso): lo sforo massimo e' UN LP interrotto, uguale per tutti i bracci.
    (Col budget INTERO su ogni chiamata sforava di piu' proprio completion, che
    di LP per giro ne paga due: il braccio da dimostrare riceveva piu' secondi.)
  * n_iter = arrotondamenti fatti, n_lp = LP di PROIEZIONE RISOLTI (il primo LP,
    quello di z_LP, sta in tlp; un LP interrotto dal tempo NON e' "risolto" e non
    si conta). Le due chiavi hanno la STESSA semantica in tutti i modi: per ogni
    uscita reale -- target, timelimit, error -- vale n_lp = n_iter - 1, perche'
    l'iterato del giro k viene dall'LP del giro k-1. Solo l'uscita per
    --max-iter, che e' la rete di sicurezza (default 1e8) e nella campagna non
    scatta mai, lascia n_lp = n_iter: li' l'ultimo LP e' stato risolto e poi il
    ciclo e' semplicemente finito.
  * Gurobi: Threads=1, Method=1 (dual simplex, l'unico che riusa la base fra un
    LP e il successivo), OutputFlag=0.

LE RIGHE DI PRESSIONE (--pressure, MF 04/09/2026)
-------------------------------------------------
La riga c'x <= U' dell'LP di proiezione e' INVALIDA per il problema originale, e
puo' permetterselo: il recupero (test diretto di x^ e completamento con le intere
fissate) lavora sempre sui vincoli ORIGINALI, senza alcuna riga aggiunta, e
l'uscita chiede c'x <= U su quel modello. La riga interna, quindi, non e' un
taglio: e' solo PRESSIONE sull'LP di proiezione, verso l'integer-feasibility e
verso il basso. Se e' cosi', c'x <= U' e' UNA pressione fra tante, e --pressure
apre la famiglia:

  cut:w          la riga di oggi, c'x <= U - w G   (identica a --Uprime)
  reflect:a[:b]  la stessa riga, ma ADATTIVA: parte da U - a G, e ogni punto
                 ammissibile di valore v > U (inutile: sta sopra il bersaglio)
                 la fa scendere a min(U', 2U - v) -- lo SPECCHIO di v sotto U --
                 mai sotto U - b G ne' sotto z_LP; dopo --stall-relax giri senza
                 nemmeno un punto ammissibile risale di meta' strada.
  track:eta[:b]  la stessa riga, ma che insegue il COSTO DELL'ARROTONDATO.
                 reflect reagisce ai punti AMMISSIBILI sopra U, e nella maggior
                 parte dei fallimenti quei punti non arrivano mai: la riga resta
                 dove l'hanno messa e la corsa e' di fatto un cut. L'arrotondato
                 x^, invece, c'e' a OGNI giro. Detto e = (c'x^ - U)/G l'errore
                 relativo dell'arrotondato rispetto al bersaglio,
                     U' <- U' - eta e G,      U' in [U - b G, U],
                 con U' che parte da U: arrotondato SOPRA la soglia -> la riga
                 scende e tira giu' l'iterato; arrotondato SOTTO la soglia ma
                 non ammissibile -> la riga risale e restituisce spazio alla
                 feasibility. E' un controllo proporzionale, con eta il guadagno.
                 track_e_mean riporta la media di e sulla corsa.
  lb:k[:grow]    local branching attorno all'incumbent del pilota, raggio
                 K = max(1, round(k nb)); se l'LP si svuota K raddoppia, e con
                 ':grow' raddoppia anche dopo --stall-relax giri senza nemmeno
                 un punto ammissibile (la palla e' troppo stretta).
  lbmove:k[:grow]  la stessa palla, ma col CENTRO MOBILE: parte da x_inc e si
                 sposta sul miglior punto che il recupero trova, anche se sta
                 SOPRA U -- quei punti oggi si buttano via, e sono l'unica
                 informazione che la pompa raccoglie sulla zona ammissibile.
                 La riga si riscrive (coefficienti e RHS) a ogni spostamento e
                 K torna al raggio iniziale; n_center_moves li conta.
  sgn:w          il cutoff "nei segni": s_j = sign(c_j) sulle sole binarie, riga
                 s'x <= s'x_inc - w (s'x_inc - smin), con smin = min{s'x : x in P}
                 da UN LP in piu' all'inizio. E' il cutoff senza le magnitudini,
                 che su costi molto sbilanciati sono quelle che lo rendono ostile.
  card:k         cardinalita': sum_{j in B} x_j <= (1-k) |{j : xinc_j = 1}|.
  nogood:m       righe tabu sulle ultime m x^ scartate.

G = U - z_LP e' il gap del bersaglio: tutte le quantita' "in unita' di gap" si
misurano li' (se G <= 0 la SPEC si spegne e lo dice in pressure_note). Le SPEC si
combinano col '+' (reflect:0.02+lb:0.1). Le righe di pressione stanno SOLO
nell'LP di proiezione -- mai nel clone del completamento, mai nel test di
ammissibilita', mai nella validazione -- e sono aggiunte DOPO il primo LP, come
la riga statica, cosi' z_LP resta il vero bound. Uscita, budget, perturbazioni e
validazione NON cambiano. --pressure vale solo per test/completion: in naive la
riga c'x <= U e' statica e dentro il modello, e il pilota non ha un U.

VINCOLO DI IDENTITA': senza --pressure il JSON e' quello di prima, chiave per
chiave -- le chiavi della pressione ESISTONO SOLO se l'opzione e' data.

Perimetro. Come fp.py, la pompa e' quella binaria: le variabili continue sono
sempre ammesse (entrano nei vincoli e nel completamento, non nella distanza),
le variabili INTERE GENERALI no -- l'istanza viene rifiutata con status "error"
e un messaggio "skip: ...", cosi' il runner la registra invece di perdere il
file JSON.

Uso:
  python fp_target.py inst.mps.gz --mode pilot --pilot-completion --tlp-max 5 \
      --time-limit 150 --seed 9999 --out p.json
  python fp_target.py inst.mps.gz --mode naive --U 1234.5 --time-limit 300 --seed 0 --out n.json
  python fp_target.py inst.mps.gz --mode test --U 1234.5 --Uprime 1180.0 \
      --time-limit 300 --seed 0 --out t.json
  python fp_target.py inst.mps.gz --mode completion --U 1234.5 \
      --pressure reflect:0.02+lb:0.1 --incumbent p.json.inc \
      --time-limit 300 --seed 0 --out c.json
"""

import argparse
import collections
import hashlib
import json
import os
import sys
import time

import numpy as np
import gurobipy as gp
from gurobipy import GRB

# La pompa e' quella di fp.py (sezione 2 del paper): da li' viene il test di
# violazione delle righe, e da li' sono copiati alla lettera l'arrotondamento,
# la perturbazione a T flip e il restart randomizzato (vedi pump()).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fp import violation as fp_violation  # noqa: E402

TOL = 1e-6

# i modi con la fascia ADATTIVA (Q3): come test/completion, riga interna con
# U' = U - mediana(delta) dal giro K+1 in poi (vedi il docstring in testa).
ADAPT_MODES = ("test-adapt", "completion-adapt")


class Skip(Exception):
    """Istanza fuori dal perimetro dell'esperimento: non e' un errore del codice."""


class BadOption(Exception):
    """Riga di comando incoerente: e' un errore d'USO, non dell'istanza.

    Non e' uno Skip di proposito: il runner legge come "unsupported" ogni
    messaggio che inizia per "skip:", e un refuso in --pressure verrebbe
    archiviato come istanza fuori perimetro invece che come campagna da
    ricontrollare. Qui il messaggio esce come "BadOption: ..." e si vede."""


# --------------------------------------------------------------------------
# lettura e preparazione
# --------------------------------------------------------------------------

def load(path, mode, U, need_clone, threads=1, method=1, time_limit=None):
    """Legge il modello, lo porta nel senso di MINIMO, ne estrae le matrici per
    il test di ammissibilita', costruisce l'LP di proiezione e -- se serve -- il
    clone continuo per il completamento.

    Per --mode naive la riga c'x <= U viene aggiunta al modello PRIMA di tutto:
    finisce quindi sia nelle matrici del test sia nell'LP di proiezione sia nel
    clone. Per gli altri modi il modello resta l'originale."""
    env = gp.Env(params={"OutputFlag": 0})
    m = gp.read(path, env=env)
    m.Params.OutputFlag = 0
    m.Params.Threads = threads

    if m.NumQConstrs or m.NumSOS or m.NumGenConstrs:
        raise Skip("il modello ha vincoli quadratici/SOS/generali: il test di "
                   "ammissibilita' su A x guarda solo le righe lineari")

    vars_ = m.getVars()
    vtype = np.array([v.VType for v in vars_])
    # Molti MPS (tutta miplib2003) dichiarano le binarie come INTEGER con bound
    # [0,1]: vanno trattate come binarie. Identico a fp.py.
    is_bin = np.array([t == GRB.BINARY or
                       (t == GRB.INTEGER and v.LB >= -1e-9 and v.UB <= 1 + 1e-9)
                       for v, t in zip(vars_, vtype)], dtype=bool)
    n_genint = int(np.sum((vtype == GRB.INTEGER) & ~is_bin))
    if n_genint:
        raise Skip(f"{n_genint} variabili intere generali: la pompa della "
                   f"sezione 2 e' binaria")

    # --- normalizzazione a MINIMO, dentro il modello: da qui in poi non esiste
    #     piu' alcun fattore di segno, e ogni valore riportato e' del min.
    maximize = (m.ModelSense == GRB.MAXIMIZE)
    if maximize:
        obj0 = m.getAttr("Obj", vars_)
        m.setAttr("Obj", vars_, [-float(o) for o in obj0])
        m.ObjCon = -float(m.ObjCon)
        m.ModelSense = GRB.MINIMIZE
        m.update()

    c = np.array(m.getAttr("Obj", vars_), dtype=float)
    objcon = float(m.ObjCon)          # il termine costante dell'obiettivo:
                                      # c'x qui e' SEMPRE c @ x + objcon
    lb = np.array(m.getAttr("LB", vars_), dtype=float)
    ub = np.array(m.getAttr("UB", vars_), dtype=float)

    # --- naive: la riga del bersaglio e' una riga vera del modello, aggiunta
    #     PRIMA che la pompa esista. La pompa non sapra' mai che c'e'.
    if mode == "naive":
        m.addConstr(gp.LinExpr(c.tolist(), vars_) <= U - objcon, name="objrow")
        m.update()

    A = m.getA().tocsr()
    rhs = np.array(m.getAttr("RHS", m.getConstrs()), dtype=float)
    sense = np.array(m.getAttr("Sense", m.getConstrs()))

    def _cont(mm):
        mm.Params.OutputFlag = 0
        mm.Params.Method = method       # dual simplex: riusa la base
        mm.Params.Threads = threads
        if time_limit is not None:
            # rete di sicurezza per il singolo LP: nessun LP puo' costare piu'
            # dell'intero budget della pompa (TimeLimit di Gurobi e' per
            # chiamata, non cumulativo).
            mm.Params.TimeLimit = float(time_limit)
        return mm

    lp = _cont(m.relax())
    clone = _cont(m.relax()) if need_clone else None
    # il MIP originale ha finito il suo lavoro: c, objcon, lb, ub, A, rhs e
    # sense sono gia' in numpy, e lp/clone sono copie indipendenti. Tenerlo vivo
    # significherebbe TRE modelli in memoria oltre alla CSR di A, ed e' proprio
    # sulle istanze grosse (ds, proteindesign*, rmine11) che si rischia l'OOM.
    m.dispose()

    bidx = np.flatnonzero(is_bin)
    P = dict(env=env, lp=lp, clone=clone,
             c=c, objcon=objcon, is_bin=is_bin, bidx=bidx,
             A=A, rhs=rhs, sense=sense, lb=lb, ub=ub,
             n=len(vars_), maximize=maximize,
             n_bin=int(is_bin.sum()), n_cont=int((~is_bin).sum()),
             n_cons=len(rhs), name=os.path.basename(path))
    # bound delle sole binarie: servono a complete() per non chiedere a Gurobi un
    # LP gia' condannato quando una perturbazione ha ribaltato una binaria fissa
    P["blb"], P["bub"] = lb[bidx], ub[bidx]
    if clone is not None:
        cv = clone.getVars()
        P["clone_vars"] = cv
        P["clone_bvars"] = [cv[j] for j in bidx]
    # maschere per il controllo dei bound (Gurobi usa +-1e100 per l'infinito)
    P["fin_l"] = np.isfinite(lb) & (lb > -GRB.INFINITY)
    P["fin_u"] = np.isfinite(ub) & (ub < GRB.INFINITY)
    P["slb"] = np.maximum(1.0, np.abs(np.where(P["fin_l"], lb, 0.0)))
    P["sub"] = np.maximum(1.0, np.abs(np.where(P["fin_u"], ub, 0.0)))
    return P


def feasible(P, x, tol):
    """Ammissibilita' di x per il modello di riferimento, con tolleranza
    RELATIVA tol: TUTTE le righe (fp.violation), TUTTI i bound, e l'integralita'
    delle variabili intere. Le righe sono quelle di P["A"]: per il braccio naive
    comprendono la riga del bersaglio, per gli altri no.

    CONVENZIONE DI TOLLERANZA, ereditata da fp.py e non cambiata qui perche' e'
    quella con cui e' stata prodotta la sezione 2 del paper: la violazione di
    ogni riga e' divisa per max(1, |rhs|) e quella di ogni bound per
    max(1, |bound|). E' RELATIVA, e su una riga con rhs grande e' quindi piu'
    larga della FeasibilityTol di Gurobi, che e' assoluta (1e-6). Per questo il
    punto dichiarato di successo viene poi rivalidato da validate(), che ripassa
    dal solutore coi suoi default: quello, e non questo, e' il metro con cui si
    scrive nel paper che una soluzione e' stata trovata."""
    vmax, _ = fp_violation(P, x)
    if vmax > tol:
        return False
    fl, fu = P["fin_l"], P["fin_u"]
    if np.any((P["lb"][fl] - x[fl]) / P["slb"][fl] > tol):
        return False
    if np.any((x[fu] - P["ub"][fu]) / P["sub"][fu] > tol):
        return False
    b = P["is_bin"]
    if b.any() and float(np.max(np.abs(x[b] - np.round(x[b])))) > tol:
        return False
    return True


def complete(P, x_hat, S, tol, tl_left):
    """Recupero di FGL 2005, sez. 3.2. Fissa le variabili intere a x^ nel clone
    continuo del modello (senza alcuna riga sull'obiettivo, salvo il braccio
    naive dove la riga fa parte del modello) e minimizza c'x sui vincoli
    originali. Ritorna la coppia (valore, punto), oppure (None, None).

    Gli status di Gurobi NON sono tutti uguali e vanno contati a parte: prima
    qualunque status diverso da OPTIMAL finiva in n_completion_infeasible, cosi'
    un LP semplicemente INTERROTTO dal tempo veniva letto come "il clone non ha
    soluzione". Il punto ottimo, poi, passa comunque da feasible() con la stessa
    tolleranza RELATIVA del braccio test: i due bracci devono usare lo stesso
    metro, non la parola di Gurobi contro il nostro test.

    Nessuna stampa: qui si passa una volta per iterazione, e su un'istanza da
    7000 giri qualunque riga su stderr diventa un file di log piu' grande dei
    dati. Tutto quello che c'e' da sapere e' nei contatori del JSON."""
    cl, cb = P["clone"], P["clone_bvars"]
    v = x_hat[P["bidx"]]
    # x^ FUORI dai bound della variabile: succede quando una perturbazione
    # ribalta una binaria fissata (lb = ub). Fissare LB = UB = x^ renderebbe il
    # clone infeasible di sicuro: si conta e si risparmia l'LP.
    if np.any(v < P["blb"] - tol) or np.any(v > P["bub"] + tol):
        S["n_completion_infeasible"] += 1
        return None, None
    v = v.tolist()
    cl.setAttr("LB", cb, v)
    cl.setAttr("UB", cb, v)
    cl.Params.TimeLimit = tl_left
    cl.optimize()
    S["n_completion_lp"] += 1
    st = cl.Status
    if st == GRB.OPTIMAL:
        x = np.array(cl.getAttr("X", P["clone_vars"]), dtype=float)
        if feasible(P, x, tol):
            # ObjVal comprende gia' la costante ObjCon
            return float(cl.ObjVal), x
        S["n_completion_rejected"] += 1
        return None, None
    if st == GRB.INFEASIBLE:
        S["n_completion_infeasible"] += 1
    elif st == GRB.TIME_LIMIT:
        S["n_completion_timelimit"] += 1
    else:
        # UNBOUNDED / INF_OR_UNBD / NUMERIC e compagnia. Un clone ILLIMITATO
        # sarebbe in teoria un successo (esistono punti ammissibili di costo
        # arbitrariamente basso), ma non abbiamo un punto da esibire e le
        # istanze della campagna sono limitate: si conta, e lo status finisce
        # nel JSON invece che su stderr.
        S["n_completion_other"] += 1
        S["completion_status_other"] = int(st)
    return None, None


def validate(path, x, best_obj, S, threads=1):
    """VALIDAZIONE INDIPENDENTE del punto di successo, fuori dal budget.

    feasible() misura con la tolleranza RELATIVA di fp.py (vedi la sua
    docstring); qui si chiede al solutore, coi SUOI default (FeasibilityTol
    assoluta 1e-6), se il punto sta davvero nel poliedro: il modello viene
    RILETTO dall'MPS -- quindi senza nessuna riga aggiunta da noi, neanche
    quella del braccio naive -- TUTTE le variabili vengono fissate al punto
    trovato e si risolve. validated=1 se lo status e' OPTIMAL e il valore
    coincide con best_obj entro 1e-6 relativo.

    Il tempo di tutto questo sta in validate_time e NON entra ne' in
    time_to_success ne' in time_total: non e' tempo speso a cercare."""
    t = time.perf_counter()
    env = m = None
    try:
        env = gp.Env(params={"OutputFlag": 0})
        m = gp.read(path, env=env)
        m.Params.OutputFlag = 0
        m.Params.Threads = threads
        vs = m.getVars()
        xs = [float(z) for z in x]
        m.setAttr("LB", vs, xs)
        m.setAttr("UB", vs, xs)
        m.optimize()
        S["validate_status"] = int(m.Status)
        if m.Status == GRB.OPTIMAL:
            # ObjVal e' nel senso ORIGINALE del modello riletto: best_obj e U
            # vivono nel senso di MINIMO, quindi su un massimo va negato.
            z = float(m.ObjVal)
            if m.ModelSense == GRB.MAXIMIZE:
                z = -z
            S["validate_obj"] = z
            S["validated"] = int(abs(z - best_obj) <= TOL * max(1.0, abs(best_obj)))
        else:
            S["validated"] = 0
    except Exception as e:                                   # noqa: BLE001
        S["validated"] = 0
        S["validate_status"] = f"{type(e).__name__}: {e}"
    finally:
        if m is not None:
            m.dispose()
        if env is not None:
            env.dispose()
        S["validate_time"] = time.perf_counter() - t


def _key(v):
    """Chiave dell'arrotondamento per il rilevamento dei cicli. E' il digest dei
    byte invece dei byte stessi (fp.py): stesso test di appartenenza, ma memoria
    costante -- qui le iterazioni sono limitate dal TEMPO, non da 200, e su
    un'istanza con 10^4 binarie l'insieme dei byte esploderebbe.

    L'array va prima a INT8: np.round(-1e-15) vale -0.0, che in float64 ha byte
    diversi da 0.0 e darebbe una chiave diversa per lo stesso arrotondamento --
    la finestra di ciclo non scatterebbe mai. Su 0/1 int8 il problema non esiste,
    e il digest costa otto volte meno byte da leggere."""
    return hashlib.blake2b(np.asarray(v).astype(np.int8).tobytes(),
                           digest_size=16).digest()


# --------------------------------------------------------------------------
# le righe di PRESSIONE (--pressure)
# --------------------------------------------------------------------------

PRESSURE_KINDS = ("cut", "reflect", "track", "lb", "lbmove", "sgn", "card",
                  "nogood")
NEEDS_INC = ("lb", "lbmove", "card")  # senza --incumbent non hanno senso: errore
# le SPEC che governano la STESSA riga: di ogni gruppo se ne puo' usare una sola
OWNS_OBJROW = ("cut", "reflect", "track")   # la riga c'x <= U'
OWNS_LBROW = ("lb", "lbmove")         # la riga Delta(x, x_c) <= K


def parse_pressure(text):
    """'reflect:0.02+lb:0.1' -> [(kind, [numeri], testo), ...], gia' validato.

    Le SPEC si combinano col '+' e ognuna compare al piu' una volta: due 'lb'
    con raggi diversi sarebbero due righe che si contraddicono, e due SPEC
    sullo stesso oggetto -- cut e reflect sulla riga dell'obiettivo, lb e
    lbmove sulla palla di local branching -- sarebbero due padroni della stessa
    riga."""
    specs, seen = [], set()
    for piece in text.split("+"):
        piece = piece.strip()
        if not piece:
            raise BadOption("--pressure: SPEC vuota in %r" % text)
        bits = piece.split(":")
        kind = bits[0].strip()
        if kind not in PRESSURE_KINDS:
            raise BadOption("--pressure: SPEC sconosciuta %r (ammesse: %s)"
                            % (kind, "|".join(PRESSURE_KINDS)))
        if kind in seen:
            raise BadOption("--pressure: SPEC %r ripetuta in %r" % (kind, text))
        seen.add(kind)
        specs.append((kind, _check_spec(kind, [b.strip() for b in bits[1:]], piece),
                      piece))
    for group, what in ((OWNS_OBJROW, "la riga c'x <= U'"),
                        (OWNS_LBROW, "la riga di local branching")):
        if len(seen.intersection(group)) > 1:
            raise BadOption("--pressure: %s governano la STESSA cosa (%s): se ne "
                            "puo' dare una sola" % ("/".join(group), what))
    return specs


def _num(tok, piece, what):
    try:
        return float(tok)
    except ValueError:
        raise BadOption("--pressure %r: %s non e' un numero (%r)"
                        % (piece, what, tok))


def _grow(tok, piece):
    """Il terzo campo di lb/lbmove: la sola parola 'grow'. E' un interruttore,
    non un numero -- vale la pena che si legga come tale nella riga ARMS del
    runner (completion:lb:0.1:grow)."""
    if tok.lower() == "grow":
        return 1.0
    raise BadOption("--pressure %r: l'ultimo campo puo' essere solo la parola "
                    "'grow' (K raddoppia anche dopo --stall-relax giri senza "
                    "nessun punto ammissibile), non %r" % (piece, tok))


def _check_spec(kind, raw, piece):
    """Arita', tipo e intervalli di una SPEC; ritorna i parametri NORMALIZZATI
    (sempre numeri: 'grow' diventa 1.0, e i default assenti sono riempiti). Un
    parametro fuori intervallo deve fermare la corsa SUBITO: passasse, la riga
    sarebbe muta (w = 0) o infeasible (w >= 1) e il braccio finirebbe
    nell'aggregato come se avesse lavorato."""
    def n(k):
        if len(raw) != k:
            raise BadOption("--pressure %r: servono %d parametri, ce ne sono %d"
                            % (piece, k, len(raw)))
    if kind in ("cut", "sgn", "card", "nogood"):
        n(1)
        v = [_num(raw[0], piece, {"cut": "w", "sgn": "w", "card": "k",
                                  "nogood": "m"}[kind])]
        if kind == "cut" and not 0.0 <= v[0] < 1.0:
            raise BadOption("--pressure %r: w deve stare in [0,1)" % piece)
        if kind == "sgn" and not 0.0 <= v[0] <= 1.0:
            raise BadOption("--pressure %r: w deve stare in [0,1]" % piece)
        if kind == "card" and not 0.0 < v[0] < 1.0:
            raise BadOption("--pressure %r: k deve stare in (0,1)" % piece)
        if kind == "nogood" and (v[0] < 1.0 or v[0] != int(v[0])):
            raise BadOption("--pressure %r: m deve essere un intero >= 1" % piece)
        return v
    if kind == "track":
        # eta ha un default: 'track' da solo e' una SPEC legittima
        if len(raw) > 2:
            raise BadOption("--pressure %r: serve [eta[:wmax]]" % piece)
        v = [_num(raw[0], piece, "eta") if len(raw) >= 1 else 0.5,
             _num(raw[1], piece, "wmax") if len(raw) == 2 else 0.5]
        if not 0.0 < v[0] <= 1.0:
            raise BadOption("--pressure %r: eta deve stare in (0,1]" % piece)
        if not 0.0 <= v[1] < 1.0:
            raise BadOption("--pressure %r: wmax deve stare in [0,1)" % piece)
        return v
    if kind == "reflect":
        if not 1 <= len(raw) <= 2:
            raise BadOption("--pressure %r: serve wmin[:wmax]" % piece)
        v = [_num(raw[0], piece, "wmin")]
        v.append(_num(raw[1], piece, "wmax") if len(raw) == 2 else 0.5)
        if not 0.0 <= v[0] < 1.0 or not 0.0 <= v[1] < 1.0:
            raise BadOption("--pressure %r: wmin e wmax devono stare in [0,1)" % piece)
        if v[1] < v[0]:
            raise BadOption("--pressure %r: wmax < wmin (la riga scenderebbe "
                            "sopra il punto di partenza)" % piece)
        return v
    # lb e lbmove: k, piu' l'interruttore 'grow'
    if not 1 <= len(raw) <= 2:
        raise BadOption("--pressure %r: serve k[:grow]" % piece)
    v = [_num(raw[0], piece, "k")]
    v.append(_grow(raw[1], piece) if len(raw) == 2 else 0.0)
    if not 0.0 < v[0] <= 1.0:
        raise BadOption("--pressure %r: k deve stare in (0,1]" % piece)
    return v


def read_incumbent(path, P, notes):
    """Il punto del pilota, nel formato scritto da write_incumbent(): una riga
    per BINARIA A 1 con l'indice della variabile nel modello, le altre a 0. Le
    righe vuote e quelle che iniziano per '#' sono intestazione.

    Un indice fuori intervallo e' un errore (file di un'ALTRA istanza: la riga
    di local branching sarebbe costruita su variabili sbagliate e nessuno se ne
    accorgerebbe). Un indice che punta a una continua si annota e si ignora: le
    SPEC guardano solo le binarie.

    Ritorna anche il VALORE del punto, letto dall'"obj=" dell'intestazione: a
    lbmove serve per sapere quando il recupero ha trovato qualcosa di meglio
    del centro corrente. Se l'intestazione non c'e' il valore e' None, e il
    primo punto recuperato prende comunque il posto del centro."""
    x = np.zeros(P["n"])
    obj = None
    n_on = n_nonbin = 0
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if line.startswith("#"):
                for tok in line[1:].split():
                    if tok.startswith("obj="):
                        try:
                            obj = float(tok[4:])
                        except ValueError:
                            pass
                continue
            if not line:
                continue
            try:
                j = int(line.split()[0])
            except ValueError:
                raise BadOption("--incumbent %s: riga %d non e' un indice intero (%r)"
                                % (path, ln, line[:40]))
            if not 0 <= j < P["n"]:
                raise BadOption("--incumbent %s: riga %d, indice %d fuori da [0,%d): "
                                "e' il punto di un'altra istanza?"
                                % (path, ln, j, P["n"]))
            if not P["is_bin"][j]:
                n_nonbin += 1
                continue
            x[j] = 1.0
            n_on += 1
    if n_nonbin:
        notes.append("incumbent: %d indici non binari ignorati" % n_nonbin)
    return x, n_on, obj


def write_incumbent(path, P, x, obj, name):
    """Il punto trovato, nel formato che --incumbent rilegge. Lo scrive OGNI
    corsa che trova un punto ammissibile e ha un --out: al pilota serve (e' lui
    che genera l'incumbent dello scenario), agli altri non fa male."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    bidx = P["bidx"]
    on = bidx[np.round(x[bidx]) > 0.5]
    with open(path, "w") as f:
        f.write("# inst=%s obj=%.15g nb=%d\n"
                % (name, float(obj), int(P["n_bin"])))
        for j in on:
            f.write("%d\n" % int(j))


class Pressure:
    """Le righe di pressione dell'LP di proiezione: costruzione, movimento,
    contatori. Tutto quello che tocca sta in P["lp"] -- MAI in P["clone"] (il
    completamento deve vedere i vincoli originali) e mai in P["A"] (il test di
    ammissibilita' pure).

    Il ciclo di vita, nell'ordine in cui la pompa lo attraversa:
      setup()         dopo il primo LP: legge l'incumbent, paga l'eventuale LP
                      di sgn e aggiunge le righe.
      on_iteration()  a ogni giro che NON ha raggiunto il bersaglio: reflect
                      muove U', lbmove sposta il centro della palla, nogood
                      aggiunge la riga tabu.
      relax()         quando l'LP di proiezione si svuota: allarga la riga che
                      lo puo' aver causato (lb raddoppia K, card apre il RHS).
      finish()        i contatori nel JSON."""

    def __init__(self, args, specs, notes=None):
        self.args = args
        self.specs = specs
        self.par = {k: v for k, v, _ in specs}
        self.notes = list(notes or [])
        self.on = set()                  # le SPEC davvero attive
        self.objrow = None               # riga c'x <= U'   (cut / reflect)
        self.lbrow = self.sgnrow = self.cardrow = None
        self.ng = collections.deque()    # righe tabu, dalla piu' vecchia
        self.ng_max = 0
        self.stall = 0                   # giri a vuoto, per reflect
        self.stall_lb = 0                # giri a vuoto, per lb/lbmove
        self.track_eta = 0.0             # guadagno del controllo di track
        self.track_e_sum = 0.0           # somma degli e, per track_e_mean
        self.track_e_n = 0
        self.lb_moving = False           # il centro insegue il recupero?
        self.lb_grow = False             # K raddoppia anche per stallo?
        self.lb_center = None            # x_c sulle sole binarie (0/1)
        self.lb_val = None               # valore del centro: None = +infinito
        self.up = None

    # ---------------------------------------------------------------- costruzione

    def setup(self, P, S, U, z_lp, x_t, left):
        """Le righe entrano nell'LP DOPO il primo LP: z_LP resta il bound vero.
        x_t e' l'iterato del primo LP, cioe' quello da cui la pompa ricavera'
        il primo arrotondamento: sgn lo usa come riferimento se manca
        l'incumbent."""
        self.P, self.S, self.U, self.z_lp = P, S, U, z_lp
        self.lp = P["lp"]
        self.lpv = self.lp.getVars()
        self.G = U - z_lp
        self.nb = int(P["n_bin"])
        self.tol = TOL * max(1.0, abs(U))

        bidx = P["bidx"]
        # l'arrotondamento del PRIMO giro: a it = 0 nessuna perturbazione lo
        # tocca (x_hat_prev e' None e il restart forzato non e' ancora scaduto),
        # quindi questo e' esattamente il primo x^ della pompa.
        x_hat0 = x_t.copy()
        x_hat0[bidx] = np.abs(np.round(x_t[bidx]))

        self.xinc = self.xinc_obj = None
        if self.args.incumbent:
            self.xinc, n_on, self.xinc_obj = read_incumbent(
                self.args.incumbent, P, self.notes)
            self.notes.append("incumbent: %d binarie a 1 su %d, obj=%s"
                              % (n_on, self.nb, self.xinc_obj))
        for k in NEEDS_INC:
            if k in self.par and self.xinc is None:
                raise BadOption("--pressure %s richiede --incumbent: e' il punto "
                                "del pilota (una riga per binaria a 1), scritto "
                                "in <out>.inc accanto al JSON" % k)

        # sgn per PRIMA: il suo smin e' il minimo su P, il poliedro NUDO. Se la
        # calcolasse dopo, le altre righe l'avrebbero gia' ristretto.
        if "sgn" in self.par:
            self._sgn(x_hat0, left)
        if "cut" in self.par:
            self._cut()
        if "reflect" in self.par:
            self._reflect()
        if "track" in self.par:
            self._track()
        for k in OWNS_LBROW:
            if k in self.par:
                self._lb(k)
        if "card" in self.par:
            self._card()
        if "nogood" in self.par:
            self.ng_max = int(self.par["nogood"][0])
            self.on.add("nogood")
        self.lp.update()
        self._report()

    def _add(self, idx, coef, sense, rhs, name):
        e = gp.LinExpr([float(a) for a in coef], [self.lpv[int(j)] for j in idx])
        tc = (e <= float(rhs)) if sense == "<" else (e >= float(rhs))
        return self.lp.addConstr(tc, name=name)

    def _no_gap(self, kind):
        """G = U - z_LP <= 0: non c'e' nessuna fascia da scavare (il bersaglio
        e' sotto il bound, dato sporco che il runner intercetta con
        best_below_lp). La SPEC si spegne e resta scritto nel JSON."""
        if self.G > 0.0:
            return False
        self.notes.append("%s: G = U - z_LP = %.15g <= 0, SPEC spenta" % (kind, self.G))
        return True

    def _cut(self):
        """La riga di oggi: c'x <= U - w G, ferma per tutta la corsa. E'
        --Uprime scritto in unita' di gap."""
        if self._no_gap("cut"):
            return
        self.up = self.U - self.par["cut"][0] * self.G
        self._obj_row()
        self.on.add("cut")

    def _reflect(self):
        """La stessa riga, ma che si muove. Due estremi e una casa:
             up_home  = U - wmin G   il punto di partenza, dove si torna
             up_floor = il piu' alto fra U - wmax G e z_LP + eps: sotto non si
                        scende MAI, altrimenti l'LP di proiezione si svuota."""
        if self._no_gap("reflect"):
            return
        wmin, wmax = self.par["reflect"]
        self.up_home = self.U - wmin * self.G
        self.up_floor = max(self.U - wmax * self.G,
                            self.z_lp + TOL * max(1.0, abs(self.z_lp)))
        self.up = max(self.up_home, self.up_floor)
        self._obj_row()
        self.on.add("reflect")

    def _track(self):
        """La riga che insegue il COSTO DELL'ARROTONDATO.

        Il limite di reflect, misurato nel primo giro ad a = 0.9: reagisce ai
        soli punti AMMISSIBILI di valore sopra U, e nel 60-93% dei fallimenti
        quei punti non esistono -- la riga non si muove mai e il braccio e' un
        cut travestito. L'arrotondato x^, invece, c'e' a ogni giro: e' l'unico
        segnale sempre disponibile su dove sta andando la pompa rispetto al
        bersaglio.

        Controllo proporzionale, con e = (c'x^ - U)/G l'errore relativo:
            U' <- U' - eta e G,     U' in [U - wmax G, U],  U' >= z_LP + eps
        e U' che parte da U (nessuna fascia: la fascia la scava il controllo).
        e > 0 (arrotondato sopra la soglia) fa SCENDERE la riga e tira giu'
        l'iterato; e < 0 (arrotondato sotto la soglia ma non ammissibile: il
        problema non e' piu' il costo) la fa RISALIRE e restituisce spazio alla
        feasibility. Il pavimento impedisce di svuotare l'LP, il soffitto U
        impedisce alla riga di diventare piu' larga del bersaglio -- sopra U non
        avrebbe piu' alcun senso, il punto va comunque sotto U per uscire."""
        if self._no_gap("track"):
            return
        self.track_eta, wmax = self.par["track"]
        self.up_floor = max(self.U - wmax * self.G,
                            self.z_lp + TOL * max(1.0, abs(self.z_lp)))
        self.up_ceil = self.U
        self.up = self._track_clamp(self.U)
        self._obj_row()
        self.on.add("track")

    def _track_clamp(self, up):
        """U' dentro [pavimento, soffitto]. Col pavimento sopra il soffitto
        (gap G cosi' piccolo che z_LP + eps supera U) vince il pavimento: e'
        l'unico dei due che, violato, svuota l'LP di proiezione."""
        return max(self.up_floor, min(self.up_ceil, up))

    def _track_step(self, x_hat):
        """Un passo del controllo, sull'arrotondato che sta per entrare
        nell'LP -- cioe' DOPO le perturbazioni, quello vero."""
        P = self.P
        e = (float(P["c"] @ x_hat) + P["objcon"] - self.U) / self.G
        self.track_e_sum += e
        self.track_e_n += 1
        old = self.up
        self.up = self._track_clamp(self.up - self.track_eta * e * self.G)
        if self.up == old:
            return False                  # gia' contro un estremo: niente da riscrivere
        self._obj_row()
        if abs(self.up - old) > 1e-9 * max(1.0, abs(self.U)):
            self.S["n_uprime_changes"] += 1
        return True

    def _obj_row(self):
        """Crea o sposta la riga sull'obiettivo. U' comprende la costante
        dell'obiettivo, la riga no: da qui il - objcon (come la riga statica)."""
        P, S = self.P, self.S
        rhs = self.up - P["objcon"]
        if self.objrow is None:
            idx = np.flatnonzero(P["c"])
            self.objrow = self._add(idx, P["c"][idx], "<", rhs, "pres_obj")
        else:
            self.objrow.RHS = rhs
        S["uprime_final"] = self.up
        S["uprime_min"] = (self.up if S["uprime_min"] is None
                           else min(S["uprime_min"], self.up))
        S["uprime_max"] = (self.up if S["uprime_max"] is None
                           else max(S["uprime_max"], self.up))

    def _lb(self, kind):
        """Local branching (Fischetti-Lodi 2003) attorno a un centro x_c:
             sum_{xc_j=1} (1 - x_j) + sum_{xc_j=0} x_j <= K
        cioe', in forma di riga,  sum_j (1 - 2 xc_j) x_j <= K - n1(x_c).

        kind = 'lb'      il centro e' x_inc e non si muove piu';
        kind = 'lbmove'  il centro INSEGUE il recupero: ogni punto ammissibile
                         di valore migliore del centro corrente diventa il
                         nuovo centro, anche se sta sopra U. E' la palla di
                         local branching che scivola giu' lungo la sequenza dei
                         punti recuperati, invece di restare inchiodata alla
                         soluzione del pilota.
        Con ':grow' K raddoppia anche dopo --stall-relax giri a vuoto, non solo
        quando l'LP di proiezione si svuota."""
        bidx = self.P["bidx"]
        if self.nb == 0:
            self.notes.append("%s: nessuna binaria, SPEC spenta" % kind)
            return
        k, grow = self.par[kind]
        self.lb_kind = kind
        self.lb_moving = (kind == "lbmove")
        self.lb_grow = bool(grow)
        self.lb_center = np.round(self.xinc[bidx])
        self.lb_val = self.xinc_obj
        self.lb_n1 = float(self.lb_center.sum())
        self.lbK0 = float(min(self.nb, max(1, int(round(k * self.nb)))))
        self.lbK = self.lbK0
        self.lbrow = self._add(bidx, 1.0 - 2.0 * self.lb_center, "<",
                               self.lbK - self.lb_n1, "pres_lb")
        if self.lb_moving and self.lb_val is None:
            self.notes.append("lbmove: l'incumbent non porta un obj=, il primo "
                              "punto recuperato prende comunque il centro")
        self.on.add(kind)

    def _lb_move(self, x):
        """Sposta il centro della palla sul punto x (le sue sole binarie) e
        RISCRIVE la riga: i coefficienti valgono 1 - 2 x_c e cambiano di segno
        esattamente dove il centro e' cambiato, il RHS segue n1(x_c). Si tocca
        solo cio' che cambia (chgCoeff), non si rifa' la riga: cosi' Gurobi
        tiene la base e l'LP riparte a caldo.

        K torna al valore iniziale: il centro nuovo e' un altro posto, e il
        raggio allargato per lo stallo del centro vecchio non c'entra piu'."""
        bidx = self.P["bidx"]
        b = np.round(x[bidx])
        chg = np.flatnonzero(b != self.lb_center)
        for j in chg:
            self.lp.chgCoeff(self.lbrow, self.lpv[int(bidx[j])],
                             float(1.0 - 2.0 * b[j]))
        self.lb_center = b
        self.lb_n1 = float(b.sum())
        self.lbK = self.lbK0
        self.lbrow.RHS = self.lbK - self.lb_n1
        self.S["n_center_moves"] += 1
        return chg.size

    def _lb_step(self, v, x):
        """Il giro di lb/lbmove. Ritorna True se la riga e' cambiata.

        Due mosse distinte, e non si escludono:
          * il CENTRO segue il miglior punto recuperato (solo lbmove);
          * K RADDOPPIA dopo --stall-relax giri senza NESSUN punto ammissibile
            (solo con ':grow'): la palla e' evidentemente troppo stretta perche'
            il recupero ci trovi qualcosa dentro."""
        if v is None:
            self.stall_lb += 1
            if not self.lb_grow or self.stall_lb < self.args.stall_relax:
                return False
            self.stall_lb = 0
            if self.lbK >= self.nb:
                return False              # gia' ridondante: non c'e' piu' nulla da aprire
            self.lbK = min(float(self.nb), 2.0 * self.lbK)
            self.lbrow.RHS = self.lbK - self.lb_n1
            self.S["n_lb_relax"] += 1
            return True
        self.stall_lb = 0
        if not self.lb_moving:
            return False
        if self.lb_val is not None and v >= self.lb_val - self.tol:
            return False                  # non e' meglio del centro: si resta
        self.lb_val = v
        self._lb_move(x)
        return True

    def _card(self):
        """Cardinalita': meno binarie a 1 di quante ne ha l'incumbent. Su molti
        modelli di copertura/assegnamento e' il modo piu' diretto di scendere,
        e non guarda i costi."""
        bidx = self.P["bidx"]
        n1 = float(np.round(self.xinc[bidx]).sum())
        if n1 <= 0.0:
            self.notes.append("card: l'incumbent ha zero binarie a 1, SPEC spenta")
            return
        self.card_rhs = (1.0 - self.par["card"][0]) * n1
        self.cardrow = self._add(bidx, np.ones(bidx.size), "<",
                                 self.card_rhs, "pres_card")
        self.on.add("card")

    def _sgn(self, x_hat0, left):
        """Il cutoff "nei segni": s_j = sign(c_j) sulle sole binarie, e la riga
             s'x <= s'x_ref - w (s'x_ref - smin)
        con smin = min{s'x : x in P} da UN LP in piu' (dentro il budget, contato
        in n_lp_extra). E' il cutoff privato delle MAGNITUDINI dei costi, che su
        obiettivi molto sbilanciati sono quelle che rendono la riga ostile
        all'arrotondamento: qui ogni binaria pesa uno."""
        P, S = self.P, self.S
        bidx = P["bidx"]
        s = np.zeros(P["n"])
        s[bidx] = np.sign(P["c"][bidx])
        idx = np.flatnonzero(s)
        if idx.size == 0:
            self.notes.append("sgn: costo nullo su tutte le binarie, SPEC spenta")
            return
        lp, lpv = self.lp, self.lpv
        lp.setAttr("Obj", lpv, s.tolist())
        lp.Params.TimeLimit = left()
        lp.optimize()
        if lp.Status != GRB.OPTIMAL:
            self.notes.append("sgn: LP per smin non ottimo (status %s), SPEC spenta"
                              % lp.Status)
            return
        S["n_lp_extra"] += 1
        # ObjVal comprenderebbe ObjCon, che con questo obiettivo non c'entra
        smin = float(np.asarray(lp.getAttr("X", lpv), dtype=float) @ s)
        if self.xinc is not None:
            xref, why = self.xinc, "incumbent"
        else:
            xref, why = x_hat0, "primo arrotondamento x^ (nessun --incumbent)"
        sref = float(xref @ s)
        gap = sref - smin
        if gap <= 0.0:
            self.notes.append("sgn: s'x_ref - smin = %.15g <= 0, SPEC spenta" % gap)
            return
        rhs = sref - self.par["sgn"][0] * gap
        self.sgnrow = self._add(idx, s[idx], "<", rhs, "pres_sgn")
        self.notes.append("sgn: riferimento = %s, s'x_ref=%.15g smin=%.15g rhs=%.15g"
                          % (why, sref, smin, rhs))
        self.on.add("sgn")

    # ------------------------------------------------------------------ movimento

    def on_iteration(self, x_hat, v, x):
        """Un giro che NON ha raggiunto il bersaglio. v e' il valore del miglior
        punto ammissibile recuperato in questo giro e x quel punto (None
        entrambi se non ce n'e' stato nessuno)."""
        moved = False
        if "reflect" in self.on:
            moved |= self._reflect_step(v)
        if "track" in self.on:
            moved |= self._track_step(x_hat)
        if self.lbrow is not None:
            moved |= self._lb_step(v, x)
        if "nogood" in self.on and (v is None or v > self.U + self.tol):
            self._nogood(x_hat)
            moved = True
        if moved:
            self.lp.update()

    def _reflect_step(self, v):
        """La riflessione. Un punto ammissibile di valore v > U dice che da
        quella parte del poliedro si atterra TROPPO IN ALTO: si specchia v sotto
        la soglia (2U - v) e si chiede all'LP di scendere almeno fin li'. Se
        invece per --stall-relax giri non arriva NIENTE, la riga e' troppo bassa
        e si rilassa di meta' strada verso casa."""
        S = self.S
        if v is None:
            self.stall += 1
            if self.stall < self.args.stall_relax:
                return False
            self.stall = 0
            if self.up_home - self.up <= 1e-12 * max(1.0, abs(self.up_home)):
                return False                       # gia' a casa: niente da fare
            self.up = min(self.up_home, self.up + 0.5 * (self.up_home - self.up))
        else:
            self.stall = 0
            if v <= self.U + self.tol:
                return False                       # sotto la soglia: si esce, non si riflette
            cand = max(self.up_floor, min(self.up, 2.0 * self.U - v))
            if cand >= self.up - 1e-12 * max(1.0, abs(self.up)):
                return False                       # gia' piu' in basso dello specchio
            self.up = cand
        self._obj_row()
        S["n_uprime_changes"] += 1
        return True

    def _nogood(self, x_hat):
        """Riga tabu sull'arrotondamento appena scartato:
             sum_{x^_j=1} (1 - x_j) + sum_{x^_j=0} x_j >= 1
        cioe' sum_j (1 - 2 x^_j) x_j >= 1 - n1. Fra i punti 0-1 taglia via
        esattamente x^ e nessun altro, e nel continuo spinge l'iterato altrove.
        Se ne tengono al piu' m: la piu' vecchia esce."""
        bidx = self.P["bidx"]
        b = np.round(x_hat[bidx])
        r = self._add(bidx, 1.0 - 2.0 * b, ">", 1.0 - float(b.sum()), "pres_ng")
        self.ng.append(r)
        self.S["n_nogood_added"] += 1
        while len(self.ng) > self.ng_max:
            self.lp.remove(self.ng.popleft())

    def relax(self):
        """L'LP di proiezione si e' svuotato: si allarga la riga che lo puo'
        aver causato. Ritorna True se qualcosa e' cambiato (vale la pena
        riprovare), False se non c'e' piu' niente da allargare -- e allora e'
        davvero un errore, non una riga troppo stretta.

        Solo lb/lbmove e card: cut/reflect stanno sopra z_LP per costruzione,
        sgn e' un semispazio che contiene x_ref, e le righe tabu tagliano un
        vertice 0-1 per volta."""
        if self.lbrow is not None and self.lbK < self.nb:
            # K = nb rende la riga ridondante: oltre non ha senso andare
            self.lbK = min(float(self.nb), 2.0 * self.lbK)
            self.lbrow.RHS = self.lbK - self.lb_n1
            self.S["n_lb_relax"] += 1
            self.lp.update()
            return True
        if self.cardrow is not None and self.card_rhs < self.nb:
            new = min(float(self.nb), self.card_rhs * 1.1)
            if new <= self.card_rhs + 1e-12:      # RHS ~ 0: il 10% non muove nulla
                new = min(float(self.nb), self.card_rhs + 1.0)
            self.card_rhs = new
            self.cardrow.RHS = new
            self.S["n_card_relax"] += 1
            self.lp.update()
            return True
        return False

    # -------------------------------------------------------------------- referto

    def _report(self):
        S = self.S
        S["pressure_on"] = ",".join(k for k, _, _ in self.specs if k in self.on) or None
        off = [k for k, _, _ in self.specs if k not in self.on]
        notes = list(self.notes)
        if off:
            notes.append("SPEC spente: " + ",".join(off))
        S["pressure_note"] = "; ".join(notes) if notes else None

    def finish(self):
        if self.up is not None:
            self.S["uprime_final"] = self.up
        if self.track_e_n:
            self.S["track_e_mean"] = self.track_e_sum / self.track_e_n
        self._report()


# --------------------------------------------------------------------------
# la pompa
# --------------------------------------------------------------------------

def pump(P, args, rng, S):
    """La pompa di FGL 2005 (distanza pura, alpha = 0) con il bersaglio U.

    Perturbazioni: FGL 2005 con T = 20, finestra di ciclo 3 e restart forzato
    ogni 100 iterazioni, regola di restart [-0.3, 0.7] su TUTTE le binarie; il
    solo flip debole e' ristretto alle variabili con LP non integrale (soglia
    1e-6, come SCIP). In dettaglio, e nell'ORDINE di FGL ("skip steps 7-10") e
    di SCIP (heur_feaspump.c), che e' quello che conta:

      * candidate al FLIP DEBOLE: le binarie con
        frac_gap = |x*_j - x^_j| > --frac-min. Soglia 1e-6: si escludono le sole
        integrali a tolleranza, come SCIP. (BFL 2007 usa 0.02, ma per lo
        SHIFTING del codice a interi generali; usarla qui, su un'istanza dove
        l'LP e' quasi integrale, azzera le candidate e blocca la pompa.)
      * PRIMA di tutto il RESTART FORZATO: se sono passate >= --restart-every
        iterazioni dall'ultimo restart (FGL: R = 100; SCIP: perturbfreq = 100),
        si fa il restart e basta. E' il primo controllo, non l'ultimo: chiuso in
        coda a un elif non parte mai durante uno stallo a 1-ciclo, dove il ramo
        del flip debole se lo mangia a ogni giro.
      * altrimenti, se x^ coincide con l'arrotondamento precedente, FLIP DEBOLE:
        TT ~ U[T/2, 3T/2] con T = --flip, e si ribaltano le min(TT, #candidate)
        candidate con frac_gap piu' grande. Senza candidate si passa al restart.
      * altrimenti, se x^ e' uguale a uno degli ultimi --cycle-window = 3
        arrotondamenti (FGL: "last 3 iterations"; SCIP: cyclelength = 3),
        RESTART di FGL alla lettera ("for each j in I"): per OGNI binaria j si
        estrae rho_j ~ U[-0.3, 0.7] e si ribalta j sse frac_gap_j + max(rho_j, 0)
        > 0.5, cioe' con probabilita' 0.2 + frac_gap_j, integrali comprese. La
        variante di SCIP ristretta alle frazionarie (handleCycle) su fiber era
        un no-op: 2-3 frazionarie, 3560 restart su 7100 giri, pompa ferma.
        SCIP se lo puo' permettere perche' ha il termine sull'obiettivo che
        cambia a ogni giro e si arrende dopo 10 stalli; la pompa pura no.
      * GARANZIA DI PROGRESSO: un restart che non ribalta NIENTE lascia x^
        identico, l'LP di proiezione ridara' lo stesso iterato e il giro dopo si
        ripete uguale -- livelock. Quando succede si ribaltano comunque le
        min(TT, #candidate) candidate con frac_gap maggiore; se le candidate
        sono zero (LP integrale sulle binarie: dovrebbe gia' essere un successo,
        e se non lo e' e' un problema numerico o una riga violata dalle
        continue) si ribaltano TT binarie a caso, uniformemente. Il caso e'
        contato in n_restart_forced_flip.

    n_perturb conta i flip deboli, n_restart i restart (compresi quelli con la
    garanzia di progresso). n_recovered e n_feas NON sono confrontabili fra
    naive e gli altri bracci: per naive contano gli x^ ammissibili per il
    modello RISTRETTO. Per confrontare si usano target_ok e validated.
    Scrive tutto dentro S, il dizionario del risultato."""
    lp = P["lp"]
    lpv = lp.getVars()
    c, objcon = P["c"], P["objcon"]
    bidx = P["bidx"]
    nb = P["n_bin"]
    nrm_d = np.sqrt(nb) or 1.0

    mode, U = args.mode, args.U
    tgt_tol = None if U is None else TOL * max(1.0, abs(U))
    use_completion = wants_completion(args)

    t0 = time.perf_counter()

    def left():
        """Budget RESIDUO, da rimettere PRIMA di ogni optimize(). Col budget
        intero su ogni chiamata (TimeLimit di Gurobi e' per chiamata, non
        cumulativo) un run poteva sforare di 2 TL su test e di 3 TL su
        completion, cioe' proprio il braccio che paga piu' LP per giro riceveva
        piu' secondi. Cosi' lo sforo massimo e' un LP interrotto."""
        return max(1e-3, args.time_limit - (time.perf_counter() - t0))

    # --- primo LP: min c'x sul rilassamento continuo. Da' z_LP e il primo
    #     iterato. Per il braccio naive il rilassamento contiene gia' la riga
    #     c'x <= U (e' parte del modello); per test/completion la riga c'x <= U'
    #     viene aggiunta DOPO, cosi' zlp e' sempre il vero bound del modello.
    #     Non entra in n_lp: il suo tempo e' tlp, e n_lp conta i soli LP di
    #     proiezione.
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
        S["status"] = "error"
        S["error"] = f"rilassamento non ottimo (status {lp.Status})"
        S["time_total"] = time.perf_counter() - t0
        return
    z_lp = float(lp.ObjVal)
    S["zlp"] = z_lp
    x_t = np.array(lp.getAttr("X", lpv), dtype=float)

    # --- uscita anticipata sulle istanze LENTE: se il solo primo LP costa piu'
    #     di --tlp-max, la ricognizione lo sa gia' qui e non spende l'intero
    #     budget del pilota per scoprirlo. zlp e tlp sono comunque riportati.
    if args.tlp_max is not None and S["tlp"] > args.tlp_max:
        S["status"] = "slow"
        S["time_total"] = time.perf_counter() - t0
        return

    # --- le righe di PRESSIONE (--pressure): stanno SOLO nell'LP di proiezione,
    #     mai nel clone del completamento e mai nel test di ammissibilita'.
    #     Vanno costruite QUI, dopo il primo LP e prima della riga statica: la
    #     SPEC sgn misura il suo smin sul poliedro NUDO.
    pres = None
    if args.pressure_specs:
        pres = Pressure(args, args.pressure_specs)
        pres.setup(P, S, U, z_lp, x_t, left)

    # --- la riga INTERNA c'x <= U': sta solo nell'LP di proiezione, ed e'
    #     costante per tutta la corsa (non segue mai l'incumbent). Con
    #     --pressure cut/reflect la riga sull'obiettivo la mette Pressure, e
    #     --Uprime e' rifiutato in main(): qui non c'e' nulla da aggiungere.
    if mode in ("test", "completion") and args.Uprime is not None:
        lp.addConstr(gp.LinExpr(c.tolist(), lpv) <= args.Uprime - objcon,
                     name="objcut")
        lp.update()

    # --- la fascia ADATTIVA (test-adapt / completion-adapt, Q3): la riga
    #     interna parte a U (w = 0) e scende a U - m dal giro K+1, con m la
    #     mediana dei rounding gap delta_k osservati (regola nel docstring).
    #     Il RHS si cambia sull'handle della riga; G = U - z_LP e' il gap.
    adapt = mode in ADAPT_MODES
    adapt_row = None
    adapt_G = None
    adapt_deltas = []
    adapt_up = None
    adapt_moat = 0.0
    if adapt:
        adapt_row = lp.addConstr(gp.LinExpr(c.tolist(), lpv) <= U - objcon,
                                 name="objcut")
        lp.update()
        adapt_up = U
        adapt_G = U - z_lp
        S["uprime_final"] = S["uprime_min"] = U

    def _adapt_update():
        """Dal giro K+1: m = mediana dei delta (i primi K se freeze, tutti se
        running), troncata in [0, G(1-eps)]; U' = U - m. Cambia il RHS solo se
        U' si sposta davvero."""
        nonlocal adapt_up, adapt_moat
        if adapt_G is None or adapt_G <= 0 or len(adapt_deltas) < args.adapt_k:
            return
        if args.adapt_rule in ("freeze", "abs"):
            if S["n_uprime_changes"] or len(adapt_deltas) > args.adapt_k:
                return                       # gia' congelata (o m <= 0 al giro K)
            first = adapt_deltas[:args.adapt_k]
            if args.adapt_rule == "abs":
                first = [abs(v) for v in first]
            m = float(np.median(first))
        else:
            m = float(np.median(adapt_deltas))
        m = min(max(m, 0.0), adapt_G * (1.0 - args.adapt_eps))
        new_up = U - m
        if abs(new_up - adapt_up) <= TOL * max(1.0, abs(U)):
            return                           # m ~ 0 (o invariata): riga ferma
        adapt_row.RHS = new_up - objcon
        adapt_up, adapt_moat = new_up, m
        S["n_uprime_changes"] += 1
        S["uprime_final"] = new_up
        S["uprime_min"] = min(S["uprime_min"], new_up)

    # finestra di ciclo: i digest degli ultimi --cycle-window arrotondamenti
    # (FGL: "last 3 iterations"). Prima era un insieme su TUTTA la storia, che
    # non e' la regola di FGL e con un budget a tempo cresceva senza limite.
    recent = collections.deque(maxlen=max(1, args.cycle_window))
    x_hat_prev = None
    last_restart = 0
    best_obj = None
    best_x = None
    t_first = None
    z_first = None
    status = "maxiter"

    for it in range(args.max_iter):
        S["n_iter"] = it + 1

        # ---- arrotondamento dell'iterato corrente. np.abs perche'
        #      np.round(-1e-15) vale -0.0: sul valore non cambia nulla, ma i byte
        #      di -0.0 e 0.0 sono diversi e il digest del ciclo li leggerebbe
        #      come due arrotondamenti distinti. Le binarie sono 0/1, il valore
        #      assoluto e' sicuro. (_key porta comunque a int8: cintura doppia.)
        x_hat = x_t.copy()
        x_hat[bidx] = np.abs(np.round(x_t[bidx]))
        if adapt:
            # rounding gap del giro, sull'arrotondamento PURO (prima di flip e
            # restart): delta = c'x^ - c'x~, e le continue sono le stesse.
            adapt_deltas.append(float(c[bidx] @ (x_hat[bidx] - x_t[bidx])))
            S["n_delta"] = len(adapt_deltas)

        # ---- candidate: le binarie su cui l'LP NON e' integrale. La soglia e'
        #      1e-6 come in SCIP, che esclude solo le integrali a tolleranza;
        #      BFL 2007 usa 0.02, ma per lo SHIFTING del codice a interi
        #      generali, non per decidere chi si puo' ribaltare. Con 0.02 su
        #      un'istanza dove l'LP e' quasi integrale (fiber) le candidate
        #      diventavano zero e il restart non ribaltava niente: 3780 restart
        #      su 7000 giri, tutti a vuoto.
        frac_gap = np.abs(x_t[bidx] - x_hat[bidx])
        cand = np.flatnonzero(frac_gap > args.frac_min)

        def _top(k_max):
            """Le min(k_max, #cand) candidate con frac_gap maggiore. argsort
            STABILE: a parita' di frac_gap l'ordine deve dipendere solo
            dall'indice, non dall'implementazione dell'ordinamento."""
            k = max(1, min(int(k_max), cand.size))
            return cand[np.argsort(-frac_gap[cand], kind="stable")[:k]]

        # ---- l'ordine delle perturbazioni e' quello di FGL ("skip steps 7-10")
        #      e di SCIP (heur_feaspump.c): PRIMA il restart forzato. Chiuso in
        #      un elif, come stava prima, non partiva MAI durante uno stallo a
        #      1-ciclo -- il ramo del flip debole se lo mangiava a ogni giro --
        #      ed e' esattamente il livelock visto su fiber.
        do_restart = False
        if it - last_restart >= args.restart_every:
            do_restart = True
        elif x_hat_prev is not None and np.array_equal(x_hat[bidx], x_hat_prev):
            # ---- flip debole (FGL 2005): TT ~ U[T/2, 3T/2] fra le candidate
            #      con frac_gap piu' grande, cioe' quelle su cui l'LP e' piu' in
            #      disaccordo con l'arrotondamento.
            if cand.size:
                TT = int(rng.integers(args.flip // 2, 3 * args.flip // 2 + 1))
                sel = _top(TT)
                x_hat[bidx[sel]] = 1.0 - x_hat[bidx[sel]]
                S["n_perturb"] += 1
            else:
                do_restart = True     # niente da ribaltare: si passa al restart
        elif _key(x_hat[bidx]) in recent:
            do_restart = True

        if do_restart:
            # ---- restart di FGL 2005 alla lettera, "for each j in I": rho_j ~
            #      U[-0.3, 0.7], flip sse frac_gap_j + max(rho_j, 0) > 0.5, cioe'
            #      probabilita' 0.2 + frac_gap_j per OGNI binaria, integrali
            #      comprese. NON la variante di SCIP ristretta alle frazionarie:
            #      su fiber l'LP di proiezione lascia 2-3 binarie frazionarie e
            #      quel restart era un no-op (3560 restart su 7100 giri, la
            #      pompa ferma sullo stesso arrotondamento). SCIP se lo puo'
            #      permettere perche' ha il termine sull'obiettivo che cambia a
            #      ogni giro e si arrende dopo 10 stalli; la pompa a distanza
            #      pura no.
            rho = rng.random(nb) - 0.3
            sel = np.flatnonzero(frac_gap + np.maximum(rho, 0.0) > 0.5)
            if sel.size == 0:
                # ---- GARANZIA DI PROGRESSO. Un restart che non ribalta niente
                #      lascia x^ identico: l'LP di proiezione ha lo stesso
                #      obiettivo, ridara' lo stesso iterato, e il giro dopo si
                #      ripete uguale. E' il livelock. Si ribalta comunque.
                TT = int(rng.integers(args.flip // 2, 3 * args.flip // 2 + 1))
                if cand.size:
                    sel = _top(TT)
                elif nb:
                    # nessuna frazionaria: l'LP e' integrale sulle binarie e
                    # dovrebbe gia' essere un successo. Se non lo e' (numerica,
                    # o una riga violata dalle continue), si ribalta a caso,
                    # uniformemente, pur di non restare fermi.
                    sel = rng.choice(nb, size=max(1, min(TT, nb)), replace=False)
                else:
                    sel = np.empty(0, dtype=int)
                S["n_restart_forced_flip"] += 1
            x_hat[bidx[sel]] = 1.0 - x_hat[bidx[sel]]
            S["n_restart"] += 1
            last_restart = it

        recent.append(_key(x_hat[bidx]))
        x_hat_prev = x_hat[bidx].copy()

        # ---- IL RECUPERO: da x^ a un punto ammissibile, e a che costo. Si tiene
        #      anche il PUNTO, non solo il valore: serve a validate().
        got = []
        if feasible(P, x_hat, args.feas_tol):
            S["n_feas"] += 1
            got.append((float(c @ x_hat) + objcon, x_hat.copy()))
        if use_completion:
            v, xc = complete(P, x_hat, S, args.feas_tol, left())
            if v is not None:
                got.append((v, xc))
        # il tempo si guarda DOPO il completamento: e' l'LP in piu' che paga
        # solo questo braccio, e non deve diventare tempo regalato.
        now = time.perf_counter() - t0

        iter_v = iter_x = None        # il miglior punto recuperato IN QUESTO giro
        if got:
            S["n_recovered"] += 1
            v, xv = min(got, key=lambda p: p[0])
            iter_v, iter_x = v, xv
            if t_first is None:
                t_first, z_first = now, v
            if best_obj is None or v < best_obj:
                best_obj, best_x = v, xv
            # ---- l'uscita, UNA SOLA REGOLA per tutti i bracci: esiste un punto
            #      ammissibile per i vincoli ORIGINALI di costo <= U (per naive
            #      la riga del bersaglio e' fra le originali, quindi la
            #      condizione e' automaticamente soddisfatta a meno di un
            #      epsilon di tolleranza). Il pilota, che non ha U, si ferma
            #      alla prima soluzione ammissibile.
            if mode == "pilot" or best_obj <= U + tgt_tol:
                status = "target"
                S["time_to_success"] = now
                break

        if now > args.time_limit:
            status = "timelimit"
            break

        # ---- le righe di PRESSIONE seguono la corsa: U' riflette il punto
        #      appena recuperato (o risale dopo lo stallo), le righe tabu
        #      escludono l'arrotondamento che non e' servito a niente. Si passa
        #      di qui SOLO se il bersaglio non e' stato raggiunto.
        if pres is not None:
            pres.on_iteration(x_hat, iter_v, iter_x)

        # ---- la fascia adattiva: U' = U - mediana(delta) dal giro K+1 in poi
        #      (freeze: una volta sola; running: a ogni giro). Solo se il
        #      bersaglio non e' stato raggiunto, come le righe di pressione.
        if adapt:
            _adapt_update()

        # ---- obiettivo dell'LP di proiezione: DISTANZA PURA sulle binarie
        #      (e' fp.py con alpha = 0; la normalizzazione 1/sqrt(nb) e' un
        #      fattore positivo e non cambia l'argmin). Le continue restano
        #      libere, come in fp.py.
        w = np.zeros(P["n"])
        w[bidx] = (1.0 - 2.0 * x_hat[bidx]) / nrm_d
        lp.setAttr("Obj", lpv, w.tolist())
        lp.Params.TimeLimit = left()
        lp.optimize()
        # ---- LP vuoto per colpa di una riga di pressione (lb con K troppo
        #      piccolo, card con RHS troppo stretto): si allarga e si riprova,
        #      invece di dichiarare morta la corsa. Il tetto di 64 tentativi e'
        #      solo una cintura: relax() smette da sola quando la riga e'
        #      diventata ridondante, e il TimeLimit residuo chiude comunque.
        n_retry = 0
        while (pres is not None and n_retry < 64
               and lp.Status not in (GRB.OPTIMAL, GRB.TIME_LIMIT)
               and pres.relax()):
            n_retry += 1
            lp.Params.TimeLimit = left()
            lp.optimize()
        if lp.Status == GRB.TIME_LIMIT:
            status = "timelimit"
            break
        if lp.Status != GRB.OPTIMAL:
            # LP di proiezione vuoto: succede se U' < z_LP (w > 1), oppure se
            # la riga c'x <= U del braccio naive taglia via tutto il poliedro.
            status = "error"
            if adapt:
                S["error"] = (f"LP di proiezione non ottimo (status {lp.Status}); "
                              f"fascia adattiva U'={adapt_up} (moat={adapt_moat}), "
                              f"z_LP={z_lp}")
            elif pres is None:
                S["error"] = (f"LP di proiezione non ottimo (status {lp.Status}); "
                              f"riga interna U'={args.Uprime}, z_LP={z_lp}")
            else:
                S["error"] = (f"LP di proiezione non ottimo (status {lp.Status}); "
                              f"pressure={args.pressure} (attive: "
                              f"{S.get('pressure_on')}), U'={pres.up}, "
                              f"z_LP={z_lp}")
            break
        # si conta solo un LP RISOLTO: un LP interrotto dal tempo non lo e', e
        # contarlo faceva sballare di uno il rapporto n_iter/n_lp a seconda di
        # DOVE la corsa era finita, non del braccio. Cosi' vale sempre
        # n_lp = n_iter - 1, in tutti i modi.
        S["n_lp"] += 1
        x_t = np.array(lp.getAttr("X", lpv), dtype=float)

    # ---- esito
    S["status"] = status
    S["best_obj"] = best_obj
    S["t_first_feasible"] = t_first
    S["z_first_feasible"] = z_first
    S["time_total"] = time.perf_counter() - t0
    # UNA SOLA regola di esito per tutti i bracci: success = target_ok. Prima
    # naive dichiarava successo con un metro suo (bastava un punto ammissibile
    # del modello ristretto, cioe' la tolleranza RELATIVA di riga), e
    # l'aggregato confrontava bracci misurati con righelli diversi.
    if mode == "pilot":
        S["zinc"] = best_obj
        S["target_ok"] = int(best_obj is not None)
    else:
        S["target_ok"] = int(best_obj is not None and best_obj <= U + tgt_tol)
    S["success"] = S["target_ok"]
    if U is not None and S["zlp"] is not None and args.Uprime is not None:
        den = U - S["zlp"]
        S["w_eff"] = (U - args.Uprime) / den if abs(den) > TOL else None
    if adapt:
        S["moat"] = adapt_moat
        S["uprime_final"] = adapt_up
        S["w_eff"] = (adapt_moat / adapt_G if adapt_G is not None
                      and abs(adapt_G) > TOL else None)
        if adapt_deltas:
            S["delta_med_all"] = float(np.median(adapt_deltas))
            S["delta_frac_pos"] = float(np.mean(np.array(adapt_deltas) > 0))
    if pres is not None:
        pres.finish()

    # ---- validazione indipendente, FUORI dal budget: time_total e'
    #      gia' stato scritto, e validate() misura il proprio tempo a parte.
    if S["target_ok"] and best_x is not None and not args.no_validate:
        validate(args.mps, best_x, best_obj, S, threads=args.threads)

    # ---- il punto trovato, nel formato di --incumbent: e' cosi' che il pilota
    #      consegna l'incumbent dello scenario alle SPEC lb/sgn/card. Sta FUORI
    #      dal budget e non tocca il JSON; se la scrittura fallisce lo dice su
    #      stderr (che il runner raccoglie in un .err) e la corsa resta valida --
    #      alzare qui un'eccezione trasformerebbe un successo in status=error.
    if best_x is not None and args.out:
        try:
            write_incumbent(args.out + ".inc", P, best_x, best_obj,
                            inst_name(args.mps))
        except OSError as e:                                 # noqa: BLE001
            print(f"[avviso] {args.out}.inc non scritto: {e}", file=sys.stderr)


# --------------------------------------------------------------------------

def wants_completion(args):
    """Chi paga l'LP di completamento di FGL. Di default solo il braccio
    'completion'; i due flag esistono per poter dare lo stesso recupero anche al
    pilota e al naive, se il runner lo vuole."""
    return (args.mode == "completion"
            or args.mode == "completion-adapt"
            or (args.mode == "pilot" and args.pilot_completion)
            or (args.mode == "naive" and args.naive_completion))


def inst_name(path):
    b = os.path.basename(path)
    for ext in (".gz", ".bz2", ".mps", ".lp"):
        if b.endswith(ext):
            b = b[:-len(ext)]
    return b


def new_summary(args, path):
    """Tutte le chiavi del contratto esistono SEMPRE, anche quando la corsa
    muore: il runner non deve mai trovarsi davanti a un JSON monco.

    ECCEZIONE, ed e' voluta: le chiavi della PRESSIONE esistono solo se
    --pressure e' dato. Senza l'opzione il JSON deve restare quello di prima
    chiave per chiave -- e' il vincolo di identita' dell'esperimento, l'unico
    modo di confrontare i bracci nuovi con le campagne gia' fatte. Il runner
    legge le chiavi con get() e scrive "-" dove mancano, quindi l'arita' della
    riga RES non ne soffre."""
    S = dict(
        inst=inst_name(path), file=os.path.basename(path),
        mode=args.mode, seed=args.seed,
        U=args.U, Uprime=args.Uprime, maximize=None,
        zlp=None, tlp=None, zinc=None,
        success=0, time_to_success=None, t_first_feasible=None, best_obj=None,
        n_iter=0,
        # n_lp: SOLO gli LP di proiezione. Il primo LP (quello che da' z_LP) NON
        # e' contato qui: il suo tempo e' tlp.
        n_lp=0, n_perturb=0, n_restart=0, n_restart_forced_flip=0,
        n_recovered=0,
        n_completion_lp=0, n_completion_infeasible=0,
        n_completion_timelimit=0, n_completion_other=0,
        n_completion_rejected=0, completion_status_other=None,
        time_total=0.0, status="error", error=None,
        # --- validazione indipendente del punto di successo (fuori dal budget)
        validated=None, validate_status=None, validate_obj=None,
        validate_time=None,
        # --- diagnostica, oltre al contratto
        n_var=None, n_bin=None, n_cont=None, n_cons=None, n_feas=0,
        z_first_feasible=None, target_ok=0, w_eff=None,
        time_load=None, completion_used=int(wants_completion(args)),
        alpha=0.0, flip=args.flip, time_limit=args.time_limit,
        # i tre parametri della pompa di FGL, registrati con la corsa
        frac_min=args.frac_min, cycle_window=args.cycle_window,
        restart_every=args.restart_every, tlp_max=args.tlp_max,
    )
    if args.pressure:
        S.update(
            pressure=args.pressure, pressure_on=None, pressure_note=None,
            incumbent=args.incumbent, stall_relax=args.stall_relax,
            # U' della riga sull'obiettivo (cut/reflect): finale ed estremi
            # raggiunti. La TRAIETTORIA non si salva: su una corsa da 7000 giri
            # sarebbe un file piu' grande dei dati.
            n_uprime_changes=0, uprime_final=None,
            uprime_min=None, uprime_max=None,
            n_lb_relax=0, n_card_relax=0, n_nogood_added=0, n_lp_extra=0,
            n_center_moves=0, track_e_mean=None,
        )
    if args.mode in ADAPT_MODES:
        # la fascia adattiva (Q3): chiavi SOLO in questi modi, per il vincolo
        # di identita' del JSON degli altri bracci.
        S.update(
            adapt_rule=args.adapt_rule, adapt_k=args.adapt_k,
            adapt_eps=args.adapt_eps,
            n_delta=0, moat=0.0, uprime_final=None, uprime_min=None,
            n_uprime_changes=0, delta_med_all=None, delta_frac_pos=None,
        )
    return S


def _jsonable(o):
    if isinstance(o, np.generic):
        return o.item()
    return str(o)


def emit(S, out):
    line = json.dumps(S, default=_jsonable)
    if out:
        d = os.path.dirname(out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out, "w") as f:
            f.write(line + "\n")
    print(line, flush=True)


def main():
    p = argparse.ArgumentParser(
        description="Feasibility Pump davanti a un bersaglio di costo U "
                    "(quattro bracci: pilot, naive, test, completion).")
    p.add_argument("mps", help="istanza .mps / .mps.gz")
    p.add_argument("--mode", required=True,
                   choices=["pilot", "naive", "test", "completion",
                            "test-adapt", "completion-adapt"])
    p.add_argument("--adapt-rule", choices=["freeze", "running", "abs"], default="freeze",
                   help="test-adapt/completion-adapt: m = mediana dei PRIMI K "
                        "delta, congelata (freeze, primaria), o di TUTTI i delta "
                        "finora, a ogni giro (running), o di |delta| sui primi K, "
                        "congelata (abs, esplorativa)")
    p.add_argument("--adapt-k", type=int, default=5,
                   help="K: giri di sola misura (w = 0) prima di applicare la "
                        "fascia adattiva")
    p.add_argument("--adapt-eps", type=float, default=1e-3,
                   help="la riga adattiva non scende sotto z_LP + eps (U - z_LP)")
    p.add_argument("--U", type=float, default=None,
                   help="bersaglio, nel senso di MINIMO del modello convertito")
    p.add_argument("--Uprime", type=float, default=None,
                   help="riga interna dell'LP di proiezione (test/completion), "
                        "U' = U - w (U - z_LP); costante per tutta la corsa")
    p.add_argument("--time-limit", type=float, default=300.0,
                   help="budget in secondi, sul tempo della POMPA")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=None, help="file JSON (una riga)")
    p.add_argument("--flip", type=int, default=20,
                   help="T del flip debole di FGL: TT ~ U[T/2, 3T/2]")
    p.add_argument("--frac-min", type=float, default=1e-6,
                   help="soglia di frazionarieta': sono candidate a una "
                        "perturbazione solo le binarie con |x*_j - x^_j| > "
                        "questa soglia. 1e-6 come SCIP, che esclude le sole "
                        "integrali a tolleranza (BFL 2007 usa 0.02, ma per lo "
                        "shifting del codice a interi generali)")
    p.add_argument("--cycle-window", type=int, default=3,
                   help="quanti arrotondamenti passati definiscono un ciclo "
                        "(FGL: gli ultimi 3; SCIP: cyclelength)")
    p.add_argument("--restart-every", type=int, default=100,
                   help="restart FORZATO dopo questo numero di iterazioni "
                        "dall'ultimo restart (FGL: R = 100; SCIP: perturbfreq)")
    p.add_argument("--tlp-max", type=float, default=None,
                   help="se il PRIMO LP costa piu' di questo, esce subito con "
                        "status 'slow' (default: nessun limite)")
    p.add_argument("--no-validate", action="store_true",
                   help="salta la validazione indipendente del punto di "
                        "successo (che rilegge l'MPS: su istanze enormi la "
                        "rilettura costa, anche se e' fuori dal budget)")
    p.add_argument("--max-iter", type=int, default=100_000_000,
                   help="rete di sicurezza: il budget vero e' il tempo")
    p.add_argument("--feas-tol", type=float, default=1e-6,
                   help="tolleranza RELATIVA del test di ammissibilita'")
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--lp-method", type=int, default=1,
                   help="Gurobi Method: 1 = dual simplex (warm start)")
    p.add_argument("--allow-cont", action="store_true", default=True,
                   help="sempre attivo: le continue entrano nei vincoli e nel "
                        "completamento, non nella distanza")
    p.add_argument("--pilot-completion", action="store_true",
                   help="da' al pilota il recupero di FGL sez. 3.2 (default: no)")
    p.add_argument("--naive-completion", action="store_true",
                   help="da' al naive il recupero di FGL sez. 3.2 (default: no)")
    p.add_argument("--pressure", default=None,
                   help="righe di PRESSIONE nell'LP di proiezione, combinabili "
                        "col '+': cut:w | reflect:wmin[:wmax] | track:eta[:wmax] | "
                        "lb:k[:grow] | "
                        "lbmove:k[:grow] | sgn:w | card:k | nogood:m (es. "
                        "'reflect:0.02+lbmove:0.1:grow'). Solo --mode "
                        "test|completion. Default: nessuna, cioe' il "
                        "comportamento di sempre")
    p.add_argument("--incumbent", default=None,
                   help="il punto del pilota, come lo scrive questo programma in "
                        "<out>.inc: una riga per binaria a 1 con l'indice della "
                        "variabile nel modello, piu' un'intestazione con obj=. "
                        "Obbligatorio per le SPEC lb, lbmove e card, usato da "
                        "sgn se c'e'")
    p.add_argument("--stall-relax", type=int, default=50,
                   help="giri CONSECUTIVI senza nessun punto ammissibile dopo i "
                        "quali una SPEC si rilassa: reflect fa risalire U' di "
                        "meta' strada verso il punto di partenza, lb:k:grow e "
                        "lbmove:k:grow raddoppiano il raggio K")
    args = p.parse_args()
    args.pressure_specs = None

    S = new_summary(args, args.mps)
    try:
        if args.mode != "pilot" and args.U is None:
            raise Skip(f"--U e' obbligatorio per --mode {args.mode}")
        if args.pressure:
            # non e' uno Skip: un refuso nella riga di comando e' un errore
            # della CAMPAGNA, non un'istanza fuori perimetro.
            if args.mode not in ("test", "completion"):
                raise BadOption(
                    f"--pressure non vale per --mode {args.mode}, solo per "
                    f"test|completion: in naive la riga c'x <= U e' statica e sta "
                    f"DENTRO il modello (la pompa non la deve vedere muoversi), e "
                    f"il pilota non ha un U da cui misurare il gap")
            args.pressure_specs = parse_pressure(args.pressure)
            if args.Uprime is not None and any(
                    k in OWNS_OBJROW for k, _, _ in args.pressure_specs):
                raise BadOption("--Uprime e --pressure cut/reflect governano la "
                                "STESSA riga c'x <= U': se ne dia una sola")
            if args.stall_relax < 1:
                raise BadOption("--stall-relax deve essere >= 1")
        if (args.mode in ("test", "completion")
                and args.Uprime is None and not args.pressure):
            raise Skip(f"--Uprime e' obbligatorio per --mode {args.mode}")
        if args.mode in ADAPT_MODES:
            if args.Uprime is not None:
                raise BadOption(f"--Uprime non vale per --mode {args.mode}: la "
                                f"riga interna parte a U e scende da sola")
            if args.adapt_k < 1:
                raise BadOption("--adapt-k deve essere >= 1")
            if not (0 < args.adapt_eps < 1):
                raise BadOption("--adapt-eps deve stare in (0,1)")

        t = time.perf_counter()
        P = load(args.mps, args.mode, args.U, wants_completion(args),
                 threads=args.threads, method=args.lp_method,
                 time_limit=args.time_limit)
        S["time_load"] = time.perf_counter() - t
        S.update(maximize=bool(P["maximize"]), n_var=int(P["n"]),
                 n_bin=int(P["n_bin"]), n_cont=int(P["n_cont"]),
                 n_cons=int(P["n_cons"]))

        pump(P, args, np.random.default_rng(args.seed), S)
    except Skip as e:
        S["status"], S["error"] = "error", f"skip: {e}"
    except Exception as e:                                   # noqa: BLE001
        S["status"], S["error"] = "error", f"{type(e).__name__}: {e}"

    emit(S, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
