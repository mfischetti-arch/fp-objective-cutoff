#!/bin/bash
# job26_react.sh -- campagna REACTIVE CUTOFF PUMP contro la pompa FGL (MF, 06/09/2026).
# Un'istanza per task; TUTTI i bracci dell'istanza girano nello stesso task, in
# lotti di NPAR run a un thread in parallelo sulla stessa lama esclusiva (policy
# DEI: CPU < 60% -> job cancellato; e i tempi si confrontano solo dentro
# l'istanza). Codice: fp_react.py (riusa fp_target.py + fp.py, che devono stare
# nella stessa cartella).
#
# Lista (INST, default inst_react.txt, da mk_react_list.py): colonne tab
#   name  mps  tlp  TL  pilot  n_bin  n_cont  zlp  zinc
# TL = clamp(20 t_LP, 20, 300) dal pilota di E3, uguale per tutti i bracci.
#
# Bracci (ARMS, sigla -> opzioni in opts()):
#   fgl   pompa FGL del pilota (flip + restart casuali)          x SEEDS
#   hyb   guinzaglio down-hold, restart FGL solo all'esaurimento  x SEEDS
#   dh dk uh uk oh ok   react puro, direzione down/up/osc x tenuta hold/kick, gamma 2
#   oh13 ok13           osc hold/kick con gamma 1.3
#   I bracci deterministici girano una volta sola (seme 0, irrilevante).
# I run sono interlacciati (casuale, deterministico, casuale, ...) cosi' ogni
# lotto di 4 mescola i bracci e il confronto primario (fgl vs oh) sta nello
# stesso lotto.
#
#   sbatch --array=0-273%12 job26_react.sh
#   sbatch --array=0-42%8 --export=ALL,INST=inst_react_slow.txt,RUNTAG=slow job26_react.sh
#   smoke: sbatch --array=0-2 --export=ALL,INST=inst_smoke.txt,RUNTAG=smoke job26_react.sh
#
# Una riga RES per run, chiavi dal JSON sempre le stesse e nello stesso ordine
# ("-" dove mancano). Esito primario: success (punto ammissibile del modello
# ORIGINALE, rivalidato: validated=1), poi t_first_feasible e n_iter.
#SBATCH --job-name=fpc_r26
#SBATCH --partition=razor
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=14G --time=03:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpg/logs/r26_%A_%a.log
export LC_ALL=C
source /nfsd/opt/gurobi.env
cd /home/fisch/fpg
PY=${PYBIN:-./venv/bin/python}
LIST=${INST:-inst_react.txt}
I=${SLURM_ARRAY_TASK_ID}
RUNTAG=${RUNTAG:-r1}
NPAR=${NPAR:-4}
SEEDS=${SEEDS:-"0 1 2 3 4"}
ARMS=${ARMS:-"fgl hyb oh ok dh dk uh uk oh13 ok13"}
ARMS=${ARMS//,/ }        # --export=ALL,ARMS=eoh,eoh05,edh : le virgole diventano spazi
OUT=out/react_${RUNTAG}
mkdir -p "$OUT" logs

ROW=$(grep -v '^#' "$LIST" | tr -d '\r' | sed -n "$((I+1))p")
[ -n "$ROW" ] || { echo "RES|?|FAIL|no_row_$I"; exit 0; }
IFS=$'\t' read -r NAME MPS TLP TL PILOT NBIN NCONT ZLP ZINC <<< "$ROW"
[ -f "$MPS" ] || { echo "RES|$NAME|FAIL|no_mps"; echo "== [$I] $NAME: $MPS assente"; exit 0; }
echo "== [$I] $NAME nodo=$(hostname) TL=$TL tlp=$TLP pilot=$PILOT nbin=$NBIN ncont=$NCONT RUNTAG=$RUNTAG $(date)"

opts () {
  case "$1" in
    fgl)  echo "--pump fgl" ;;
    hyb)  echo "--pump hybrid" ;;
    dh)   echo "--pump react --leash down --tenure hold" ;;
    dk)   echo "--pump react --leash down --tenure kick" ;;
    uh)   echo "--pump react --leash up --tenure hold" ;;
    uk)   echo "--pump react --leash up --tenure kick" ;;
    oh)   echo "--pump react --leash osc --tenure hold" ;;
    ok)   echo "--pump react --leash osc --tenure kick" ;;
    oh13) echo "--pump react --leash osc --tenure hold --gamma 1.3" ;;
    ok13) echo "--pump react --leash osc --tenure kick --gamma 1.3" ;;
    eoh)   echo "--pump react --leash osc --tenure hold --every 0.01" ;;
    eoh05) echo "--pump react --leash osc --tenure hold --every 0.05" ;;
    edh)   echo "--pump react --leash down --tenure hold --every 0.01" ;;
    oheq)  echo "--pump react --leash osc --tenure hold --eq" ;;
    fl)    echo "--pump flipleash --leash osc --tenure hold" ;;
    flk)   echo "--pump flipleash --leash osc --tenure kick" ;;
    pf)    echo "--pump portfolio --pf-cap 0.7 --pf-every 0.01 --pf-gate" ;;   # dichiarato (train)
    pf3)   echo "--pump portfolio --pf-cap 0.3 --pf-every 0.01 --pf-gate" ;;   # esplorativo
    ff)    echo "--pump portfolio --pf-cap 0.7 --pf-first fgl" ;;   # CONTROLLO: FGL poi FGL con altro seme
    ff3)   echo "--pump portfolio --pf-cap 0.3 --pf-first fgl" ;;
    alt20)  echo "--pump alternate --alt-k 20 --leash osc --tenure hold --every 0.01" ;;
    alt100) echo "--pump alternate --alt-k 100 --leash osc --tenure hold --every 0.01" ;;
    alth50) echo "--pump alternate --alt-k 50 --alt-keep --leash osc --tenure hold --every 0.01" ;;
    *) return 1 ;;
  esac
}

