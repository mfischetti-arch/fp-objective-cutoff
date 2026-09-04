#!/usr/bin/env python3
"""
Uscire dai cicli con un cutoff su una funzione obiettivo RANDOM (smoke test).

    python3 scip_patch_rcut.py ~/scipwork/scip/src/scip/heur_feaspump.c

Da applicare dopo scip_patch{,_moat,_arms,_stop,_osc,_vcut}.py. Idempotente.

L'IDEA (MF, 01/09/2026 notte). Il pump esce da un ciclo perturbando il
ROUNDING: flippa qualche variabile di xhat e spera che la proiezione vada
altrove. Puo' fallire, e fallisce: bare su glass-sc fa un milione di giri con
1594 iterazioni LP, cioe' l'LP restituisce lo stesso x~ qualunque cosa si
faccia a xhat. Muovere il POLIEDRO e' diverso: x~ DEVE spostarsi.

IL DISEGNO DI MF, preciso:
  - a ogni stallo si prende una direzione random r a coefficienti in {-1,0,+1}
    sulle variabili intere;
  - la si valuta in x* (l'ottimo dell'LP con la f.o. ORIGINALE, salvato prima
    del dive) e nel punto corrente x~ su cui il pump cicla: a = r'x*, b = r'x~;
  - il rhs si fissa FRA i due valori, vicino a b: se b > a la riga e'
    r'x <= b - theta (b - a), se b < a e' r'x >= b + theta (a - b). Cosi' x~
    viola il taglio -- il giro dopo NON puo' restituirlo -- mentre x* lo
    soddisfa, quindi il poliedro tagliato non e' mai vuoto: nessun LP
    infeasible per costruzione (a meno di tolleranze);
  - se la direzione non separa (|b - a| sotto tolleranza) se ne prova un'altra;
    se nessuna separa si ricade nel flip standard.

IMPLEMENTAZIONE. In un LP di diving non si possono cambiare i coefficienti di
una riga, solo lhs/rhs: quindi le direzioni random sono K righe create UNA
volta all'inizio del dive (libere: lhs = -inf, rhs = +inf) e usate a
rotazione, una per stallo. «Cambiare funzione random se non si sblocca» e'
allora automatico: ogni stallo prende la direzione successiva. Il taglio vive
un solo LP (e' un calcio): subito dopo il solve la riga torna libera.

Parametri:
  heuristics/feaspump/rcut       TRUE per accendere il meccanismo
  heuristics/feaspump/rcutk      numero di direzioni random (default 16)
  heuristics/feaspump/rcuttheta  dove sta il rhs fra b e a (0 = su x~, 1 = su
                                 x*; default 0.1, cioe' vicino a x~)
  heuristics/feaspump/rcutflip   TRUE per fare ANCHE il flip standard

Contatori in fp_exit: rcut = calci dati, rcutnosep = direzioni scartate perche'
non separavano, rcutinf = LP infeasible dopo un calcio (dovrebbe restare 0).
"""
import io
import sys

A_STRUCT = """   SCIP_Bool             vvalid;             /**< are those three levels usable? */"""
N_STRUCT = """   SCIP_Bool             vvalid;             /**< are those three levels usable? */
   SCIP_Bool             rcut;               /**< escape cycles by cutting on a random objective? */
   int                   rcutk;              /**< number of random directions kept as free diving rows */
   SCIP_Real             rcuttheta;          /**< where the rhs sits between r'x~ (0) and r'x* (1) */
   SCIP_Bool             rcutflip;           /**< also perform the standard flip when the random cut fires? */
   int                   nrcut;              /**< how many times the random cut fired */
   int                   nrcutnosep;         /**< directions skipped because they did not separate x~ from x* */
   int                   nrcutinf;           /**< diving LPs that came out infeasible after a kick */"""

A_LOCAL = """   SCIP_ROW* moatrow;         /* the progressive rounding-moat row, if enabled */"""
N_LOCAL = """   SCIP_ROW* moatrow;         /* the progressive rounding-moat row, if enabled */
   SCIP_ROW** rrows;          /* the random-direction rows used to kick x~ out of a cycle */
   SCIP_Real* rrowsa;         /* r'x* for each of them, x* = the LP optimum for the original objective */
   SCIP_SOL* xstar;           /* that LP optimum, saved before diving */
   int rrowsn;                /* how many rows were actually created */
   int rrownext;              /* next direction to try */
   int rrowactive;            /* index of the row whose side is finite right now, or -1 */"""

A_NULL = """   moatrow = NULL;
   moatwidth = 0.0;"""
N_NULL = """   moatrow = NULL;
   moatwidth = 0.0;
   rrows = NULL;
   rrowsa = NULL;
   xstar = NULL;
   rrowsn = 0;
   rrownext = 0;
   rrowactive = -1;"""

