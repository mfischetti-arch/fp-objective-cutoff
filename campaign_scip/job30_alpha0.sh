#!/bin/bash
#SBATCH --job-name=fpc_a0
#SBATCH --partition=razor
#SBATCH --array=0-175%32
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=14G --time=01:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpc/logs/alpha0_%A_%a.log

# Q2 DEL REFEREE MPC (16/09/2026): il vantaggio del test del punto arrotondato
# senza cutoff (recbare 22-154-0 su bare, E1) e' un effetto di alpha > 0?
#
# Ripete i DUE bracci senza cutoff della campagna fattoriale (job21_factorial.sh)
# con la proiezione pura, heuristics/feaspump/alpha = 0 (alpha parte da alpha e
# viene moltiplicato per objfactor a ogni giro: resta 0), sulle 176 istanze di
# E1 (inst_e1.txt, da mk_inst_e1.py), 5 semi, STESSO binario scip_f5, STESSO
# time limit e STESSO z_LP per istanza della campagna (tl_e1.txt, presi da
# results_fact.txt: il probe del primo LP NON viene rifatto), stessi parametri
# comuni di job21 riga per riga, ordine dei bracci casuale dentro il seme come
# in job21. Le righe RES| hanno lo stesso formato di job21: collect_res.py e
# agg_fact.load le leggono tali e quali (results_alpha0.txt).
#
#   bare       nessun cutoff, nessun recupero        + alpha = 0
#   recbare    nessun cutoff, controllo diretto      + alpha = 0
cd /home/fisch/fpc
SCIP=${SCIPBIN:-/home/fisch/scipwork/bin/scip_f5}
I=${SLURM_ARRAY_TASK_ID}
MPS=$(grep -v '^#' ${INST:-inst_e1.txt} | awk -F'\t' 'NR=='$((I+1))' {print $3}')
NAME=$(basename "$MPS" .mps.gz)
SEEDS="${SEEDS:-0 1 2 3 4}"
OUT=out/alpha0; SETS=sets_a0; SOLS=sols_a0
mkdir -p $OUT $SETS $SOLS
echo "== [$I] $NAME  nodo=$(hostname)  $(date)  scip=$(md5sum $SCIP | cut -c1-12)"

# ------------------------------------------ tl e z_LP: quelli della campagna
TL=$(awk -F'\t' -v n="$NAME" '$1==n {print $2}' ${TLZ:-tl_e1.txt})
ZLP=$(awk -F'\t' -v n="$NAME" '$1==n {print $3}' ${TLZ:-tl_e1.txt})
if [ -z "$TL" ] || [ -z "$ZLP" ]; then echo "RES|$NAME|probe|FAIL|tl_zlp_missing_in_tl_e1"; exit 0; fi
echo "== [$I] $NAME  z_LP=$ZLP  TL=$TL  (da tl_e1.txt)  alpha=0"

