#!/bin/bash
# Compila SCIP + SoPlex da sorgente su arrow-16 (la lama fuori coda: dal login
# non si compila). Serve per modificare heur_feaspump.c e misurare l'effetto.
#
#     ssh dei 'ssh arrow-16 "bash ~/fpc/scip_build.sh"'
#
# gcc di sistema e' un 8.5: si usa gcc-toolset-13 via scl, altrimenti SCIP non
# compila. Build minima: niente IPOPT, ZIMPL, PAPILO, GMP -- non servono per
# un'euristica primale e ognuno di quelli e' una dipendenza in piu' che puo'
# rompere la build.
set -e
ROOT=/home/fisch/scipwork
mkdir -p $ROOT
cd $ROOT

# ⚠️ I commit sono INCHIODATI di proposito, e non e' pedanteria: le patch in
# scip_patch*.py sostituiscono ANCORE TESTUALI dentro heur_feaspump.c. Su un
# master piu' recente quelle righe cambiano, le ancore non fanno piu' match e
# l'artefatto non si ricostruisce. Questi due hash sono l'albero che ha
# prodotto TUTTI i risultati del paper (letti da arrow-16 il 01/09/2026).
SCIP_COMMIT=dba4b2a5653707291e16ddb3cc843c7b872291ba     # 2026-08-24
SOPLEX_COMMIT=f0dbc81b47aa13f5746edd42b80df013257e8b2f   # 2026-08-08

if [ ! -d soplex ]; then
  git clone https://github.com/scipopt/soplex.git
  ( cd soplex && git checkout -q $SOPLEX_COMMIT )
fi
if [ ! -d scip ]; then
  git clone https://github.com/scipopt/scip.git
  ( cd scip && git checkout -q $SCIP_COMMIT )
fi
echo "== soplex $(cd soplex && git rev-parse --short HEAD)  scip $(cd scip && git rev-parse --short HEAD)"

run () { scl enable gcc-toolset-13 -- "$@"; }

echo "== gcc: $(run gcc --version | head -1)"

# --- SoPlex
if [ ! -f $ROOT/inst/lib/libsoplex.a ] && [ ! -f $ROOT/inst/lib64/libsoplex.a ]; then
  mkdir -p soplex/build && cd soplex/build
  run cmake .. -DCMAKE_INSTALL_PREFIX=$ROOT/inst -DCMAKE_BUILD_TYPE=Release \
               -DGMP=off -DBOOST=off -DPAPILO=off -DQUADMATH=off
  run make -j4
  run make install
  cd $ROOT
fi
echo "== soplex ok"

# --- SCIP (baseline, sorgente intatto)
mkdir -p scip/build && cd scip/build
run cmake .. -DCMAKE_INSTALL_PREFIX=$ROOT/inst -DCMAKE_BUILD_TYPE=Release \
             -DSOPLEX_DIR=$ROOT/inst -DIPOPT=off -DZIMPL=off -DPAPILO=off \
             -DGMP=off -DREADLINE=off -DBOOST=off -DAMPL=off
run make -j4
echo "== scip ok: $ROOT/scip/build/bin/scip"
$ROOT/scip/build/bin/scip -c "quit" | head -12