A_CREATE = """   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );
"""
N_CREATE = """   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );

   if( heurdata->rcut )
   {
      int k;

      /* the LP optimum for the ORIGINAL objective, read off the diving LP
       * before anything is changed: the random cuts are placed so that this
       * point always stays feasible, which keeps the diving LP from ever
       * becoming empty */
      SCIP_CALL( SCIPcreateLPSol(scip, &xstar, heur) );
      SCIP_CALL( SCIPunlinkSol(scip, xstar) );

      SCIP_CALL( SCIPallocBlockMemoryArray(scip, &rrows, heurdata->rcutk) );
      SCIP_CALL( SCIPallocBlockMemoryArray(scip, &rrowsa, heurdata->rcutk) );
      for( k = 0; k < heurdata->rcutk; k++ )
      {
         rrowsa[k] = 0.0;
         /* NOT a free row: SoPlex 9 throws XENTER05 ("This should never
          * happen") on a free row with +/-1 coefficients added in diving,
          * measured on glass-sc. Wide finite sides make the row redundant
          * and keep the LP solver happy; 1e7 is far above any activity a
          * +/-1 row can reach on these instances. */
         SCIP_CALL( SCIPcreateEmptyRowUnspec(scip, &rrows[k], "fp_rcut",
               -1e7, 1e7, FALSE, FALSE, TRUE) );
         SCIP_CALL( SCIPcacheRowExtensions(scip, rrows[k]) );
         for( i = 0; i < nvars; i++ )
         {
            /* only columns that are in the LP: a diving row over a variable
             * without an LP column is the one thing the moat row can never
             * do (an inactive variable has objective zero) and the prime
             * suspect for the XENTER05 exception of SoPlex */
            if( SCIPvarIsIntegral(vars[i]) && SCIPvarIsInLP(vars[i]) )
            {
               /* {0,1} rather than {-1,0,1}: with mixed signs SoPlex 9 throws
                * XENTER05 on the first dive LP after the row is added (also with
                * finite sides), while the objective row of the moat, all
                * non-negative, never does. A 0/1 direction separates x~ from x*
                * just as well: it counts how many variables of a random subset
                * are at one. */
               int coef = SCIPrandomGetInt(heurdata->randnumgen, 0, 1);
               if( coef != 0 )
               {
                  SCIP_CALL( SCIPaddVarToRow(scip, rrows[k], vars[i], (SCIP_Real)coef) );
                  rrowsa[k] += (SCIP_Real)coef * SCIPgetSolVal(scip, xstar, vars[i]);
               }
            }
         }
         SCIP_CALL( SCIPflushRowExtensions(scip, rrows[k]) );
         SCIP_CALL( SCIPaddRowDive(scip, rrows[k]) );
         rrowsn++;
      }
      SCIP_CALL( SCIPsolveDiveLP(scip, -1, &lperror, NULL) );
      if( lperror || SCIPgetLPSolstat(scip) != SCIP_LPSOLSTAT_OPTIMAL )
      {
         for( k = 0; k < rrowsn; k++ )
         {
            SCIP_CALL( SCIPreleaseRow(scip, &rrows[k]) );
         }
         rrowsn = 0;
      }
   }
"""

A_CYCLE = """               /* 1-cycles have a special flipping rule (flip most fractional variables) */
               if( j == 0 )"""
N_CYCLE = """               /* The random kick: instead of (or on top of) flipping the
                * rounding, forbid the LP iterate itself with a cut that x*
                * satisfies. The next projection cannot return x~, whatever
                * the rounding does. Directions that do not separate x~ from
                * x* are skipped; if none does, fall through to the flip.
                */
               if( rrowsn > 0 )
               {
                  int tries;
                  SCIP_Bool kicked = FALSE;

                  for( tries = 0; tries < rrowsn && !kicked; tries++ )
                  {
                     int k = rrownext;
                     SCIP_Real a = rrowsa[k];
                     SCIP_Real b = SCIPgetRowActivity(scip, rrows[k]);

                     rrownext = (rrownext + 1) % rrowsn;
                     if( SCIPisGT(scip, b, a) )
                     {
                        /* the K rows are a sliding window of walls: reusing a
                         * row drops its old wall and raises the new one */
                        SCIP_CALL( SCIPchgRowLhsDive(scip, rrows[k], -1e7) );
                        SCIP_CALL( SCIPchgRowRhsDive(scip, rrows[k], b - heurdata->rcuttheta * (b - a)) );
                        kicked = TRUE;
                     }
                     else if( SCIPisLT(scip, b, a) )
                     {
                        SCIP_CALL( SCIPchgRowRhsDive(scip, rrows[k], 1e7) );
                        SCIP_CALL( SCIPchgRowLhsDive(scip, rrows[k], b + heurdata->rcuttheta * (a - b)) );
                        kicked = TRUE;
                     }
                     else
                        heurdata->nrcutnosep++;
                     if( kicked )
                     {
                        rrowactive = k;
                        heurdata->nrcut++;
                        SCIPdebugMsg(scip, " -> %d-cycle: random kick on direction %d (a=%g, b=%g)\\n", j+1, k, a, b);
                     }
                  }
                  if( kicked && !heurdata->rcutflip )
                     break;
               }

               /* 1-cycles have a special flipping rule (flip most fractional variables) */
               if( j == 0 )"""

