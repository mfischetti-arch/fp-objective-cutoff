#!/usr/bin/env python3
"""Costruisce heur_feaspump_min.c dal pristino (SCIP 11.0.0, commit dba4b2a).

    python3 build_min.py heur_feaspump_pristine.c heur_feaspump_min.c

Patch MINIMA: cutlam, tryrounded, lpfix, restartonsol. Nient'altro.
Ogni ancora deve comparire UNA volta nel pristino, altrimenti si ferma.
"""
import io
import sys

NOTICE = """/* NOTICE (Apache License 2.0, section 4(b)): this file has been MODIFIED with
 * respect to the original SCIP Optimization Suite distribution (SCIP 11.0.0,
 * git commit dba4b2a).
 *
 * Modified on 2026-09-16 by Matteo Fischetti (University of Padova).
 * All changes are guarded by new parameters whose default value reproduces
 * the original behaviour exactly:
 *   heuristics/feaspump/cutlam        objective cutoff row c'x <= U in the
 *                                     diving LP, U = zlow + cutlam*(zinc - zlow)
 *   heuristics/feaspump/tryrounded    feasibility check of the rounded point
 *                                     at every pumping round
 *   heuristics/feaspump/lpfix         completion of the rounded point on a
 *                                     clone LP (integers fixed, c'x minimised)
 *   heuristics/feaspump/restartonsol  the pump keeps going after the diving
 *                                     LP became integral
 *
 * The original file is part of the SCIP Optimization Suite, Copyright (C)
 * Zuse Institute Berlin (ZIB) and contributors, licensed under the Apache
 * License, Version 2.0. The original copyright and license notices below are
 * retained unchanged.
 */
"""

STEPS = []

# ---------------------------------------------------------------- include
STEPS.append(("include", """#include "scip/scip_var.h"
""", """#include "scip/scip_var.h"
#include "lpi/lpi.h"
"""))

# ----------------------------------------------------------------- struct
STEPS.append(("struct", """   SCIP_Bool             copycuts;           /**< should all active cuts from cutpool be copied to constraints in
                                              *   subproblem?
                                              */
};""", """   SCIP_Bool             copycuts;           /**< should all active cuts from cutpool be copied to constraints in
                                              *   subproblem?
                                              */
   SCIP_Real             cutlam;             /**< objective cutoff in the diving LP at zlow + cutlam*(zinc - zlow);
                                              *   negative: no cutoff
                                              */
   SCIP_Bool             tryrounded;         /**< should the rounded point be tried as a solution at every round? */
   SCIP_Bool             lpfix;              /**< should the rounded point be completed on a clone LP (integers fixed,
                                              *   true objective minimised over the remaining variables)?
                                              */
   SCIP_Bool             restartonsol;       /**< should the pump keep going after the diving LP became integral? */
};"""))

# ------------------------------------------------------------ local decls
STEPS.append(("locals", """   SCIP_SOL* closestsol;      /* rounded solution closest to the LP relaxation: used for stage3 */""",
"""   SCIP_SOL* closestsol;      /* rounded solution closest to the LP relaxation: used for stage3 */
   SCIP_ROW* cutoffrow;       /* objective cutoff row added to the diving LP, or NULL */
   SCIP_LPI* fixlpi;          /* clone of the node LP (true rows only) used to complete the rounded point, or NULL */
   int* fixind;               /* LP positions of the integer columns of the clone */
   SCIP_Real* fixbd;          /* values the integer columns are fixed to, one round at a time */
   SCIP_Real* fixsol;         /* primal solution of the clone */
   int fixn;                  /* number of integer columns of the clone */
   int fixncols;              /* number of columns of the clone */"""))

# ------------------------------------------------------------------- init
STEPS.append(("init", """   SCIP_CALL( SCIPallocBufferArray(scip, &lastroundedsols, heurdata->cyclelength) );
""", """   SCIP_CALL( SCIPallocBufferArray(scip, &lastroundedsols, heurdata->cyclelength) );
   cutoffrow = NULL;
   fixlpi = NULL;
   fixind = NULL;
   fixbd = NULL;
   fixsol = NULL;
   fixn = 0;
   fixncols = 0;
"""))

