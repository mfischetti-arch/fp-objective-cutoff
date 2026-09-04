#!/bin/bash
#SBATCH --job-name=fpc_fact
#SBATCH --partition=arrow,razor
#SBATCH --array=0-297%32
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=14G --time=12:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpc/logs/fact_%A_%a.log

# LA CAMPAGNA FATTORIALE (02/09/2026), disegnata sull'audit adversariale esterno
# (AUDIT/audit_adversarial_fpcutoff_v2_MPC.md, §7 e §13). Sostituisce job11 /
# job18 / job16 / job19 come unica campagna del paper.
#
# Che cosa cambia rispetto a prima, punto per punto dell'audit:
#   §4   binario scip_f5 ricostruito da sorgente pristino con la correzione di
#        SCIPrecomputeSolObj (il primale non puo' piu' stare sotto z_LP);
#   §7.1 consegna treatment-blind: OGNI braccio consegna l'iterato intero nel
#        momento in cui appare (contatore ifound), quindi il 2x2 non misura
#        piu' la consegna ma la politica;
#   §7.2 NESSUN filtro basato sull'esito: tutte e 463 le istanze girano tutti
#        i bracci. La corsa `filter` resta, come PILOT INDIPENDENTE (braccio
#        bare a budget ridotto, seme 0) che serve solo a stratificare l'analisi
#        in E1/E2 a posteriori --- non decide piu' chi gira;
#   §7.3 filtro del gap nullo: il byte SOH e' sparito, e comunque non decide
#        niente (si registra, si stratifica dopo);
#   §7.5 ordine dei bracci RANDOMIZZATO per (istanza, seme), stesso binario
#        per tutti, hash del binario nel log;
#   §7.6 il ripiego su c'xhat prima dell'incumbent e' un FATTORE a parte
#        (cutosc=0 e fallback spento nei bracci "puri"; vedi FB sotto);
#   §7.7 costo del completamento: lpfix/lpfixfeas/lpfixinf/nlpiter/nloops per
#        run, e tempo alla prima soluzione;
#   §13A ogni run scrive la sua soluzione migliore in un .sol, validato POI da
#        validate_sols.sh su un SCIP fresco e sul modello ORIGINALE.
#
# Il fattoriale: candidate handling {nessuno, controllo diretto, completamento
# FGL} x cutoff {nessuno, lambda=0.5, lambda=0.95 (= la "moat")} e, come
# sensitivity, lambda in {0.75, 0.90}. Dodici bracci:
#
#   bare       nessun cutoff, nessun recupero        (la FP di SCIP, run fino al TL)
#   cut50      lambda 0.5,   nessun recupero
#   recbare    nessun cutoff, controllo diretto
#   rec50      lambda 0.5,   controllo diretto
#   rec75      lambda 0.75,  controllo diretto        (sensitivity)
#   rec90      lambda 0.90,  controllo diretto        (sensitivity)
#   rec95      lambda 0.95,  controllo diretto        (= moat, senza il nome)
#   recbare_f  nessun cutoff, completamento FGL
#   rec50_f    lambda 0.5,   completamento FGL        (= FGL fedele: cutoff + postprocessing)
#   rec95_f    lambda 0.95,  completamento FGL
#   cut50_fb   lambda 0.5,   nessun recupero, FALLBACK su c'xhat prima dell'incumbent
#   rec50_fb   lambda 0.5,   controllo diretto, idem
#
# TL = 20 * t_LP, limitato a [20, 300] s: ogni istanza riceve un numero
# confrontabile di GIRI della pompa, non di secondi. Il probe che misura t_LP ha
# un limite proprio di TPROBE (600 s di default) e serve solo a quello.
cd /home/fisch/fpc
SCIP=${SCIPBIN:-/home/fisch/scipwork/bin/scip_f5}
I=${SLURM_ARRAY_TASK_ID}
MPS=$(grep -v '^#' ${INST:-inst_wide.txt} | awk -F'\t' 'NR=='$((I+1))' {print $3}')
NAME=$(basename "$MPS" .mps.gz)
SEEDS="${SEEDS:-0 1 2 3 4}"
OUT=out/fact; SETS=sets_f; SOLS=sols/fact
mkdir -p $OUT $SETS $SOLS
echo "== [$I] $NAME  nodo=$(hostname)  $(date)  scip=$(md5sum $SCIP | cut -c1-12)"