# ------------------------------------------------------------------ un run
one () {
  local ARM=$1 SD=$2 O TAG J E T0 RC KV
  O=$(opts "$ARM") || { echo "RES|$NAME|$ARM|seed=$SD|FAIL|unknown_arm"; return; }
  TAG=${NAME}__${ARM}_s${SD}; J=$OUT/${TAG}.json; E=$OUT/${TAG}.err
  T0=$(date +%s)
  $PY fp_react.py "$MPS" $O --seed "$SD" --time-limit "$TL" --out "$J" > /dev/null 2> "$E"
  RC=$?
  [ -s "$E" ] || rm -f "$E"
  KV=$($PY - "$J" <<'PYEOF'
import json, sys
K = ["success", "validated", "t_first_feasible", "z_first_feasible", "level_first",
     "best_obj", "n_iter", "n_lp", "n_perturb", "n_restart", "n_pull", "n_exhaust",
     "n_sweep", "n_refine", "n_repeat", "tau_max", "n_feas", "n_recovered",
     "n_completion_lp", "zlp", "zhi", "zhi_unbounded", "c_zero", "thi",
     "time_total", "status", "error"]
def g(v):
    if v is None: return "-"
    if isinstance(v, bool): return "1" if v else "0"
    if isinstance(v, float): return "%.15g" % v
    s = str(v).replace("|", "/").replace("\n", " ").replace("\t", " ").strip()
    return s[:200] if s else "-"
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    d = {"success": 0, "status": "nojson", "error": str(e)[:120]}
print("|".join(k + "=" + g(d.get(k)) for k in K))
PYEOF
)
  [ -n "$KV" ] || KV="success=0|status=nojson|error=estrazione_fallita"
  echo "RES|$NAME|$ARM|seed=$SD|pilot=$PILOT|nbin=$NBIN|ncont=$NCONT|tlp=$TLP|tl=$TL|$KV|rc=$RC|wall=$(($(date +%s)-T0))"
}

# ---------------------------------------------------------- un lotto parallelo
par () {
  local outs=() o spec
  for spec in "$@"; do
    o=$(mktemp "${TMPDIR:-/tmp}/fpc26run.XXXXXX")
    outs+=("$o")
    ( one $spec ) > "$o" 2>&1 &
  done
  wait
  for o in "${outs[@]}"; do cat "$o"; rm -f "$o"; done
}

# ------------------------------------------------ la lista dei run, interlacciata
RAND=(); DET=()
for a in $ARMS; do
  case "$a" in
    fgl|hyb|fl|flk|pf|pf3|ff|ff3|alt*) for s in $SEEDS; do RAND+=("$a $s"); done ;;   # bracci con caso -> semi
    *)              DET+=("$a 0") ;;
  esac
done
RUNS=()
i=0; j=0
while [ $i -lt ${#RAND[@]} ] || [ $j -lt ${#DET[@]} ]; do
  [ $i -lt ${#RAND[@]} ] && { RUNS+=("${RAND[$i]}"); i=$((i+1)); }
  [ $j -lt ${#DET[@]} ]  && { RUNS+=("${DET[$j]}");  j=$((j+1)); }
done
echo "== [$I] ${#RUNS[@]} run in lotti di $NPAR: ${RUNS[*]// /:}"

k=0
while [ $k -lt ${#RUNS[@]} ]; do
  par "${RUNS[@]:$k:$NPAR}"
  k=$((k+NPAR))
done
echo "== [$I] $NAME fine $(date)"