# ------------------------------------------ clone LP, start dive, cutoff row
STEPS.append(("clone+dive", """   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );
""", """   /* completion LP: a clone of the node relaxation in its own LPI, with the true objective and only the true rows.
    * It is built before SCIPstartDive, so that it cannot contain the cutoff row added to the diving LP below.
    * The two LPs are kept separate on purpose: the diving LP minimises a distance and its basis is no warm start for
    * an LP that minimises c'x with the integers fixed, whereas here only the integer bounds change between two
    * rounds, so that the dual simplex reoptimises in a few iterations.
    *
    * Both genuinely continuous and implied integral variables are left free in the completion, as the pump rounds
    * neither of them (see the computation of nenfovars above).
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

            if( SCIPvarGetType(colvar) == SCIP_VARTYPE_BINARY || SCIPvarGetType(colvar) == SCIP_VARTYPE_INTEGER )
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
   SCIP_CALL( SCIPstartDive(scip) );

   /* objective cutoff: the row c'x <= rhs is added to the diving LP with a free right-hand side, and its rhs is
    * moved at every pumping round (see the loop below) according to the current incumbent
    */
   if( heurdata->cutlam >= 0.0 )
   {
      SCIP_CALL( SCIPcreateEmptyRowUnspec(scip, &cutoffrow, "fp_cutoff", -SCIPinfinity(scip), SCIPinfinity(scip),
            FALSE, FALSE, TRUE) );
      SCIP_CALL( SCIPcacheRowExtensions(scip, cutoffrow) );
      for( i = 0; i < nvars; i++ )
      {
         if( !SCIPisZero(scip, SCIPvarGetObj(vars[i])) )
         {
            SCIP_CALL( SCIPaddVarToRow(scip, cutoffrow, vars[i], SCIPvarGetObj(vars[i])) );
         }
      }
      SCIP_CALL( SCIPflushRowExtensions(scip, cutoffrow) );
      SCIP_CALL( SCIPaddRowDive(scip, cutoffrow) );

      /* adding a row invalidates the current diving LP solution, which is needed by SCIPlinkLPSol at the top of the
       * pumping loop; the rhs is still infinite here, so this resolve cannot cut anything off
       */
      SCIP_CALL( SCIPsolveDiveLP(scip, -1, &lperror, NULL) );
      if( lperror || SCIPgetLPSolstat(scip) != SCIP_LPSOLSTAT_OPTIMAL )
      {
         SCIP_CALL( SCIPreleaseRow(scip, &cutoffrow) );
         cutoffrow = NULL;
      }
   }
"""))

# ------------------------------------------------------------------ while
STEPS.append(("while", """   while( nfracs > 0
      && heurdata->nlpiterations < adjustedMaxNLPIterations(maxnlpiterations, nsolsfound, nstallloops)""",
"""   while( (nfracs > 0 || heurdata->restartonsol)
      && heurdata->nlpiterations < adjustedMaxNLPIterations(maxnlpiterations, nsolsfound, nstallloops)"""))

# ------------------------------------------------- integral iterate handed in
STEPS.append(("link", """      SCIP_CALL( SCIPlinkLPSol(scip, heurdata->roundedsol) );
""", """      /* with restartonsol the loop is entered with an integral LP iterate as well: hand it in right away, exactly
       * as it is done after the loop (the LP iterate satisfies the LP rows by construction), before the round changes
       * the objective of the diving LP
       */
      if( heurdata->restartonsol && nfracs == 0 && !lperror
         && lpsolstat == SCIP_LPSOLSTAT_OPTIMAL && SCIPgetLPSolstat(scip) == SCIP_LPSOLSTAT_OPTIMAL )
      {
         SCIP_Bool integralstored;

         SCIP_CALL( SCIPlinkLPSol(scip, heurdata->sol) );
         SCIP_CALL( SCIPtrySol(scip, heurdata->sol, FALSE, FALSE, FALSE, FALSE, FALSE, &integralstored) );
         if( integralstored )
            *result = SCIP_FOUNDSOL;
      }

      SCIP_CALL( SCIPlinkLPSol(scip, heurdata->roundedsol) );
"""))

