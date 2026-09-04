#!/usr/bin/env python3
"""
I bracci dell'esperimento v2 dentro il feasibility pump di SCIP.

    python3 scip_patch_arms.py ~/scipwork/scip/src/scip/heur_feaspump.c

Da applicare DOPO scip_patch.py (tryrounded) e scip_patch_moat.py (fp_moat).

Aggiunge due parametri.

1) heuristics/feaspump/cutlam  (default -1 = spento)

   Il cutoff dell'"utente scaltro": U = z_low + lam*(z_inc - z_low), imposto
   come rhs della riga fp_moat gia' creata dalla patch moat, e RICALCOLATO a
   ogni giro -- quindi si muove da solo a ogni aggiornamento dell'incumbent.
   lam=1 e' il cutoff all'incumbent (il piu' lasco), lam=0 e' a z_low (il piu'
   aggressivo). E' la convenzione v2, quella di MF: vedi grid/CONVENZIONE.md.

   SCIP di suo NON impone nessun cutoff sull'LP del dive (il costo entra solo
   via alpha), quindi questo braccio non esiste in SCIP e va aggiunto per
   simulare cio' che farebbe chi implementa il pump come in Fischetti-Glover-
   Lodi 2005. cutlam e moat sono alternativi: se cutlam >= 0 vince cutlam.

2) heuristics/feaspump/restartonsol  (default FALSE)

   Il pump di SCIP esce dal ciclo appena l'iterato del dive diventa intero
   (nfracs == 0): una chiamata, una soluzione, fine. Con limits/nodes 1 nessuno
   lo richiama e il time limit non si riempie. Con restartonsol il ciclo non si
   ferma li': la soluzione viene registrata (e' la perturbazione randomizzata
   gia' presente in SCIP a rimettere in moto il pump, handleCycle, perche' il
   suo trigger e' proprio "nuova soluzione migliore trovata"), e si continua
   fino al time limit o al budget di iterazioni LP.

   Serve una guardia: con nfracs == 0 il calcolo di maxnflipcands chiederebbe
   un intero casuale in un intervallo vuoto.

Lo script e' idempotente.
"""
import io
import sys

# ---------------------------------------------------------------- struct
A_STRUCT = """   SCIP_Real             moatwmin;           /**< minimum moat width, as a fraction of the integrality gap */"""
N_STRUCT = """   SCIP_Real             moatwmin;           /**< minimum moat width, as a fraction of the integrality gap */
   SCIP_Real             cutlam;             /**< objective cutoff at z_low + cutlam*(z_inc - z_low); <0: no cutoff */
   SCIP_Bool             restartonsol;       /**< should the pump keep going after the diving LP became integral? */
   int                   nintegralfound;     /**< integral LP iterates handed in from inside the loop (treatment-blind delivery) */"""

# ------------------------------------------------- azzeramento del contatore nuovo
# Si accoda alle due righe e le lascia intatte: scip_patch_osc.py ancora sulle
# stesse due righe, e deve continuare a trovarle una volta sola.
A_INIT = """   nloops = 0;
   nstallloops = 0;"""
N_INIT = """   nloops = 0;
   nstallloops = 0;
   heurdata->nintegralfound = 0;"""

# ---------------------------------------------------------------- la riga esiste anche col cutoff fisso
A_DIVE = """   if( heurdata->moat )
   {
      SCIP_CALL( SCIPcreateEmptyRowUnspec(scip, &moatrow, "fp_moat","""
N_DIVE = """   if( heurdata->moat || heurdata->cutlam >= 0.0 )
   {
      SCIP_CALL( SCIPcreateEmptyRowUnspec(scip, &moatrow, "fp_moat","""

# ---------------------------------------------------------------- rhs: cutoff fisso oppure moat
A_RHS = """      if( moatrow != NULL && !SCIPisInfinity(scip, SCIPgetUpperbound(scip)) )
      {
         SCIP_Real zinc = SCIPgetUpperbound(scip);
         SCIP_Real zlow = SCIPgetLowerbound(scip);
         SCIP_Real gap = MAX(zinc - zlow, 0.0);
         SCIP_Real w = MAX(moatwidth, heurdata->moatwmin * gap);
         SCIP_Real rhs = MAX(zlow + 0.02 * gap, zinc - w);

         SCIP_CALL( SCIPchgRowRhsDive(scip, moatrow, rhs) );
      }"""
