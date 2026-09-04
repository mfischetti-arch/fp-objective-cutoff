#!/usr/bin/env python3
"""Completamento delle continue su un CLONE dell'LP (heuristics/feaspump/lpfix).

Il problema. Il nostro recupero (scip_patch.py, tryrounded) prende `roundedsol`
--- che e' la soluzione dell'LP del dive con le sole entrate INTERE sovrascritte
dall'arrotondamento (heur_feaspump.c: SCIPlinkLPSol, poi SCIPsetSolVal sugli
interi) --- e la passa a SCIPtrySol. Il controllo e' corretto: `checklprows =
TRUE` verifica tutti i vincoli veri, e la riga invalida del cutoff non e' un
vincolo (SCIPcreateEmptyRowUnspec + SCIPaddRowDive), quindi nessuno la controlla.
Ma NON e' ottimale: le continue di quel vettore vengono da un LP che minimizzava
la DISTANZA sotto una riga INVALIDA. Su un problema misto --- si pensi a un
2-stage con interi al master e solo continue al secondo livello --- sono un
vettore arbitrario rispetto ai vincoli che dovrebbero soddisfare: il test
fallisce e concludiamo "non ammissibile" dove un completamento esiste.

La cosa giusta (MF, 02/09/2026): fissare le sole variabili INTERE al valore
arrotondato e minimizzare c'x su P. Decide l'ammissibilita' e da' il MIGLIOR
completamento, non uno qualsiasi.

Perche' un clone e non il dive (MF). I due LP vanno tenuti separati e
parametrizzati indipendentemente: la base del dive --- obiettivo distanza, righe
invalide dentro --- non e' un buon warm start per un LP che minimizza c'x con
gli interi fissati, e fissare i bound dentro il dive distruggerebbe la base del
pump. Con un LPI dedicato, fra un giro e l'altro cambiano SOLO i bound degli
interi: il duale resta ammissibile e il duale simplex riparte in poche
iterazioni. Il clone si costruisce PRIMA di SCIPstartDive, quindi non contiene
per costruzione nessuna riga invalida.

Il clone PROPONE, SCIPtrySol CERTIFICA: una copia imperfetta dell'LP del nodo
puo' sprecare un LP, non puo' far accettare un punto sbagliato.

Che cosa fa SCIP di suo: niente, perche' il punto arrotondato non lo prova mai.
L'unico meccanismo affine e' `stage3` (sub-MIP di local branching alla fine),
DEFAULT_STAGE3 = FALSE.

Da applicare DOPO scip_patch_rcut.py.  Uso:
    python3 scip_patch_lpfix.py ~/scipwork/scip/src/scip/heur_feaspump.c
Parametri e contatori nuovi:
    heuristics/feaspump/lpfix   BOOL, default FALSE
    fp_exit: lpfix=<LP risolti> lpfixfeas=<accettati> lpfixinf=<infeasible>
"""
import io
import sys

# --------------------------------------------------------------- 1. include
A_INC = """#include "scip/scip_var.h\""""
N_INC = """#include "scip/scip_var.h"
#include "lpi/lpi.h\""""

# ---------------------------------------------------------------- 2. struct
A_STRUCT = """   int                   nroundedfound;      /**< number of solutions accepted from the rounded point */"""
N_STRUCT = """   int                   nroundedfound;      /**< number of solutions accepted from the rounded point */
   SCIP_Bool             lpfix;              /**< complete the rounded point on a clone LP: integers fixed, c'x minimised? */
   int                   nlpfix;             /**< completion LPs solved */
   int                   nlpfixfeas;         /**< ...of those, how many produced a solution SCIP accepted */
   int                   nlpfixinf;          /**< ...how many came out infeasible */"""

# ---------------------------------------------------------------- 3. locali
A_LOCAL = """   int rrowsn;                /* how many rows were actually created */"""
N_LOCAL = """   int rrowsn;                /* how many rows were actually created */
   SCIP_LPI* fixlpi;          /* clone of the node LP, true rows only: completes the rounded point */
   int* fixind;               /* LP positions of the integer columns */
   SCIP_Real* fixbd;          /* the values they are fixed to, one round at a time */
   SCIP_Real* fixsol;         /* primal solution of the clone */
   int fixn;                  /* number of integer columns */
   int fixncols;              /* number of columns of the clone */"""

A_NULL = """   rrowsn = 0;
   rrownext = 0;
   rrowactive = -1;"""
