#!/usr/bin/env python3
"""
Una riga di diagnostica all'uscita del ciclo di pumping.

    python3 scip_patch_diag.py ~/scipwork/scip/src/scip/heur_feaspump.c

Serve a rispondere a una domanda sola: PERCHE' il pump si ferma. Le quattro
condizioni del while (frazionarie, budget di iterazioni LP, numero di giri,
giri di stallo) piu' lo stato dell'LP, che e' l'unica uscita per break.

Stampa a SCIP_VERBLEVEL_FULL, quindi in condizioni normali non si vede: si
accende con "set display verblevel 5". Idempotente.
"""
import io
import sys

A = """   if( nfracs == 0 && !lperror && lpsolstat == SCIP_LPSOLSTAT_OPTIMAL )"""
N = """   SCIPverbMessage(scip, SCIP_VERBLEVEL_FULL, NULL,
      "fp_exit: nloops=%d nfracs=%d nstall=%d/%d nlpiter=%" SCIP_LONGINT_FORMAT "/%" SCIP_LONGINT_FORMAT
      " lperror=%u lpsolstat=%d stopped=%u ifound=%d\\n",
      nloops, nfracs, nstallloops, maxstallloops, heurdata->nlpiterations,
      adjustedMaxNLPIterations(maxnlpiterations, nsolsfound, nstallloops),
      lperror, lpsolstat, SCIPisStopped(scip), heurdata->nintegralfound);

   if( nfracs == 0 && !lperror && lpsolstat == SCIP_LPSOLSTAT_OPTIMAL )"""


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "fp_exit:" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if s.count(A) != 1:
        print(f"ERRORE: ancora trovata {s.count(A)} volte, ne serve 1")
        return 1
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s.replace(A, N, 1))
    print(f"diagnostica applicata a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
