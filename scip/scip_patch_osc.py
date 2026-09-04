#!/usr/bin/env python3
"""
Il cutoff reattivo: U oscilla, e vive anche prima del primo incumbent.

    python3 scip_patch_osc.py ~/scipwork/scip/src/scip/heur_feaspump.c

Da applicare dopo scip_patch{,_moat,_arms,_stop}.py. Idempotente.

L'IDEA (MF, 01/09/2026). Il modo standard di uscire da un ciclo nel feasibility
pump e' randomizzare il ROUNDING: si flippano variabili di xhat e si spera che
l'LP vada altrove. Ma il ciclo si chiude sull'iterato CONTINUO, e infatti il
braccio bare su glass-sc fa un milione di giri con 1594 sole iterazioni LP: la
perturbazione combinatoria non riesce a spostare x*, che ci ritorna sopra ogni
volta. Muovere U agisce invece sul poliedro, quindi x* DEVE spostarsi -- non e'
una speranza, e' una conseguenza. In piu' costa meno: cambiare un rhs lascia la
base duale ammissibile e il dual simplex riparte quasi gratis, mentre cambiare
l'obiettivo (che e' cio' che fa un flip) rompe l'ammissibilita' duale.

E' la stessa struttura della reactive tabu search di Battiti: un parametro che
si muove su e giu' per tutta la ricerca invece di essere fissato. Qui il
parametro e' lambda, cioe' dove sta U fra il bound e il riferimento superiore.

DUE PARAMETRI NUOVI

  heuristics/feaspump/cutosc     ampiezza dell'oscillazione (0 = spenta: si
                                 ricade esattamente sui bracci a lambda fisso)
  heuristics/feaspump/cutoscper  periodo in giri del dente di sega

  lambda_eff(k) = clamp(cutlam - cutosc * frac(k / cutoscper), 0.02, 1.0)

Dente di sega: lambda scende dal valore base fino a cutlam-cutosc, poi risale
di scatto. La forma conta poco (MF); quel che conta e' che il parametro
attraversi una scala di valori invece di stare fermo.

IL PUNTO CHE APRE LE ISTANZE OGGI SCARTATE. Finora il rhs si aggiornava solo
con un incumbent (SCIPgetUpperbound finito): prima della prima soluzione il
cutoff era spento, cioe' proprio dove servirebbe -- nelle istanze in cui il
pump non trova niente e stalla. Il riferimento superiore diventa allora il
costo del punto arrotondato corrente c'xhat, che c'e' sempre ed e' il livello
di costo di un punto INTERO, cioe' esattamente la quota da cui vogliamo
scendere. Attenzione: in fase 1 spingere solo verso il basso puo' PEGGIORARE
l'ammissibilita' (su un covering, costo basso = poca copertura = piu' righe
violate). E' per questo che l'oscillazione non e' un ornamento: alternare
discesa e rilascio e' cio' che rende l'idea sensata invece che dannosa.

I CONTATORI (per rispondere con una misura, non con un ragionamento, alla
domanda «serve davvero il recupero?»). A ogni giro si controlla se xhat e'
ammissibile per il problema ORIGINALE e, se lo e', se sta sopra il cutoff
corrente -- cioe' se la proiezione del giro successivo potrebbe ritrovarlo da
sola oppure no. Senza cutoff il secondo contatore deve risultare zero: e' la
verifica dell'argomento di MF secondo cui, senza cutoff, un arrotondato
ammissibile non e' mai perso ma solo ritrovato un LP dopo.
"""
import io
import sys

A_STRUCT = """   SCIP_Bool             stopafter;          /**< should the whole solve stop when the pump is done? */"""
N_STRUCT = """   SCIP_Bool             stopafter;          /**< should the whole solve stop when the pump is done? */
   SCIP_Real             cutosc;             /**< amplitude of the sawtooth oscillation of the cutoff level */
   int                   cutoscper;          /**< period, in pumping rounds, of the oscillation */
   int                   nrfeas;             /**< rounded points that were feasible for the original problem */
   int                   nrabove;            /**< ...of those, how many were above the current cutoff */
   int                   nrimprove;          /**< ...of those, how many improved the incumbent */
   SCIP_Bool             cutfallback;        /**< before the first incumbent, hang the cutoff on c'xhat? (a factor of its own, audit §7.6) */"""

# la riga del cutoff serve anche quando oscilliamo senza lambda base
A_DIVE = """   if( heurdata->moat || heurdata->cutlam >= 0.0 )"""
N_DIVE = """   if( heurdata->moat || heurdata->cutlam >= 0.0 || heurdata->cutosc > 0.0 )"""