N_NULL = """   rrowsn = 0;
   rrownext = 0;
   rrowactive = -1;
   fixlpi = NULL;
   fixind = NULL;
   fixbd = NULL;
   fixsol = NULL;
   fixn = 0;
   fixncols = 0;"""

# ------------------------------------------------- 4. costruzione del clone
A_CLONE = """   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );"""
N_CLONE = """   /* The completion LP: a CLONE of the node relaxation in its own LPI, with the
    * TRUE objective and only the true rows.
    *
    * It is built HERE, before SCIPstartDive, so it cannot contain any of the
    * rows the pump adds to the dive (the objective cutoff, the moat, the random
    * directions): those are dive rows and do not exist yet.
    *
    * Two separate LPs on purpose (MF, 02/09/2026): the pump's dive minimises a
    * distance under deliberately invalid rows, and its basis is no warm start
    * for an LP that minimises c'x with the integers fixed -- while fixing bounds
    * inside the dive would wreck the pump's own basis. Here, between two rounds
    * only the integer bounds move: the dual stays feasible and the dual simplex
    * reoptimises in a handful of iterations.
    */
   /* SCIP 11 counts continuous variables in two buckets: SCIPgetNContVars are
    * the genuinely continuous ones and SCIPgetNContImplVars those the presolver
    * proved implicitly integral. The pump rounds neither --- its enforced set is
    * nvars minus both (see the computation of nenfovars above) --- so both are
    * what the completion has left to optimise, and both must count here. Using
    * SCIPgetNContVars alone silently disables the whole thing on instances whose
    * continuous variables are all implied, which is most of MIPLIB 2017.
    */
   if( heurdata->lpfix && SCIPgetNContVars(scip) + SCIPgetNContImplVars(scip) > 0 )
   {
      SCIP_COL** clonecols;
      SCIP_ROW** clonerows;
      int nclonecols;
      int nclonerows;

      SCIP_CALL( SCIPgetLPColsData(scip, &clonecols, &nclonecols) );
      SCIP_CALL( SCIPgetLPRowsData(scip, &clonerows, &nclonerows) );

      if( nclonecols > 0 && nclonerows > 0 )
      {
         SCIP_Real* cobj;
         SCIP_Real* clb;
         SCIP_Real* cub;
         SCIP_Real* clhs;
         SCIP_Real* crhs;
         int* cbeg;
         int* cind;
         SCIP_Real* cval;
         SCIP_Real lpiinf;
         int cnnz;
         int k;
         int r;

         cnnz = 0;
         for( k = 0; k < nclonecols; ++k )
            cnnz += SCIPcolGetNLPNonz(clonecols[k]);

         SCIP_CALL( SCIPlpiCreate(&fixlpi, SCIPgetMessagehdlr(scip), "fp_fixlp", SCIP_OBJSEN_MINIMIZE) );
         lpiinf = SCIPlpiInfinity(fixlpi);

         SCIP_CALL( SCIPallocBufferArray(scip, &cobj, nclonecols) );
         SCIP_CALL( SCIPallocBufferArray(scip, &clb, nclonecols) );
         SCIP_CALL( SCIPallocBufferArray(scip, &cub, nclonecols) );
         SCIP_CALL( SCIPallocBufferArray(scip, &cbeg, nclonecols) );
         SCIP_CALL( SCIPallocBufferArray(scip, &clhs, nclonerows) );
         SCIP_CALL( SCIPallocBufferArray(scip, &crhs, nclonerows) );
         SCIP_CALL( SCIPallocBufferArray(scip, &cind, MAX(cnnz, 1)) );
         SCIP_CALL( SCIPallocBufferArray(scip, &cval, MAX(cnnz, 1)) );
         SCIP_CALL( SCIPallocBlockMemoryArray(scip, &fixind, nclonecols) );
         SCIP_CALL( SCIPallocBlockMemoryArray(scip, &fixbd, nclonecols) );
         SCIP_CALL( SCIPallocBlockMemoryArray(scip, &fixsol, nclonecols) );

         for( r = 0; r < nclonerows; ++r )
         {
            SCIP_Real cst = SCIProwGetConstant(clonerows[r]);
            SCIP_Real l = SCIProwGetLhs(clonerows[r]);
            SCIP_Real u = SCIProwGetRhs(clonerows[r]);

            clhs[r] = SCIPisInfinity(scip, -l) ? -lpiinf : l - cst;
            crhs[r] = SCIPisInfinity(scip, u) ? lpiinf : u - cst;
         }

         cnnz = 0;
         for( k = 0; k < nclonecols; ++k )
         {
            SCIP_ROW** colrows = SCIPcolGetRows(clonecols[k]);
            SCIP_Real* colvals = SCIPcolGetVals(clonecols[k]);
            SCIP_VAR* colvar = SCIPcolGetVar(clonecols[k]);
            int ncolrows = SCIPcolGetNLPNonz(clonecols[k]);
            int j;

            cbeg[k] = cnnz;
            cobj[k] = SCIPvarGetObj(colvar);
            clb[k] = SCIPisInfinity(scip, -SCIPvarGetLbGlobal(colvar)) ? -lpiinf : SCIPvarGetLbGlobal(colvar);
            cub[k] = SCIPisInfinity(scip, SCIPvarGetUbGlobal(colvar)) ? lpiinf : SCIPvarGetUbGlobal(colvar);

            for( j = 0; j < ncolrows; ++j )
            {
               int rpos = SCIProwGetLPPos(colrows[j]);

               if( rpos >= 0 && rpos < nclonerows )
               {
                  cind[cnnz] = rpos;
                  cval[cnnz] = colvals[j];
                  ++cnnz;
               }
            }

            if( SCIPvarGetType(colvar) == SCIP_VARTYPE_BINARY
               || SCIPvarGetType(colvar) == SCIP_VARTYPE_INTEGER )
            {
               fixind[fixn] = k;
               ++fixn;
            }
         }

         SCIP_CALL( SCIPlpiLoadColLP(fixlpi, SCIP_OBJSEN_MINIMIZE, nclonecols, cobj, clb, cub, NULL,
               nclonerows, clhs, crhs, NULL, cnnz, cbeg, cind, cval) );
         fixncols = nclonecols;

         SCIPfreeBufferArray(scip, &cval);
         SCIPfreeBufferArray(scip, &cind);
         SCIPfreeBufferArray(scip, &crhs);
         SCIPfreeBufferArray(scip, &clhs);
         SCIPfreeBufferArray(scip, &cbeg);
         SCIPfreeBufferArray(scip, &cub);
         SCIPfreeBufferArray(scip, &clb);
         SCIPfreeBufferArray(scip, &cobj);

         SCIPdebugMsg(scip, "feasibility pump: completion LP built, %d cols (%d integer), %d rows\\n",
            nclonecols, fixn, nclonerows);
      }
   }

   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );"""

