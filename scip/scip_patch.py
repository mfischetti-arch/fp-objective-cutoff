#!/usr/bin/env python3
"""
Aggiunge a heur_feaspump.c di SCIP il test del punto arrotondato.

    python3 scip_patch.py ~/scipwork/scip/src/scip/heur_feaspump.c

Perche'. In quel file c'e' UNA sola SCIPtrySol, su heurdata->sol collegata
all'LP e solo quando nfracs == 0, cioe' quando l'iterato LP e' gia' intero. La
roundedsol viene costruita, letta per la distanza e confrontata per i cicli,
ma la sua ammissibilita' non e' mai verificata: le soluzioni che il rounding
produce per caso lungo la strada non le raccoglie nessuno.

Il test si mette **subito dopo il completamento dell'arrotondamento e prima dei
flip anti-ciclo**, che altrimenti allontanerebbero il punto.

Dietro un parametro con default FALSE, cosi' baseline e variante sono lo STESSO
binario con lo stesso ordine di operazioni e cambia solo il flag:

    heuristics/feaspump/tryrounded = TRUE

Lo script e' idempotente: rieseguirlo non applica due volte.
"""
import io
import sys

ANCHOR_STRUCT = """   SCIP_Bool             copycuts;           /**< should all active cuts from cutpool be copied to constraints in
                                              *   subproblem?
                                              */
};"""

ADD_STRUCT = """   SCIP_Bool             copycuts;           /**< should all active cuts from cutpool be copied to constraints in
                                              *   subproblem?
                                              */
   SCIP_Bool             tryrounded;         /**< should the rounded point be tried as a solution every round? */
   int                   nroundedfound;      /**< number of solutions accepted from the rounded point */
};"""

ANCHOR_LOOP = """      SCIPfreeBufferArray(scip, &pseudocands);

      /* initialize cycle check */"""

ADD_LOOP = """      SCIPfreeBufferArray(scip, &pseudocands);

      /* try the rounded point as a solution.
       *
       * The pump builds roundedsol at every round but never checks whether it
       * happens to be feasible: it only stops when the LP iterate itself is
       * integral, so any feasible point produced by the rounding along the way
       * is simply not collected. Testing it here, before the anti-cycling flips
       * move it away, costs one feasibility check per round.
       */
      if( heurdata->tryrounded )
      {
         SCIP_SOL* trysol;
         SCIP_Bool stored;

         /* roundedsol is LINKED to the diving LP, whose objective is the
          * DISTANCE, not the cost: a copy of it inherits that value and SCIP
          * would store a bogus primal bound.
          *
          * ❌ SCIPrecomputeSolObj is NOT the way to fix that, and using it here
          * was a real bug (found by an external audit, 02/09/2026): it asserts
          * SCIPsolIsOriginal(sol) and walks the ORIGINAL problem's variables,
          * adding the ORIGINAL objective offset (sol.c, SCIPsolRecomputeObj).
          * Our solution lives in the transformed space, the assert is compiled
          * out in a Release build, and the stored objective came out wrong
          * wherever presolve introduced an offset or fixed variables --- on 15
          * of 149 instances SCIP ended up reporting a primal bound BELOW the LP
          * bound, with err=0 and a genuinely feasible vector.
          *
          * The right way is the one SCIP's own rounding heuristics use: build
          * the solution from scratch and set every value, because SCIPsolSetVal
          * maintains sol->obj incrementally with SCIPvarGetUnchangedObj --- the
          * objective coefficient the dive has NOT touched. No recompute needed.
          */
         SCIP_CALL( SCIPcreateSol(scip, &trysol, heur) );
         {
            SCIP_VAR** allvars;
            int nallvars;
            int iv;

            SCIP_CALL( SCIPgetVarsData(scip, &allvars, &nallvars, NULL, NULL, NULL, NULL) );
            for( iv = 0; iv < nallvars; ++iv )
            {
               SCIP_CALL( SCIPsetSolVal(scip, trysol, allvars[iv],
                     SCIPgetSolVal(scip, heurdata->roundedsol, allvars[iv])) );
            }
         }
         /* checklprows MUST be TRUE here. The existing SCIPtrySol in this file
          * passes FALSE because its solution comes straight from the LP and
          * therefore satisfies the rows by construction; the rounded point does
          * not, and with FALSE SCIP accepts it unchecked -- on nug08 that means
          * storing the all-zero point and reporting a primal bound of 0 for a
          * problem whose optimum is 214.
          */
         SCIP_CALL( SCIPtrySolFree(scip, &trysol, FALSE, FALSE, TRUE, TRUE, TRUE, &stored) );
         if( stored )
         {
            heurdata->nroundedfound++;
            SCIPdebugMsg(scip, "feasibility pump: rounded point accepted as solution\\n");
            *result = SCIP_FOUNDSOL;
         }
      }

      /* initialize cycle check */"""

ANCHOR_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/copycuts",
         "should all active cuts from cutpool be copied to constraints in subproblem?",
         &heurdata->copycuts, TRUE, DEFAULT_COPYCUTS, NULL, NULL) );

   return SCIP_OKAY;"""

ADD_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/copycuts",
         "should all active cuts from cutpool be copied to constraints in subproblem?",
         &heurdata->copycuts, TRUE, DEFAULT_COPYCUTS, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/tryrounded",
         "should the rounded point be tried as a solution at every pumping round?",
         &heurdata->tryrounded, FALSE, FALSE, NULL, NULL) );

   return SCIP_OKAY;"""


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()

    if "tryrounded" in s:
        print("gia' applicata, non faccio nulla")
        return 0

    for anchor, add, what in ((ANCHOR_STRUCT, ADD_STRUCT, "struct heurdata"),
                              (ANCHOR_LOOP, ADD_LOOP, "test nel loop"),
                              (ANCHOR_PARAM, ADD_PARAM, "parametro")):
        if s.count(anchor) != 1:
            print(f"ERRORE: l'ancora '{what}' compare {s.count(anchor)} volte, "
                  f"mi aspettavo 1. Il sorgente e' cambiato: non tocco niente.")
            return 1
        s = s.replace(anchor, add, 1)
        print(f"  applicato: {what}")

    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"patch applicata a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