# ---------------------------------------------------------------- probe
# Solo il PRIMO LP: separazione spenta (non cambia t_LP ne' z_LP, che sono
# misurati prima di ogni taglio) e time limit proprio. Chi non lo passa esce.
P=$SETS/${NAME}_probe.cmd
{ echo "set limits time ${TPROBE:-600}"; echo ".."
  echo "set limits nodes 1"; echo ".."
  echo "set separating emphasis off"; echo ".."; echo ".."
  echo "set heuristics emphasis off"; echo ".."; echo ".."
  echo "read $MPS"; echo "optimize"; echo "display statistics"; echo "quit"; } > "$P"
$SCIP -b "$P" > $OUT/${NAME}__probe.log 2>&1
TLP=$(grep -m1 'First LP Time' $OUT/${NAME}__probe.log | awk '{print $5}')
ZLP=$(grep -m1 'First LP value' $OUT/${NAME}__probe.log | awk '{print $5}')
# SCIP stampa un TRATTINO, non una stringa vuota, quando il primo LP non e'
# stato risolto entro il limite: va escluso anche quel caso, altrimenti
# l'istanza corre tutti i bracci con z_LP="-" e cade dall'analisi in silenzio.
if [ -z "$TLP" ] || [ -z "$ZLP" ] || [ "$ZLP" = "-" ] || [ "$TLP" = "-" ]; then echo "RES|$NAME|probe|FAIL|rootlp_unsolved_within_${TPROBE:-600}s"; exit 0; fi
TL=$(awk -v t="$TLP" 'BEGIN{v=20*t; if(v<20)v=20; if(v>300)v=300; printf "%d", v}')
TLF=$(awk -v v="$TL" 'BEGIN{printf "%d", (v/2 < 10 ? 10 : v/2)}')   # pilot: meta' del TL, almeno 10 s
echo "== [$I] $NAME  t_LP=$TLP  z_LP=$ZLP  TL=$TL  TL_pilot=$TLF"

# --------------------------------------------- un run: .set + .cmd + esecuzione
# $1 tag  $2 TL  $3 cutlam  $4 tryrounded  $5 lpfix  $6 fallback  $7 seed
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

# ------------------------------------------------ il pilot, registrato e basta
# NON decide chi gira. Serve a stratificare: E1 = il pilot trova una soluzione,
# E2 = non la trova. Braccio bare, seme 0, meta' del budget.
FL=$(one filter "$TLF" -1 FALSE FALSE FALSE 0)
echo "$FL"
# gap di integralita' nullo: si registra, non si scarta (la stratificazione lo
# gestisce a posteriori)
PF=$(echo "$FL" | sed 's/.*|primal=\([^|]*\)|.*/\1/')
if [ -n "$PF" ] && awk -v a="$PF" -v b="$ZLP" 'BEGIN{exit !(a-b < 1e-6 && b-a < 1e-6)}'; then
  echo "NOTE|$NAME|gap di integralita' nullo al nodo radice"
fi

# --------------------------------- i dodici bracci x 5 semi, in ordine RANDOM
#   tag        lam   try   lpfix  fallback
ARMS="bare:-1:FALSE:FALSE:FALSE cut50:0.5:FALSE:FALSE:FALSE recbare:-1:TRUE:FALSE:FALSE
      rec50:0.5:TRUE:FALSE:FALSE rec75:0.75:TRUE:FALSE:FALSE rec90:0.9:TRUE:FALSE:FALSE
      rec95:0.95:TRUE:FALSE:FALSE recbare_f:-1:TRUE:TRUE:FALSE rec50_f:0.5:TRUE:TRUE:FALSE
      rec95_f:0.95:TRUE:TRUE:FALSE cut50_fb:0.5:FALSE:FALSE:TRUE rec50_fb:0.5:TRUE:FALSE:TRUE"
N=0
for SD in $SEEDS; do
  # permutazione deterministica per (istanza, seme): riproducibile, ma diversa da run a run
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
