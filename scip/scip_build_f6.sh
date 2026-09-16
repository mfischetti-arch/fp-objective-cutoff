#!/bin/bash
# scip_f6 = scip_f5 + cronometro del completamento (M14 del referee MPC).
#
#     ssh dei 'ssh arrow-16 "nohup bash ~/fpc/scip_build_f6.sh > ~/scipwork/build_f6.log 2>&1 &"'
#
# Worktree NUOVO ~/scipwork/scip_f6 allo stesso commit dba4b2a del paper; dentro
# ci va il sorgente GIA' PATCHATO di scip_f5 (copiato da ~/scipwork/scip, che
# NON si tocca) piu' scip_patch_lpfixtime.py. Stessi flag di scip_build_all.sh.
# Binario NUOVO ~/scipwork/bin/scip_f6; scip_f1/f2/f5 restano quelli del paper.
set -e
ROOT=/home/fisch/scipwork
P=/home/fisch/fpc
WT=$ROOT/scip_f6
run () { scl enable gcc-toolset-13 -- "$@"; }

if [ ! -d $WT ]; then
  cd $ROOT/scip && git worktree add $WT dba4b2a
fi
cd $WT && git log --oneline -1
cp $ROOT/scip/src/scip/heur_feaspump.c $WT/src/scip/heur_feaspump.c
md5sum $ROOT/scip/src/scip/heur_feaspump.c $WT/src/scip/heur_feaspump.c
grep -q nlpfix $WT/src/scip/heur_feaspump.c || { echo "ERRORE: il sorgente copiato non e' quello di f5"; exit 1; }
python3 $P/scip_patch_lpfixtime.py $WT/src/scip/heur_feaspump.c
grep -c lpfixtime $WT/src/scip/heur_feaspump.c

mkdir -p $WT/build_f6
cd $WT/build_f6
run cmake .. -DCMAKE_INSTALL_PREFIX=$ROOT/inst -DCMAKE_BUILD_TYPE=Release \
             -DSOPLEX_DIR=$ROOT/inst -DIPOPT=off -DZIMPL=off -DPAPILO=off \
             -DGMP=off -DREADLINE=off -DBOOST=off -DAMPL=off > cmake_f6.log
run make -j4 > make_f6.log 2>&1
cp $WT/build_f6/bin/scip $ROOT/bin/scip_f6
md5sum $ROOT/bin/scip_f5 $ROOT/bin/scip_f6
$ROOT/bin/scip_f6 -c "set heuristics feaspump lpfix TRUE" -c "quit" | tail -1
echo "== scip_f6 pronto $(date)"
