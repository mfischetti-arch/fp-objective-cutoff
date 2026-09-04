#!/bin/bash
# Ricostruisce TUTTI i binari sperimentali da un sorgente pristino, dopo la
# correzione del 02/09/2026 su SCIPrecomputeSolObj.
#
#     ssh dei 'ssh arrow-16 "bash ~/fpc/scip_build_all.sh"'
#
# ❌ Il difetto corretto (trovato da un audit esterno). Le patch del recupero
# (scip_patch.py), dei contatori (scip_patch_osc.py) e del completamento
# (scip_patch_lpfix.py) costruivano la soluzione da provare con
#     SCIPcreateSolCopy + SCIPunlinkSol + SCIPrecomputeSolObj
# ma SCIPrecomputeSolObj e' una routine per soluzioni ORIGINALI: asserisce
# SCIPsolIsOriginal, itera sulle variabili del problema originale e somma
# l'offset di origprob (sol.c, SCIPsolRecomputeObj). La nostra soluzione vive
# nello spazio TRASFORMATO; in Release l'assert sparisce e il valore memorizzato
# usciva sbagliato ovunque il presolve avesse un offset o dei fissaggi. Esito:
# 205 run su 15 istanze con primal bound SOTTO il bound LP, err=0, e vettori
# perfettamente ammissibili --- era il valore, non il punto.
#
# ✅ La correzione: costruire la soluzione da zero e assegnare ogni valore.
# SCIPsolSetVal mantiene sol->obj da se' con SCIPvarGetUnchangedObj, cioe' il
# coefficiente che il dive NON ha toccato. E' il modo in cui lo fanno le
# euristiche di arrotondamento di SCIP, e non serve nessun recompute.
#
# I binari nuovi hanno nomi NUOVI (suffisso "f" = fixed) apposta: nessun file di
# risultati puo' mescolare per sbaglio una passata vecchia con una nuova.
#
#   bin/scip_f1  = patch + moat + arms + stop + diag           (E1: job11, job18)
#   bin/scip_f2  = f1 + osc                                    (E2 e contatori)
#   bin/scip_f5  = f2 + vcut + rcut + lpfix                    (completamento)
set -e
ROOT=/home/fisch/scipwork
SRC=$ROOT/scip/src/scip/heur_feaspump.c
P=/home/fisch/fpc
run () { scl enable gcc-toolset-13 -- "$@"; }

build () {   # $1 = nome albero, $2 = nome binario
  mkdir -p $ROOT/scip/$1
  cd $ROOT/scip/$1
  run cmake .. -DCMAKE_INSTALL_PREFIX=$ROOT/inst -DCMAKE_BUILD_TYPE=Release \
               -DSOPLEX_DIR=$ROOT/inst -DIPOPT=off -DZIMPL=off -DPAPILO=off \
               -DGMP=off -DREADLINE=off -DBOOST=off -DAMPL=off > /dev/null
  run make -j4 > /dev/null
  cp $ROOT/scip/$1/bin/scip $ROOT/bin/$2
  echo "== $2 pronto"
}

# --------------------------------------------------- sorgente pristino da git
cd $ROOT/scip
git show HEAD:src/scip/heur_feaspump.c > $SRC
grep -q "SCIP_CALL( SCIPrecomputeSolObj" $SRC && { echo "ERRORE: il pristino non e' pristino"; exit 1; }
echo "== sorgente ripristinato da git HEAD ($(wc -l < $SRC) righe)"

# ------------------------------------------------------------------- f1 (E1)
python3 $P/scip_patch.py       $SRC
python3 $P/scip_patch_moat.py  $SRC
python3 $P/scip_patch_arms.py  $SRC
python3 $P/scip_patch_stop.py  $SRC
python3 $P/scip_patch_diag.py  $SRC
! grep -q "SCIP_CALL( SCIPrecomputeSolObj" $SRC || { echo "ERRORE: chiamata a recompute ancora presente in f1"; exit 1; }
build build_f1 scip_f1

# --------------------------------------------------- f2 (E2 e contatori) = +osc
python3 $P/scip_patch_osc.py   $SRC
! grep -q "SCIP_CALL( SCIPrecomputeSolObj" $SRC || { echo "ERRORE: chiamata a recompute ancora presente in f2"; exit 1; }
build build_f2 scip_f2

# ------------------------------------------- f5 (completamento) = +vcut +rcut +lpfix
python3 $P/scip_patch_vcut.py  $SRC
python3 $P/scip_patch_rcut.py  $SRC
python3 $P/scip_patch_lpfix.py $SRC
! grep -q "SCIP_CALL( SCIPrecomputeSolObj" $SRC || { echo "ERRORE: chiamata a recompute ancora presente in f5"; exit 1; }
build build_f5 scip_f5

echo
echo "== controllo dei parametri"
$ROOT/bin/scip_f1 -c "set heuristics feaspump tryrounded TRUE" -c "quit" | tail -1
$ROOT/bin/scip_f2 -c "set heuristics feaspump cutosc 0.8"      -c "quit" | tail -1
$ROOT/bin/scip_f5 -c "set heuristics feaspump lpfix TRUE"      -c "quit" | tail -1