# ------------------------------------- 5. il completamento, dentro il recupero
A_TRY = """         if( stored )
         {
            heurdata->nroundedfound++;
            SCIPdebugMsg(scip, "feasibility pump: rounded point accepted as solution\\n");
            *result = SCIP_FOUNDSOL;
         }
      }"""
N_TRY = """         if( stored )
         {
            heurdata->nroundedfound++;
            SCIPdebugMsg(scip, "feasibility pump: rounded point accepted as solution\\n");
            *result = SCIP_FOUNDSOL;
         }

         /* The completion. Fix the integers at the rounded values on the clone
          * and minimise the TRUE objective over what is left --- which on a
          * mixed problem is the continuous part. This is run whether or not the
          * direct check above succeeded: when it did, the completion returns the
          * same integers with a BETTER continuous part, because the direct point
          * carries the continuous values of an LP that was minimising a distance
          * under an invalid row.
          */
         if( fixlpi != NULL )
         {
            SCIP_COL** curcols;
            int ncurcols;

            SCIP_CALL( SCIPgetLPColsData(scip, &curcols, &ncurcols) );

            /* the column set must still be the one the clone was built from */
            if( ncurcols == fixncols )
            {
               int k;

               for( k = 0; k < fixn; ++k )
                  fixbd[k] = SCIPgetSolVal(scip, heurdata->roundedsol, SCIPcolGetVar(curcols[fixind[k]]));

               SCIP_CALL( SCIPlpiChgBounds(fixlpi, fixn, fixind, fixbd, fixbd) );
               heurdata->nlpfix++;

               if( SCIPlpiSolveDual(fixlpi) == SCIP_OKAY && SCIPlpiIsOptimal(fixlpi) )
               {
                  SCIP_SOL* fixtrysol;
                  SCIP_Bool fixstored;

                  SCIP_CALL( SCIPlpiGetSol(fixlpi, NULL, fixsol, NULL, NULL, NULL) );

                  /* Costruita da zero, come in scip_patch.py: si parte dal punto
                   * arrotondato perche' le variabili fuori dall'LP tengano un
                   * valore sensato, poi ogni colonna dell'LP viene sovrascritta
                   * con la risposta del clone. SCIPsetSolVal mantiene sol->obj
                   * da se' con SCIPvarGetUnchangedObj: nessun recompute, che qui
                   * era la stessa chiamata sbagliata corretta in scip_patch.py.
                   */
                  SCIP_CALL( SCIPcreateSol(scip, &fixtrysol, heur) );
                  {
                     SCIP_VAR** allvars;
                     int nallvars;
                     int iv;

                     SCIP_CALL( SCIPgetVarsData(scip, &allvars, &nallvars, NULL, NULL, NULL, NULL) );
                     for( iv = 0; iv < nallvars; ++iv )
                     {
                        SCIP_CALL( SCIPsetSolVal(scip, fixtrysol, allvars[iv],
                              SCIPgetSolVal(scip, heurdata->roundedsol, allvars[iv])) );
                     }
                  }
                  for( k = 0; k < fixncols; ++k )
                  {
                     SCIP_CALL( SCIPsetSolVal(scip, fixtrysol, SCIPcolGetVar(curcols[k]), fixsol[k]) );
                  }
                  SCIP_CALL( SCIPtrySolFree(scip, &fixtrysol, FALSE, FALSE, TRUE, TRUE, TRUE, &fixstored) );

                  if( fixstored )
                  {
                     heurdata->nlpfixfeas++;
                     heurdata->nroundedfound++;
                     SCIPdebugMsg(scip, "feasibility pump: completed rounded point accepted\\n");
                     *result = SCIP_FOUNDSOL;
                  }
               }
               else if( SCIPlpiIsPrimalInfeasible(fixlpi) )
                  heurdata->nlpfixinf++;
            }
         }
      }"""