# il rhs: riferimento c'xhat se manca l'incumbent, e lambda che oscilla
A_RHS = """      if( moatrow != NULL && !SCIPisInfinity(scip, SCIPgetUpperbound(scip)) )
      {
         SCIP_Real zinc = SCIPgetUpperbound(scip);
         SCIP_Real zlow = SCIPgetLowerbound(scip);
         SCIP_Real gap = MAX(zinc - zlow, 0.0);
         SCIP_Real rhs;

         if( heurdata->cutlam >= 0.0 )
         {"""
N_RHS = """      if( moatrow != NULL )
      {
         SCIP_Real zinc = SCIPgetUpperbound(scip);
         SCIP_Real zlow = SCIPgetLowerbound(scip);
         SCIP_Real gap;
         SCIP_Real rhs;

         /* No incumbent yet? Then the cutoff would simply not exist, which is
          * precisely the case we care about: the instances where the pump
          * stalls without ever finding anything. Use the cost of the current
          * rounded point as the upper reference -- it always exists, and it is
          * the cost of an INTEGER point, i.e. the level we want to get below.
          */
         if( heurdata->cutfallback && SCIPisInfinity(scip, zinc) && nloops > 1 )
         {
            SCIP_Real cr = 0.0;
            for( i = 0; i < nvars; i++ )
            {
               SCIP_Real o = SCIPvarGetObj(vars[i]);
               if( !SCIPisZero(scip, o) )
                  cr += o * SCIPgetSolVal(scip, heurdata->roundedsol, vars[i]);
            }
            if( cr > zlow )
               zinc = cr;
         }

         gap = MAX(zinc - zlow, 0.0);

         if( SCIPisInfinity(scip, zinc) )
         {
            /* still nothing to hang the cutoff on: leave the row free */
            SCIP_CALL( SCIPchgRowRhsDive(scip, moatrow, SCIPinfinity(scip)) );
         }
         else if( heurdata->cutlam >= 0.0 || heurdata->cutosc > 0.0 )
         {"""

A_RHS2 = """            /* the "clever user" cutoff: a fixed fraction of the current
             * integrality gap below the incumbent. It moves down by itself
             * every time the incumbent improves, because zinc does.
             */
            rhs = zlow + heurdata->cutlam * gap;
         }
         else
         {
            SCIP_Real w = MAX(moatwidth, heurdata->moatwmin * gap);
            rhs = MAX(zlow + 0.02 * gap, zinc - w);
         }

         SCIP_CALL( SCIPchgRowRhsDive(scip, moatrow, rhs) );
      }"""
N_RHS2 = """            /* the "clever user" cutoff: a fixed fraction of the current
             * integrality gap below the reference. It moves down by itself
             * every time the incumbent improves, because zinc does.
             *
             * With cutosc > 0 the level is not fixed but sweeps a range, like
             * the tenure in a reactive tabu search: lambda slides down from
             * cutlam to cutlam-cutosc over cutoscper rounds and then jumps
             * back up. Moving the cutoff moves the polyhedron, so x* has to
             * move -- which is what a random flip of the rounding only hopes
             * to achieve.
             */
            SCIP_Real lam = (heurdata->cutlam >= 0.0 ? heurdata->cutlam : 1.0);

            if( heurdata->cutosc > 0.0 )
            {
               int per = MAX(heurdata->cutoscper, 1);
               lam -= heurdata->cutosc * ((SCIP_Real)(nloops % per) / (SCIP_Real)per);
            }
            lam = MAX(0.02, MIN(1.0, lam));
            rhs = zlow + lam * gap;
            SCIP_CALL( SCIPchgRowRhsDive(scip, moatrow, rhs) );
         }
         else
         {
            SCIP_Real w = MAX(moatwidth, heurdata->moatwmin * gap);
            rhs = MAX(zlow + 0.02 * gap, zinc - w);
            SCIP_CALL( SCIPchgRowRhsDive(scip, moatrow, rhs) );
         }
      }"""

# i contatori: e' l'arrotondato ammissibile? e sta sopra il cutoff?
A_CNT = """      /* initialize cycle check */
      minimum = MIN(heurdata->cyclelength, nloops-1);"""