# --------------------------------------------- un run: .set + .cmd + esecuzione
# $1 tag  $2 TL  $3 cutlam  $4 tryrounded  $5 lpfix  $6 fallback  $7 seed
# Identico a job21_factorial.sh tranne la riga `heuristics/feaspump/alpha = 0`
# e il `set diffsave`, che scrive i parametri non di default effettivamente
# caricati (per verificare che alpha = 0 sia arrivato a SCIP).
one () {
  local TAG=$1 T=$2 LAM=$3 TRY=$4 LPF=$5 FB=$6 SD=$7
  local S=$SETS/${NAME}_${TAG}_s${SD}.set
  {
    echo "limits/time = $T"
    echo "limits/nodes = 1"
    echo "misc/referencevalue = $ZLP"
    echo "randomization/randomseedshift = $SD"
    echo "heuristics/feaspump/freq = 1"
    echo "heuristics/feaspump/freqofs = 0"
    echo "heuristics/feaspump/maxsols = -1"
    echo "heuristics/feaspump/maxloops = -1"
    echo "heuristics/feaspump/maxstallloops = 1000000"
    echo "heuristics/feaspump/maxlpiterquot = 1000"
    echo "heuristics/feaspump/maxlpiterofs = 10000000"
    echo "heuristics/feaspump/restartonsol = TRUE"
    echo "heuristics/feaspump/stopafter = TRUE"
    echo "heuristics/feaspump/cutlam = $LAM"
    echo "heuristics/feaspump/tryrounded = $TRY"
    echo "heuristics/feaspump/moat = FALSE"
    echo "heuristics/feaspump/cutosc = 0"
    echo "heuristics/feaspump/cutfallback = $FB"
    echo "heuristics/feaspump/lpfix = $LPF"
    echo "heuristics/feaspump/rcut = FALSE"
    echo "heuristics/feaspump/alpha = 0"
    echo "display/verblevel = 5"
  } > "$S"
  local C=$SETS/${NAME}_${TAG}_s${SD}.cmd
  local SOL=$SOLS/${NAME}__${TAG}_s${SD}.sol
  { echo "set heuristics emphasis off"; echo ".."; echo ".."
    echo "set load $S"; echo ".."
    echo "set diffsave $SETS/${NAME}_${TAG}_s${SD}.diff"; echo ".."
    echo "read $MPS"; echo "optimize"; echo "display statistics"
    echo "write solution $SOL"; echo "quit"; } > "$C"

  local L=$OUT/${NAME}__${TAG}_s${SD}.log
  $SCIP -b "$C" > "$L" 2>&1
  local PRI=$(grep -m1 '^  primal-ref' "$L" | awk '{print $3}')
  local PDI=$(grep -m1 '^  primal-dual' "$L" | awk '{print $3}')
  local T2=$(grep -m1 '^Solving Time (sec)' "$L" | sed 's/.*: *//')
  local P2=$(grep -m1 '^Primal Bound' "$L" | sed 's/.*: *//' | awk '{print $1}')
  local NS=$(grep -m1 '^Primal Bound' "$L" | grep -o '([0-9]* solutions)' | tr -dc '0-9')
  local TF=$(grep -m1 '^  First Solution' "$L" | grep -o '[0-9.]* seconds' | tr -d ' seconds')
  local FP=$(grep -m1 '^  feaspump' "$L" | awk '{printf "calls=%s,found=%s", $5, $6}')
  local NL=$(grep -o 'nloops=[0-9]*' "$L" | awk -F= '{s+=$2} END{printf "%d", s}')
  local IT=$(grep -o 'nlpiter=[0-9]*' "$L" | awk -F= '{s+=$2} END{printf "%d", s}')
  local IF=$(grep -o 'ifound=[0-9]*' "$L" | awk -F= '{s+=$2} END{printf "%d", s}')
  local LF=$(grep -o 'lpfix=[0-9]* lpfixfeas=[0-9]* lpfixinf=[0-9]*' "$L" \
             | awk '{for(i=1;i<=3;i++){split($i,a,"=");s[i]+=a[2]}} END{printf "lpfix=%d|lpfixfeas=%d|lpfixinf=%d", s[1], s[2], s[3]}')
  local ER=$(grep -c -E 'ERROR|Assertion' "$L")
  [ -f "$SOL" ] || SOL=none
  echo "RES|$NAME|$TAG|seed=$SD|tl=$T|zlp=$ZLP|print=$PRI|pdint=$PDI|time=$T2|primal=$P2|nsol=${NS:-0}|tfirst=${TF:-none}|$FP|nloops=${NL:-0}|nlpiter=${IT:-0}|ifound=${IF:-0}|${LF:-lpfix=0|lpfixfeas=0|lpfixinf=0}|sol=$SOL|err=$ER"
}

# ------------------------------------ i due bracci x 5 semi, in ordine RANDOM
#   tag        lam   try   lpfix  fallback
ARMS="bare:-1:FALSE:FALSE:FALSE recbare:-1:TRUE:FALSE:FALSE"
N=0
for SD in $SEEDS; do
  # permutazione deterministica per (istanza, seme), come in job21
  ORDER=$(echo $ARMS | tr ' ' '\n' | awk -v s="$NAME$SD" 'BEGIN{srand(length(s)*7919+0)} {print rand()"\t"$0}' | sort | cut -f2)
  for A in $ORDER; do
    IFS=: read TAG LAM TRY LPF FB <<< "$A"
    [ -n "$ARMSEL" ] && ! echo " $ARMSEL " | grep -q " $TAG " && continue
    one "$TAG" "$TL" "$LAM" "$TRY" "$LPF" "$FB" "$SD" &
    N=$((N+1))
    [ $((N % 4)) -eq 0 ] && wait
  done
done
wait
echo "== [$I] $NAME fatto: $(date)"