# ------------------------------------------------------------- flip guard
STEPS.append(("flip", """      maxnflipcands = SCIPrandomGetInt(heurdata->randnumgen, MIN(nfracs/2+1, heurdata->minflips), MIN(nfracs, maxflips));""",
"""      /* with restartonsol the loop is entered with nfracs == 0 as well, and the interval must not be empty */
      maxnflipcands = SCIPrandomGetInt(heurdata->randnumgen, MIN(nfracs/2+1, heurdata->minflips),
         MAX(MIN(nfracs, maxflips), MIN(nfracs/2+1, heurdata->minflips)));"""))

# ---------------------------------------------- rounded point: check + complete
STEPS.append(("tryrounded+lpfix", """      SCIPfreeBufferArray(scip, &pseudocands);

      /* initialize cycle check */""", """      SCIPfreeBufferArray(scip, &pseudocands);

      /* try the rounded point as a solution, before the anti-cycling flips move it away.
       *
       * roundedsol is linked to the diving LP, whose objective is the distance, not the cost: the solution to be
       * tried is therefore built from scratch, so that its objective value is computed with the unchanged objective
       * coefficients (SCIPsetSolVal uses SCIPvarGetUnchangedObj). checklprows must be TRUE, as the rounded point
       * does not satisfy the LP rows by construction.
       */
      if( heurdata->tryrounded )
      {
         SCIP_SOL* trysol;
         SCIP_VAR** allvars;
         SCIP_Bool stored;
         int nallvars;
         int iv;

         SCIP_CALL( SCIPcreateSol(scip, &trysol, heur) );
         SCIP_CALL( SCIPgetVarsData(scip, &allvars, &nallvars, NULL, NULL, NULL, NULL) );
         for( iv = 0; iv < nallvars; ++iv )
         {
            SCIP_CALL( SCIPsetSolVal(scip, trysol, allvars[iv], SCIPgetSolVal(scip, heurdata->roundedsol, allvars[iv])) );
         }
         SCIP_CALL( SCIPtrySolFree(scip, &trysol, FALSE, FALSE, TRUE, TRUE, TRUE, &stored) );
         if( stored )
         {
            SCIPdebugMsg(scip, "feasibility pump: rounded point accepted as solution\\n");
            *result = SCIP_FOUNDSOL;
         }
      }

      /* complete the rounded point: fix the integer variables at their rounded values on the clone LP and minimise
       * the true objective over the remaining variables; the resulting point is tried as a solution
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

            if( SCIPlpiSolveDual(fixlpi) == SCIP_OKAY && SCIPlpiIsOptimal(fixlpi) )
            {
               SCIP_SOL* fixtrysol;
               SCIP_VAR** allvars;
               SCIP_Bool fixstored;
               int nallvars;
               int iv;

               SCIP_CALL( SCIPlpiGetSol(fixlpi, NULL, fixsol, NULL, NULL, NULL) );

               /* built from scratch as above: the rounded values for variables outside the LP, then every LP column
                * overwritten with the answer of the clone
                */
               SCIP_CALL( SCIPcreateSol(scip, &fixtrysol, heur) );
               SCIP_CALL( SCIPgetVarsData(scip, &allvars, &nallvars, NULL, NULL, NULL, NULL) );
               for( iv = 0; iv < nallvars; ++iv )
               {
                  SCIP_CALL( SCIPsetSolVal(scip, fixtrysol, allvars[iv],
                        SCIPgetSolVal(scip, heurdata->roundedsol, allvars[iv])) );
               }
               for( k = 0; k < fixncols; ++k )
               {
                  SCIP_CALL( SCIPsetSolVal(scip, fixtrysol, SCIPcolGetVar(curcols[k]), fixsol[k]) );
               }
               SCIP_CALL( SCIPtrySolFree(scip, &fixtrysol, FALSE, FALSE, TRUE, TRUE, TRUE, &fixstored) );

               if( fixstored )
               {
                  SCIPdebugMsg(scip, "feasibility pump: completed rounded point accepted as solution\\n");
                  *result = SCIP_FOUNDSOL;
               }
            }
         }
      }

      /* initialize cycle check */"""))