N_CNT = """      /* Is the rounded point feasible for the ORIGINAL problem, and would the
       * cutoff hide it? Counting this is the way to answer with a measurement,
       * rather than with an argument, the question of whether the explicit
       * recovery is needed: without a cutoff a feasible rounded point is never
       * lost -- the next projection returns it at distance zero -- so nrabove
       * must come out zero there.
       */
      {
         SCIP_SOL* chksol;
         SCIP_Bool chkfeas;

         /* Costruita da zero e non copiata: vedi la nota in scip_patch.py.
          * SCIPrecomputeSolObj e' una routine per soluzioni ORIGINALI e qui
          * dava un `cr` sbagliato dove il presolve ha un offset --- il che
          * falsava nrabove e nrimprove, non nrfeas (che guarda il vettore).
          */
         SCIP_CALL( SCIPcreateSol(scip, &chksol, heur) );
         {
            SCIP_VAR** chkvars;
            int nchkvars;
            int iv;

            SCIP_CALL( SCIPgetVarsData(scip, &chkvars, &nchkvars, NULL, NULL, NULL, NULL) );
            for( iv = 0; iv < nchkvars; ++iv )
            {
               SCIP_CALL( SCIPsetSolVal(scip, chksol, chkvars[iv],
                     SCIPgetSolVal(scip, heurdata->roundedsol, chkvars[iv])) );
            }
         }
         SCIP_CALL( SCIPcheckSol(scip, chksol, FALSE, FALSE, TRUE, TRUE, TRUE, &chkfeas) );
         if( chkfeas )
         {
            SCIP_Real cr = SCIPgetSolTransObj(scip, chksol);

            heurdata->nrfeas++;
            if( moatrow != NULL && !SCIPisInfinity(scip, SCIProwGetRhs(moatrow))
                && SCIPisGT(scip, cr, SCIProwGetRhs(moatrow)) )
               heurdata->nrabove++;
            if( SCIPisLT(scip, cr, SCIPgetUpperbound(scip)) )
               heurdata->nrimprove++;
         }
         SCIP_CALL( SCIPfreeSol(scip, &chksol) );
      }

      /* initialize cycle check */
      minimum = MIN(heurdata->cyclelength, nloops-1);"""

A_DIAG = """      "fp_exit: nloops=%d nfracs=%d nstall=%d/%d nlpiter=%" SCIP_LONGINT_FORMAT "/%" SCIP_LONGINT_FORMAT
      " lperror=%u lpsolstat=%d stopped=%u ifound=%d\\n","""
N_DIAG = """      "fp_exit: nloops=%d nfracs=%d nstall=%d/%d nlpiter=%" SCIP_LONGINT_FORMAT "/%" SCIP_LONGINT_FORMAT
      " lperror=%u lpsolstat=%d stopped=%u ifound=%d"
      " rfeas=%d rabove=%d rimprove=%d\\n","""

A_DIAG2 = """      lperror, lpsolstat, SCIPisStopped(scip), heurdata->nintegralfound);"""
N_DIAG2 = """      lperror, lpsolstat, SCIPisStopped(scip), heurdata->nintegralfound,
      heurdata->nrfeas, heurdata->nrabove, heurdata->nrimprove);"""

A_PARAM = """   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/cutlam","""
N_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/cutfallback",
         "before the first incumbent, hang the cutoff on the cost of the current rounded point?",
         &heurdata->cutfallback, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/cutosc",
         "amplitude of the sawtooth oscillation of the cutoff level (0: fixed)",
         &heurdata->cutosc, FALSE, 0.0, 0.0, 1.0, NULL, NULL) );

   SCIP_CALL( SCIPaddIntParam(scip, "heuristics/" HEUR_NAME "/cutoscper",
         "period, in pumping rounds, of the cutoff oscillation",
         &heurdata->cutoscper, FALSE, 50, 1, INT_MAX, NULL, NULL) );

   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/cutlam","""

# azzeramento dei contatori a ogni chiamata
A_INIT = """   nloops = 0;
   nstallloops = 0;"""
N_INIT = """   nloops = 0;
   nstallloops = 0;
   heurdata->nrfeas = 0;
   heurdata->nrabove = 0;
   heurdata->nrimprove = 0;"""

STEPS = [(A_STRUCT, N_STRUCT, "struct heurdata"),
         (A_DIVE, N_DIVE, "riga creata anche con la sola oscillazione"),
         (A_RHS, N_RHS, "riferimento c'xhat senza incumbent"),
         (A_RHS2, N_RHS2, "lambda oscillante"),
         (A_CNT, N_CNT, "contatori sull'arrotondato"),
         (A_INIT, N_INIT, "azzeramento dei contatori"),
         (A_DIAG, N_DIAG, "diagnostica: formato"),
         (A_DIAG2, N_DIAG2, "diagnostica: argomenti"),
         (A_PARAM, N_PARAM, "parametri")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "cutosc" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "stopafter" not in s:
        print("ERRORE: applica prima scip_patch_stop.py")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"cutoff reattivo applicato a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
