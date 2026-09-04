#!/usr/bin/env python3
"""
heuristics/feaspump/stopafter: quando il pump esce, si ferma anche SCIP.

    python3 scip_patch_stop.py ~/scipwork/scip/src/scip/heur_feaspump.c

Motivo (MF, 01/09/2026). Con limits/nodes 1 SCIP non si ferma quando il pump
finisce: continua il nodo radice, separa tagli, e quel tempo entra nel primal
integral senza essere lavoro del pump -- e non e' nemmeno detto che la
soluzione finale resti quella del pump. Se il confronto e' FRA EURISTICHE, il
cronometro deve fermarsi quando l'euristica si ferma.

SCIPinterruptSolve fa terminare il solving in modo pulito alla prima occasione
utile, senza uccidere il processo: le statistiche vengono stampate lo stesso.

Idempotente.
"""
import io
import sys

A = """   SCIPdebugMsg(scip, "feasibility pump finished [%d iterations done].\\n", nloops);"""
N = """   SCIPdebugMsg(scip, "feasibility pump finished [%d iterations done].\\n", nloops);

   /* the pump is over: stop the solve here, so that the measured time and the
    * final solution are the pump's and nothing else's
    */
   if( heurdata->stopafter )
   {
      SCIPverbMessage(scip, SCIP_VERBLEVEL_FULL, NULL, "fp_stop: interrupting solve after the pump\\n");
      SCIP_CALL( SCIPinterruptSolve(scip) );
   }"""

A_STRUCT = """   SCIP_Bool             restartonsol;       /**< should the pump keep going after the diving LP became integral? */"""
N_STRUCT = """   SCIP_Bool             restartonsol;       /**< should the pump keep going after the diving LP became integral? */
   SCIP_Bool             stopafter;          /**< should the whole solve stop when the pump is done? */"""

A_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/restartonsol","""
N_PARAM = """   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/stopafter",
         "should the whole solve stop when the pump is done?",
         &heurdata->stopafter, FALSE, FALSE, NULL, NULL) );

   SCIP_CALL( SCIPaddBoolParam(scip, "heuristics/" HEUR_NAME "/restartonsol","""

STEPS = [(A_STRUCT, N_STRUCT, "struct heurdata"),
         (A, N, "interruzione dopo il pump"),
         (A_PARAM, N_PARAM, "parametro")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "stopafter" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "restartonsol" not in s:
        print("ERRORE: applica prima scip_patch_arms.py")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"stopafter applicata a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
