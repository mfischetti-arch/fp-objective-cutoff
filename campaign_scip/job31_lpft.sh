#!/bin/bash
#SBATCH --job-name=fpc_lpft
#SBATCH --partition=razor
#SBATCH --array=0-175%32
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=14G --time=01:30:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpc/logs/lpft_%A_%a.log

# M14 DEL REFEREE MPC (16/09/2026): quanto tempo di parete costa il
# completamento su clone (lpfix: LP con le intere fissate, c'x minimizzato)?
#
# Ripete i TRE bracci con completamento della campagna fattoriale
# (job21_factorial.sh) con il binario scip_f6 = sorgente di scip_f5 + un
# cronometro (scip_patch_lpfixtime.py) che stampa in `fp_exit:` due campi:
#   lpfixtime  = tutto il lavoro del completamento, giro per giro (bound del
#                clone, SCIPlpiSolveDual, lettura, costruzione della SCIP_SOL,
#                SCIPtrySol);
#   lpfixbuild = costruzione del clone, una volta per chiamata della pompa.
# Sulle 176 istanze di E1 (inst_e1.txt), 5 semi, STESSO time limit e STESSO
# z_LP per istanza della campagna (tl_e1.txt: il probe non viene rifatto),
# stessi parametri comuni di job21 riga per riga, ordine casuale dei bracci
# dentro il seme come in job21. La riga RES| ha il formato di job21 piu' due
# campi in coda, lpfixtime= e lpfixbuild= (somme sulle chiamate della pompa,
# come nloops/nlpiter): collect_res.py e agg_fact.load la leggono comunque,
# agg_lpft.py legge i campi nuovi.
#
#   recbare_f  nessun cutoff, completamento FGL
#   rec50_f    lambda 0.5,   completamento FGL
#   rec95_f    lambda 0.95,  completamento FGL
cd /home/fisch/fpc
SCIP=${SCIPBIN:-/home/fisch/scipwork/bin/scip_f6}
I=${SLURM_ARRAY_TASK_ID}
MPS=$(grep -v '^#' ${INST:-inst_e1.txt} | awk -F'\t' 'NR=='$((I+1))' {print $3}')
NAME=$(basename "$MPS" .mps.gz)
SEEDS="${SEEDS:-0 1 2 3 4}"
OUT=out/lpft; SETS=sets_lpft; SOLS=sols_lpft
mkdir -p $OUT $SETS $SOLS
echo "== [$I] $NAME  nodo=$(hostname)  $(date)  scip=$(md5sum $SCIP | cut -c1-12)"

# ------------------------------------------ tl e z_LP: quelli della campagna
TL=$(awk -F'\t' -v n="$NAME" '$1==n {print $2}' ${TLZ:-tl_e1.txt})
ZLP=$(awk -F'\t' -v n="$NAME" '$1==n {print $3}' ${TLZ:-tl_e1.txt})
if [ -z "$TL" ] || [ -z "$ZLP" ]; then echo "RES|$NAME|probe|FAIL|tl_zlp_missing_in_tl_e1"; exit 0; fi
echo "== [$I] $NAME  z_LP=$ZLP  TL=$TL  (da tl_e1.txt)"

# --------------------------------------------- un run: .set + .cmd + esecuzione
# $1 tag  $2 TL  $3 cutlam  $4 tryrounded  $5 lpfix  $6 fallback  $7 seed
# Identico a job21_factorial.sh tranne il `set diffsave` (parametri non di
# default caricati davvero) e i due campi in coda alla riga RES|.
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
  local LT=$(grep -o 'lpfixtime=[0-9.]*' "$L" | awk -F= '{s+=$2} END{printf "%.3f", s}')
  local LB=$(grep -o 'lpfixbuild=[0-9.]*' "$L" | awk -F= '{s+=$2} END{printf "%.3f", s}')
  local ER=$(grep -c -E 'ERROR|Assertion' "$L")
  [ -f "$SOL" ] || SOL=none
  echo "RES|$NAME|$TAG|seed=$SD|tl=$T|zlp=$ZLP|print=$PRI|pdint=$PDI|time=$T2|primal=$P2|nsol=${NS:-0}|tfirst=${TF:-none}|$FP|nloops=${NL:-0}|nlpiter=${IT:-0}|ifound=${IF:-0}|${LF:-lpfix=0|lpfixfeas=0|lpfixinf=0}|sol=$SOL|err=$ER|lpfixtime=${LT:-0.000}|lpfixbuild=${LB:-0.000}"
}

# ------------------------------------ i tre bracci x 5 semi, in ordine RANDOM
#   tag        lam   try   lpfix  fallback
ARMS="recbare_f:-1:TRUE:TRUE:FALSE rec50_f:0.5:TRUE:TRUE:FALSE rec95_f:0.95:TRUE:TRUE:FALSE"
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