# ------------------------------------------------------------------ 6. free
A_FREE = """   if( rrows != NULL )
   {"""
N_FREE = """   if( fixlpi != NULL )
   {
      SCIPfreeBlockMemoryArray(scip, &fixsol, fixncols);
      SCIPfreeBlockMemoryArray(scip, &fixbd, fixncols);
      SCIPfreeBlockMemoryArray(scip, &fixind, fixncols);
      SCIP_CALL( SCIPlpiFree(&fixlpi) );
   }
   if( rrows != NULL )
   {"""

# ------------------------------------------------------------ 7. contatori
A_INIT = """   heurdata->nrcut = 0;"""
N_INIT = """   heurdata->nrcut = 0;
   heurdata->nlpfix = 0;
   heurdata->nlpfixfeas = 0;
   heurdata->nlpfixinf = 0;"""

A_DIAG = """      " rcut=%d rcutnosep=%d rcutinf=%d\\n","""
N_DIAG = """      " rcut=%d rcutnosep=%d rcutinf=%d"
      " lpfix=%d lpfixfeas=%d lpfixinf=%d ncont=%d fixcols=%d fixint=%d\\n","""

A_DIAG2 = """      heurdata->nrcut, heurdata->nrcutnosep, heurdata->nrcutinf);"""
N_DIAG2 = """      heurdata->nrcut, heurdata->nrcutnosep, heurdata->nrcutinf,
      heurdata->nlpfix, heurdata->nlpfixfeas, heurdata->nlpfixinf,
      SCIPgetNContVars(scip) + SCIPgetNContImplVars(scip), fixncols, fixn);"""

# ------------------------------------------------------------- 8. parametro
A_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/rcutflip","""
N_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/lpfix",
         "complete the rounded point on a clone LP: integers fixed, true objective minimised over the rest",
         &heurdata->lpfix, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/rcutflip","""

STEPS = [(A_INC, N_INC, "include di lpi/lpi.h"),
         (A_STRUCT, N_STRUCT, "campi in struct heurdata"),
         (A_LOCAL, N_LOCAL, "variabili locali del clone"),
         (A_NULL, N_NULL, "inizializzazione a NULL"),
         (A_CLONE, N_CLONE, "costruzione del clone prima del dive"),
         (A_TRY, N_TRY, "completamento dentro il recupero"),
         (A_FREE, N_FREE, "free del clone"),
         (A_INIT, N_INIT, "azzeramento dei contatori"),
         (A_DIAG, N_DIAG, "formato di fp_exit"),
         (A_DIAG2, N_DIAG2, "argomenti di fp_exit"),
         (A_PARAM, N_PARAM, "parametro lpfix")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "nlpfix" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "nrcut" not in s:
        print("ERRORE: applica prima scip_patch_rcut.py")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"completamento su clone applicato a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
