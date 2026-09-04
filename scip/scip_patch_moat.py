#!/usr/bin/env python3
"""
Porta la rounding-moat progressiva dentro il feasibility pump di SCIP.

    python3 scip_patch_moat.py ~/scipwork/scip/src/scip/heur_feaspump.c

Da applicare DOPO scip_patch.py (che aggiunge tryrounded).

Il FP di SCIP non ha un cutoff come vincolo: il costo entra solo tramite alpha,
la combinazione convessa. La moat invece e' un vincolo c'x <= UB' che si muove.
Si ottiene aggiungendo la riga all'LP del dive (SCIPaddRowDive) e spostandone il
RHS a ogni giro (SCIPchgRowRhsDive).

La politica, che e' il punto: nessun cutoff finche' non c'e' un incumbent; poi
una fascia sotto di lui, larga quanto il peggioramento tipico del rounding
(media mobile del gap fra costo dell'arrotondato e costo dell'iterato LP), cosi'
che l'arrotondamento cada sotto l'incumbent e lo migliori invece di mancarlo.
La fascia scende insieme all'incumbent. Nessun parametro da tarare a priori --
che e' la ragione per cui questa politica ha senso e non il cutoff fisso.

    heuristics/feaspump/moat = TRUE

Lo script e' idempotente.
"""
import io
import sys

A_STRUCT = """   SCIP_Bool             tryrounded;         /**< should the rounded point be tried as a solution every round? */"""
N_STRUCT = """   SCIP_Bool             tryrounded;         /**< should the rounded point be tried as a solution every round? */
   SCIP_Bool             moat;               /**< should a progressive rounding-moat be imposed below the incumbent? */
   SCIP_Real             moatwmin;           /**< minimum moat width, as a fraction of the integrality gap */"""

# la riga del moat si crea appena entrati in diving, prima del ciclo
A_START = """   SCIP_CALL( SCIPallocBufferArray(scip, &lastroundedsols, heurdata->cyclelength) );"""
N_START = """   SCIP_CALL( SCIPallocBufferArray(scip, &lastroundedsols, heurdata->cyclelength) );

   /* progressive rounding-moat: the row is created empty (rhs = +inf, so it
    * constrains nothing) and its rhs is moved at every round. SCIP's pump has
    * no cutoff row of its own -- the cost only enters through alpha -- so one
    * has to be added to the diving LP explicitly.
    */
   moatrow = NULL;
   moatwidth = 0.0;"""

A_DECL = """   SCIP_SOL* closestsol;      /* rounded solution closest to the LP relaxation: used for stage3 */"""
N_DECL = """   SCIP_SOL* closestsol;      /* rounded solution closest to the LP relaxation: used for stage3 */
   SCIP_ROW* moatrow;         /* the progressive rounding-moat row, if enabled */
   SCIP_Real moatwidth;       /* running estimate of the rounding gap */"""

# creazione della riga: subito dopo l'inizio del diving
A_DIVE = """   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );"""
N_DIVE = """   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );

   if( heurdata->moat )
   {
      SCIP_CALL( SCIPcreateEmptyRowUnspec(scip, &moatrow, "fp_moat",
            -SCIPinfinity(scip), SCIPinfinity(scip), FALSE, FALSE, TRUE) );
      SCIP_CALL( SCIPcacheRowExtensions(scip, moatrow) );
      for( i = 0; i < nvars; i++ )
      {
         if( !SCIPisZero(scip, SCIPvarGetObj(vars[i])) )
         {
            SCIP_CALL( SCIPaddVarToRow(scip, moatrow, vars[i], SCIPvarGetObj(vars[i])) );
         }
      }
      SCIP_CALL( SCIPflushRowExtensions(scip, moatrow) );
      SCIP_CALL( SCIPaddRowDive(scip, moatrow) );

      /* adding a row invalidates the current diving LP solution: without
       * resolving, the SCIPlinkLPSol at the top of the pumping loop fails with
       * "LP solution does not exist". The rhs is still +infinity here, so this
       * solve cannot cut anything off.
       */
      SCIP_CALL( SCIPsolveDiveLP(scip, -1, &lperror, NULL) );
      if( lperror || SCIPgetLPSolstat(scip) != SCIP_LPSOLSTAT_OPTIMAL )
      {
         SCIP_CALL( SCIPreleaseRow(scip, &moatrow) );
         moatrow = NULL;
      }
   }"""

