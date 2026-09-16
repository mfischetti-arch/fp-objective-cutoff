#!/usr/bin/env python3
"""Cronometro del completamento (M14 del referee MPC): quanto tempo di parete
costa il completamento su clone (heuristics/feaspump/lpfix)?

Da applicare al sorgente GIA' PATCHATO di scip_f5 (dopo scip_patch_lpfix.py):
    python3 scip_patch_lpfixtime.py ~/scipwork/scip_f6/src/scip/heur_feaspump.c

Non cambia nessun numero della pompa: aggiunge due SCIP_CLOCK (wall clock, lo
stesso `timing/clocktype` del Solving Time di SCIP) e due campi nella riga
diagnostica `fp_exit:`
    lpfixtime=<s>   TUTTO il lavoro del completamento, giro per giro: cambio dei
                    bound del clone, SCIPlpiSolveDual, lettura della soluzione,
                    costruzione della SCIP_SOL e SCIPtrySol del completamento;
    lpfixbuild=<s>  costruzione del clone (una volta per chiamata della pompa).
I due clock nascono con il clone (quindi non esistono sulle istanze pure, dove
il clone non viene costruito: li' i campi valgono 0.000) e muoiono con esso.
Idempotente: se `lpfixtime` c'e' gia', non fa nulla.
"""
import io
import sys

# --------------------------------------------------------------- 1. include
A_INC = """#include "scip/scip_var.h"
#include "lpi/lpi.h\""""
N_INC = """#include "scip/scip_var.h"
#include "scip/scip_timing.h"
#include "lpi/lpi.h\""""

# ---------------------------------------------------------------- 2. locali
A_LOCAL = """   int fixncols;              /* number of columns of the clone */"""
N_LOCAL = """   int fixncols;              /* number of columns of the clone */
   SCIP_CLOCK* fixclock;      /* wall clock of the completion work, round after round (M14) */
   SCIP_CLOCK* fixbuildclock; /* wall clock of building the clone, once per call (M14) */"""

A_NULL = """   fixn = 0;
   fixncols = 0;"""
N_NULL = """   fixn = 0;
   fixncols = 0;
   fixclock = NULL;
   fixbuildclock = NULL;"""

# ------------------------------------------- 3. costruzione del clone: build clock
A_BUILD = """         SCIP_CALL( SCIPlpiCreate(&fixlpi, SCIPgetMessagehdlr(scip), "fp_fixlp", SCIP_OBJSEN_MINIMIZE) );"""
N_BUILD = """         SCIP_CALL( SCIPcreateClock(scip, &fixclock) );
         SCIP_CALL( SCIPcreateClock(scip, &fixbuildclock) );
         SCIP_CALL( SCIPstartClock(scip, fixbuildclock) );
         SCIP_CALL( SCIPlpiCreate(&fixlpi, SCIPgetMessagehdlr(scip), "fp_fixlp", SCIP_OBJSEN_MINIMIZE) );"""

A_BUILDEND = """   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );"""
N_BUILDEND = """   if( fixbuildclock != NULL )
   {
      SCIP_CALL( SCIPstopClock(scip, fixbuildclock) );
   }

   /* start diving */
   SCIP_CALL( SCIPstartDive(scip) );"""

# --------------------------------------- 4. il completamento, giro per giro
A_ROUND = """         if( fixlpi != NULL )
         {
            SCIP_COL** curcols;
            int ncurcols;
"""
N_ROUND = """         if( fixlpi != NULL )
         {
            SCIP_COL** curcols;
            int ncurcols;

            SCIP_CALL( SCIPstartClock(scip, fixclock) );
"""

A_ROUNDEND = """               else if( SCIPlpiIsPrimalInfeasible(fixlpi) )
                  heurdata->nlpfixinf++;
            }
         }
"""
N_ROUNDEND = """               else if( SCIPlpiIsPrimalInfeasible(fixlpi) )
                  heurdata->nlpfixinf++;
            }
            SCIP_CALL( SCIPstopClock(scip, fixclock) );
         }
"""

# ------------------------------------------------------------ 5. fp_exit
A_FMT = """      " lpfix=%d lpfixfeas=%d lpfixinf=%d ncont=%d fixcols=%d fixint=%d\\n","""
N_FMT = """      " lpfix=%d lpfixfeas=%d lpfixinf=%d ncont=%d fixcols=%d fixint=%d lpfixtime=%.3f lpfixbuild=%.3f\\n","""

A_ARG = """      SCIPgetNContVars(scip) + SCIPgetNContImplVars(scip), fixncols, fixn);"""
N_ARG = """      SCIPgetNContVars(scip) + SCIPgetNContImplVars(scip), fixncols, fixn,
      fixclock != NULL ? SCIPgetClockTime(scip, fixclock) : 0.0,
      fixbuildclock != NULL ? SCIPgetClockTime(scip, fixbuildclock) : 0.0);"""

# --------------------------------------------------------------- 6. free
A_FREE = """      SCIP_CALL( SCIPlpiFree(&fixlpi) );"""
N_FREE = """      SCIP_CALL( SCIPlpiFree(&fixlpi) );
      SCIP_CALL( SCIPfreeClock(scip, &fixclock) );
      SCIP_CALL( SCIPfreeClock(scip, &fixbuildclock) );"""

STEPS = [(A_INC, N_INC, "include scip_timing.h"),
         (A_LOCAL, N_LOCAL, "variabili locali"),
         (A_NULL, N_NULL, "inizializzazione a NULL"),
         (A_BUILD, N_BUILD, "creazione dei clock e avvio del build clock"),
         (A_BUILDEND, N_BUILDEND, "stop del build clock prima di SCIPstartDive"),
         (A_ROUND, N_ROUND, "start del clock a ogni giro"),
         (A_ROUNDEND, N_ROUNDEND, "stop del clock a fine giro"),
         (A_FMT, N_FMT, "formato di fp_exit"),
         (A_ARG, N_ARG, "argomenti di fp_exit"),
         (A_FREE, N_FREE, "free dei clock")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "lpfixtime" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "nlpfix" not in s:
        print("ERRORE: serve il sorgente di scip_f5 (dopo scip_patch_lpfix.py)")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"cronometro del completamento applicato a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