N_RHS = """      if( moatrow != NULL && !SCIPisInfinity(scip, SCIPgetUpperbound(scip)) )
      {
         SCIP_Real zinc = SCIPgetUpperbound(scip);
         SCIP_Real zlow = SCIPgetLowerbound(scip);
         SCIP_Real gap = MAX(zinc - zlow, 0.0);
         SCIP_Real rhs;

         if( heurdata->cutlam >= 0.0 )
         {
            /* the "clever user" cutoff: a fixed fraction of the current
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

# ---------------------------------------------------------------- il ciclo non si ferma sulla soluzione
A_WHILE = """   while( nfracs > 0
      && heurdata->nlpiterations < adjustedMaxNLPIterations(maxnlpiterations, nsolsfound, nstallloops)"""
N_WHILE = """   while( (nfracs > 0 || heurdata->restartonsol)
      && heurdata->nlpiterations < adjustedMaxNLPIterations(maxnlpiterations, nsolsfound, nstallloops)"""

A_FLIP = """      maxnflipcands = SCIPrandomGetInt(heurdata->randnumgen, MIN(nfracs/2+1, heurdata->minflips), MIN(nfracs, maxflips));"""
N_FLIP = """      /* with restartonsol the loop is entered with nfracs == 0 as well, and
       * then the interval below would be empty
       */
      maxnflipcands = SCIPrandomGetInt(heurdata->randnumgen, MIN(nfracs/2+1, heurdata->minflips),
         MAX(MIN(nfracs, maxflips), MIN(nfracs/2+1, heurdata->minflips)));"""

A_PERT = """      if( nloops % heurdata->perturbfreq == 0 || (heurdata->pertsolfound && SCIPgetNBestSolsFound(scip) > nbestsolsfound) )"""
N_PERT = """      if( nloops % heurdata->perturbfreq == 0 || (heurdata->pertsolfound && SCIPgetNBestSolsFound(scip) > nbestsolsfound)
         || (heurdata->restartonsol && nfracs == 0) )"""

# ------------------------------------------------ consegna treatment-blind
# Deve stare in TESTA al corpo del loop, dove SCIP stesso collega roundedsol
# all'LP del dive: da li' in poi il giro cambia i coefficienti obiettivo del
# dive (SCIPchgVarObjDive) e l'LP risulta "non risolto" anche se il vettore c'e'
# ancora --- SCIPlinkLPSol li' fallisce con «LP solution does not exist»
# (imparato con uno smoke, 02/09/2026).
A_LINK = """      SCIP_CALL( SCIPlinkLPSol(scip, heurdata->roundedsol) );"""
N_LINK = """      /* Treatment-blind delivery (02/09/2026, after the external audit).
       * The stock pump hands an integral iterate to the solver only AFTER the
       * loop (see the block below the loop), and with restartonsol the loop
       * does not stop there: a variant without recovery therefore used to
       * deliver its solutions only at the time limit, if the last iterate
       * happened to be integral at all. That confounded the 2x2 design ---
       * cutoff-vs-plain was measuring solution DELIVERY, not the policy ---
       * and left 50 of 745 plain runs without a solution on instances the
       * filter had solved. Here EVERY variant hands the integral iterate in
       * the moment it appears, with exactly the call SCIP makes after the
       * loop: the LP iterate satisfies the LP rows by construction, and
       * SCIPlinkLPSol recomputes the objective with the unchanged
       * coefficients when the dive has altered them. It sits here, before
       * the round touches the dive objective, because after that the LP is
       * flagged unsolved.
       */
      if( heurdata->restartonsol && nfracs == 0 && !lperror
         && lpsolstat == SCIP_LPSOLSTAT_OPTIMAL && SCIPgetLPSolstat(scip) == SCIP_LPSOLSTAT_OPTIMAL )
      {
         SCIP_Bool integralstored;

         SCIP_CALL( SCIPlinkLPSol(scip, heurdata->sol) );
         SCIP_CALL( SCIPtrySol(scip, heurdata->sol, FALSE, FALSE, FALSE, FALSE, FALSE, &integralstored) );
         if( integralstored )
         {
            heurdata->nintegralfound++;
            *result = SCIP_FOUNDSOL;
         }
      }

      SCIP_CALL( SCIPlinkLPSol(scip, heurdata->roundedsol) );"""

# ---------------------------------------------------------------- parametri
A_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/moat","""
N_PARAM = """   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/cutlam",
         "objective cutoff at z_low + cutlam*(z_inc - z_low); negative: no cutoff",
         &heurdata->cutlam, FALSE, -1.0, -1.0, 1.0, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/restartonsol",
         "should the pump keep going after the diving LP became integral?",
         &heurdata->restartonsol, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/moat","""

STEPS = [(A_STRUCT, N_STRUCT, "struct heurdata"),
         (A_INIT, N_INIT, "azzeramento di nintegralfound"),
         (A_DIVE, N_DIVE, "creazione della riga anche col cutoff fisso"),
         (A_RHS, N_RHS, "rhs: cutlam oppure moat"),
         (A_WHILE, N_WHILE, "il ciclo non si ferma su nfracs == 0"),
         (A_FLIP, N_FLIP, "guardia su maxnflipcands"),
         (A_PERT, N_PERT, "perturbazione forzata al restart"),
         (A_LINK, N_LINK, "consegna treatment-blind dell'iterato intero"),
         (A_PARAM, N_PARAM, "parametri")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "cutlam" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "fp_moat" not in s:
        print("ERRORE: applica prima scip_patch.py e scip_patch_moat.py")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"bracci applicati a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