# aggiornamento del rhs: prima di risolvere l'LP del giro
A_SOLVE = """      /* the LP with the new (distance) objective is solved */
      nlpiterations = SCIPgetNLPIterations(scip);"""
N_SOLVE = """      /* move the rounding-moat under the current incumbent.
       *
       * width = typical amount by which rounding worsens the cost, estimated on
       * the fly; the rhs is set to incumbent - width so that the rounded point
       * lands below the incumbent instead of just above it. Never below the
       * dual bound plus a margin, or the LP would go infeasible.
       */
      if( moatrow != NULL && !SCIPisInfinity(scip, SCIPgetUpperbound(scip)) )
      {
         SCIP_Real zinc = SCIPgetUpperbound(scip);
         SCIP_Real zlow = SCIPgetLowerbound(scip);
         SCIP_Real gap = MAX(zinc - zlow, 0.0);
         SCIP_Real w = MAX(moatwidth, heurdata->moatwmin * gap);
         SCIP_Real rhs = MAX(zlow + 0.02 * gap, zinc - w);

         SCIP_CALL( SCIPchgRowRhsDive(scip, moatrow, rhs) );
      }

      /* the LP with the new (distance) objective is solved */
      nlpiterations = SCIPgetNLPIterations(scip);"""

# stima del gap di rounding: dove roundedsol e' completa
A_EST = """      SCIPfreeBufferArray(scip, &pseudocands);"""
N_EST = """      SCIPfreeBufferArray(scip, &pseudocands);

      /* running estimate of the rounding gap: cost of the rounded point minus
       * cost of the LP iterate, both under the ORIGINAL objective (SCIPvarGetObj
       * is the transformed problem's objective, which diving does not touch)
       */
      if( moatrow != NULL )
      {
         SCIP_Real croundd = 0.0;
         SCIP_Real clp = 0.0;

         for( i = 0; i < nvars; i++ )
         {
            SCIP_Real o = SCIPvarGetObj(vars[i]);
            if( !SCIPisZero(scip, o) )
            {
               croundd += o * SCIPgetSolVal(scip, heurdata->roundedsol, vars[i]);
               clp += o * SCIPvarGetLPSol(vars[i]);
            }
         }
         if( croundd > clp )
            moatwidth = 0.7 * moatwidth + 0.3 * (croundd - clp);
      }"""

A_END = """   /* end diving */
   if( SCIPinDive(scip) )
   {
      SCIP_CALL( SCIPendDive(scip) );
   }"""
N_END = """   if( moatrow != NULL )
   {
      SCIP_CALL( SCIPreleaseRow(scip, &moatrow) );
   }

   /* end diving */
   if( SCIPinDive(scip) )
   {
      SCIP_CALL( SCIPendDive(scip) );
   }"""

A_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/tryrounded","""
N_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/moat",
         "should a progressive rounding-moat be imposed below the incumbent?",
         &heurdata->moat, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/moatwmin",
         "minimum moat width, as a fraction of the integrality gap",
         &heurdata->moatwmin, TRUE, 0.05, 0.0, 1.0, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/tryrounded","""

# La stima dinamica del gap di rounding (A_EST/N_EST) e' rimossa dalla lista:
# leggeva l'iterato LP con SCIPvarGetLPSol e dentro il pump la soluzione LP non
# e' sempre disponibile -- "LP solution does not exist", errore -8 a metà run.
# Qui la fascia si dimensiona sul gap di integralita' corrente, che invece c'e'
# sempre. Si perde l'adattamento al delta misurato (che il prototipo fuori dal
# solver fa), ma resta l'essenziale: una fascia sotto l'incumbent che scende
# insieme a lui, senza alcun lambda da fissare a priori.
STEPS = [(A_DECL, N_DECL, "dichiarazioni"),
         (A_STRUCT, N_STRUCT, "struct heurdata"),
         (A_START, N_START, "inizializzazione"),
         (A_DIVE, N_DIVE, "creazione della riga nel dive"),
         (A_SOLVE, N_SOLVE, "spostamento del rhs"),
         (A_END, N_END, "rilascio della riga"),
         (A_PARAM, N_PARAM, "parametri")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "fp_moat" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "tryrounded" not in s:
        print("ERRORE: applica prima scip_patch.py")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"moat applicata a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