A_SOLVE = """      retcode = SCIPsolveDiveLP(scip, iterlimit, &lperror, NULL);
      lpsolstat = SCIPgetLPSolstat(scip);
"""
N_SOLVE = """      retcode = SCIPsolveDiveLP(scip, iterlimit, &lperror, NULL);
      lpsolstat = SCIPgetLPSolstat(scip);

      /* The random MOAT stays (MF): the cut is not a kick for one LP but a
       * wall that keeps x~ away from where it was cycling -- the recovery
       * makes sure no solution is lost by it. It should never make the LP
       * infeasible, since x* satisfies it; if it does anyway (tolerances),
       * free that row, count it, and resolve.
       */
      if( rrowactive >= 0 )
      {
         if( retcode == SCIP_OKAY && !lperror && lpsolstat == SCIP_LPSOLSTAT_INFEASIBLE )
         {
            SCIP_CALL( SCIPchgRowLhsDive(scip, rrows[rrowactive], -1e7) );
            SCIP_CALL( SCIPchgRowRhsDive(scip, rrows[rrowactive], 1e7) );
            heurdata->nrcutinf++;
            retcode = SCIPsolveDiveLP(scip, iterlimit, &lperror, NULL);
            lpsolstat = SCIPgetLPSolstat(scip);
         }
         rrowactive = -1;
      }
"""

A_FREE = """   if( moatrow != NULL )
   {
      SCIP_CALL( SCIPreleaseRow(scip, &moatrow) );"""
N_FREE = """   if( rrows != NULL )
   {
      int k;
      for( k = 0; k < rrowsn; k++ )
      {
         SCIP_CALL( SCIPreleaseRow(scip, &rrows[k]) );
      }
      SCIPfreeBlockMemoryArray(scip, &rrowsa, heurdata->rcutk);
      SCIPfreeBlockMemoryArray(scip, &rrows, heurdata->rcutk);
   }
   if( xstar != NULL )
   {
      SCIP_CALL( SCIPfreeSol(scip, &xstar) );
   }
   if( moatrow != NULL )
   {
      SCIP_CALL( SCIPreleaseRow(scip, &moatrow) );"""

A_INIT = """   heurdata->vvalid = FALSE;"""
N_INIT = """   heurdata->vvalid = FALSE;
   heurdata->nrcut = 0;
   heurdata->nrcutnosep = 0;
   heurdata->nrcutinf = 0;"""

A_DIAG = """      " rvfeas=%d rv25=%d rv50=%d rv75=%d\\n","""
N_DIAG = """      " rvfeas=%d rv25=%d rv50=%d rv75=%d"
      " rcut=%d rcutnosep=%d rcutinf=%d\\n","""

A_DIAG2 = """      heurdata->nrvfeas, heurdata->nrv25, heurdata->nrv50, heurdata->nrv75);"""
N_DIAG2 = """      heurdata->nrvfeas, heurdata->nrv25, heurdata->nrv50, heurdata->nrv75,
      heurdata->nrcut, heurdata->nrcutnosep, heurdata->nrcutinf);"""

A_PARAM = """   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/vzinc","""
N_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/rcut",
         "escape cycles by tightening a cutoff on a random objective instead of flipping the rounding?",
         &heurdata->rcut, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddIntParam(scip, "heuristics/" HEUR_NAME "/rcutk",
         "number of random directions kept as free diving rows",
         &heurdata->rcutk, FALSE, 16, 1, 1000, NULL, NULL) );

   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/rcuttheta",
         "where the cut sits between r'x~ (0) and r'x* (1)",
         &heurdata->rcuttheta, FALSE, 0.1, 0.0, 1.0, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/rcutflip",
         "also perform the standard rounding flip when the random cut fires?",
         &heurdata->rcutflip, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/vzinc","""

STEPS = [(A_STRUCT, N_STRUCT, "struct heurdata"),
         (A_LOCAL, N_LOCAL, "variabili locali"),
         (A_NULL, N_NULL, "inizializzazione locale"),
         (A_CREATE, N_CREATE, "x* salvato e le K direzioni random"),
         (A_CYCLE, N_CYCLE, "il calcio al posto del flip"),
         (A_SOLVE, N_SOLVE, "rilascio dopo il solve"),
         (A_FREE, N_FREE, "rilascio finale"),
         (A_INIT, N_INIT, "azzeramento contatori"),
         (A_DIAG, N_DIAG, "diagnostica: formato"),
         (A_DIAG2, N_DIAG2, "diagnostica: argomenti"),
         (A_PARAM, N_PARAM, "parametri")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "nrcut" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "nrvfeas" not in s:
        print("ERRORE: applica prima scip_patch_vcut.py")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"random cut applicato a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