# ------------------------------------------------------------ perturbation
STEPS.append(("perturb", """      if( nloops % heurdata->perturbfreq == 0 || (heurdata->pertsolfound && SCIPgetNBestSolsFound(scip) > nbestsolsfound) )""",
"""      if( nloops % heurdata->perturbfreq == 0 || (heurdata->pertsolfound && SCIPgetNBestSolsFound(scip) > nbestsolsfound)
         || (heurdata->restartonsol && nfracs == 0) )"""))

# ------------------------------------------------------------- cutoff rhs
STEPS.append(("rhs", """      /* the LP with the new (distance) objective is solved */
      nlpiterations = SCIPgetNLPIterations(scip);""", """      /* move the objective cutoff: rhs = zlow + cutlam * (zinc - zlow), which follows the incumbent by itself;
       * without an incumbent the row is left free
       */
      if( cutoffrow != NULL )
      {
         SCIP_Real zinc = SCIPgetUpperbound(scip);
         SCIP_Real zlow = SCIPgetLowerbound(scip);

         if( SCIPisInfinity(scip, zinc) )
         {
            SCIP_CALL( SCIPchgRowRhsDive(scip, cutoffrow, SCIPinfinity(scip)) );
         }
         else
         {
            SCIP_Real gap = MAX(zinc - zlow, 0.0);
            SCIP_Real lam = MAX(0.02, MIN(1.0, heurdata->cutlam));

            SCIP_CALL( SCIPchgRowRhsDive(scip, cutoffrow, zlow + lam * gap) );
         }
      }

      /* the LP with the new (distance) objective is solved */
      nlpiterations = SCIPgetNLPIterations(scip);"""))

# ------------------------------------------------------------------ free
STEPS.append(("free", """   /* end diving */
   if( SCIPinDive(scip) )
   {
      SCIP_CALL( SCIPendDive(scip) );
   }""", """   if( fixlpi != NULL )
   {
      SCIPfreeBlockMemoryArray(scip, &fixsol, fixncols);
      SCIPfreeBlockMemoryArray(scip, &fixbd, fixncols);
      SCIPfreeBlockMemoryArray(scip, &fixind, fixncols);
      SCIP_CALL( SCIPlpiFree(&fixlpi) );
   }
   if( cutoffrow != NULL )
   {
      SCIP_CALL( SCIPreleaseRow(scip, &cutoffrow) );
   }

   /* end diving */
   if( SCIPinDive(scip) )
   {
      SCIP_CALL( SCIPendDive(scip) );
   }"""))

# ---------------------------------------------------------------- params
STEPS.append(("params", """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/copycuts",
         "should all active cuts from cutpool be copied to constraints in subproblem?",
         &heurdata->copycuts, TRUE, DEFAULT_COPYCUTS, NULL, NULL) );

   return SCIP_OKAY;""", """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/copycuts",
         "should all active cuts from cutpool be copied to constraints in subproblem?",
         &heurdata->copycuts, TRUE, DEFAULT_COPYCUTS, NULL, NULL) );

   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/cutlam",
         "objective cutoff in the diving LP at zlow + cutlam*(zinc - zlow), following the incumbent; negative: no cutoff",
         &heurdata->cutlam, FALSE, -1.0, -1.0, 1.0, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/tryrounded",
         "should the rounded point be tried as a solution at every pumping round?",
         &heurdata->tryrounded, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/lpfix",
         "should the rounded point be completed on a clone LP (integers fixed, true objective minimised) and tried?",
         &heurdata->lpfix, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/restartonsol",
         "should the pump keep going after the diving LP became integral?",
         &heurdata->restartonsol, FALSE, FALSE, NULL, NULL) );

   return SCIP_OKAY;"""))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    s = io.open(src, encoding="utf-8", errors="surrogateescape").read()
    for what, anchor, new in STEPS:
        n = s.count(anchor)
        if n != 1:
            print(f"ERRORE: ancora '{what}' trovata {n} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    s = NOTICE + s
    io.open(dst, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(s)
    print(f"scritto {dst} ({s.count(chr(10))} righe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
