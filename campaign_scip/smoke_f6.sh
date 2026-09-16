#!/bin/bash
# Il cronometro non deve cambiare nulla: scip_f6 contro scip_f5 con lo STESSO
# .set su due istanze MISTE piccole di E1, in modo deterministico (maxloops
# fissato invece del time limit, che dipende dall'orologio). Confronta la riga
# fp_exit (senza i due campi nuovi), Primal Bound, il conteggio delle soluzioni
# e la riga feaspump delle statistiche: devono coincidere byte per byte.
#
#     ssh dei 'ssh arrow-16 "bash ~/fpc/smoke_f6.sh"'
cd /home/fisch/fpc
D=_smoke_f6; mkdir -p $D
F5=/home/fisch/scipwork/bin/scip_f5
F6=/home/fisch/scipwork/bin/scip_f6
echo "f5 $(md5sum $F5 | cut -c1-12)  f6 $(md5sum $F6 | cut -c1-12)"
FAIL=0
for INST in assign1-5-8 mad; do
  MPS=/nfsd/rop/instances/miplib2017/$INST.mps.gz
  ZLP=$(awk -F'\t' -v n="$INST" '$1==n {print $3}' tl_e1.txt)
  for ARM in recbare_f:-1 rec50_f:0.5; do
    TAG=${ARM%%:*}; LAM=${ARM##*:}
    S=$D/${INST}_${TAG}.set
    { echo "limits/time = 600"; echo "limits/nodes = 1"; echo "misc/referencevalue = $ZLP"
      echo "randomization/randomseedshift = 0"
      echo "heuristics/feaspump/freq = 1"; echo "heuristics/feaspump/freqofs = 0"
      echo "heuristics/feaspump/maxsols = -1"; echo "heuristics/feaspump/maxloops = 200"
      echo "heuristics/feaspump/maxstallloops = 1000000"; echo "heuristics/feaspump/maxlpiterquot = 1000"
      echo "heuristics/feaspump/maxlpiterofs = 10000000"; echo "heuristics/feaspump/restartonsol = TRUE"
      echo "heuristics/feaspump/stopafter = TRUE"; echo "heuristics/feaspump/cutlam = $LAM"
      echo "heuristics/feaspump/tryrounded = TRUE"; echo "heuristics/feaspump/moat = FALSE"
      echo "heuristics/feaspump/cutosc = 0"; echo "heuristics/feaspump/cutfallback = FALSE"
      echo "heuristics/feaspump/lpfix = TRUE"; echo "heuristics/feaspump/rcut = FALSE"
      echo "display/verblevel = 5"; } > $S
    C=$D/${INST}_${TAG}.cmd
    { echo "set heuristics emphasis off"; echo ".."; echo ".."; echo "set load $S"; echo ".."
      echo "read $MPS"; echo "optimize"; echo "display statistics"; echo "quit"; } > $C
    for B in f5 f6; do
      BIN=$F5; [ $B = f6 ] && BIN=$F6
      L=$D/${INST}_${TAG}_$B.log
      $BIN -b $C > $L 2>&1
      { grep 'fp_exit' $L | sed 's/ lpfixtime=[0-9.]*//; s/ lpfixbuild=[0-9.]*//'
        grep -m1 '^Primal Bound' $L; grep -m1 '^  feaspump' $L | awk '{print "feaspump calls="$5" found="$6}'
        grep -m1 '^Solving Nodes' $L; } > $D/${INST}_${TAG}_$B.key
      # il primal integral dipende dall'orologio, non dalla pompa: si stampa a parte
      echo "   $B $(grep -m1 '^  primal-ref' $L | tr -s ' ')  $(grep -m1 '^Solving Time' $L | tr -s ' ')"
    done
    echo "== $INST $TAG"
    grep -o 'lpfix=[0-9]* lpfixfeas=[0-9]* lpfixinf=[0-9]*.*' $D/${INST}_${TAG}_f6.log | head -1
    if diff $D/${INST}_${TAG}_f5.key $D/${INST}_${TAG}_f6.key > /dev/null; then
      echo "IDENTICI: $(grep -c . $D/${INST}_${TAG}_f5.key) righe chiave"; cat $D/${INST}_${TAG}_f5.key | cut -c1-200
    else
      echo "DIVERSI"; diff $D/${INST}_${TAG}_f5.key $D/${INST}_${TAG}_f6.key; FAIL=1
    fi
  done
done
echo "esito: $([ $FAIL = 0 ] && echo OK || echo FAIL)"
