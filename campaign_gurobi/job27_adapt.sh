#!/bin/bash
# Q3 del referee MPC (16/09/2026): la "rounding moat" ADATTIVA, scalata sul
# rounding gap osservato. Runner SLURM modellato su job23_gurobi.sh (fase eval),
# con i bracci letti dall'ambiente. Stesso scenario di E3: pilota in cache
# (out/tgt23pilot, seme 9999, TLPILOT=150, TLP_MAX=5), stesso U = z_best +
# A (z_inc - z_best), stesso TL = clamp(20 t_LP, 20, 300), semi 0-4.
#
# BRACCI (ARMS, separati da spazio, ognuno "<mode>:<w>"):
#   naive:0                 il naive di E3, RIFATTO qui: e' il controllo sulla
#                           stessa lama e nella stessa contesa dei bracci nuovi
#   test:W  completion:W    i bracci di E3 a fascia fissa (solo per la verifica)
#   test-adapt:RULE         fascia adattiva, RULE = freeze | running | abs
#   completion-adapt:RULE   (vedi fp_target.py, docstring in testa)
# Default: "naive:0 test-adapt:freeze completion-adapt:freeze". I bracci di un
# seme partono INSIEME sulla stessa lama (lotti di NPAR = numero di bracci,
# come i tre di job23): stessa condizione, tempi confrontabili, e i 3 run a un
# thread su 4 core danno il 75% di CPU che la policy del DEI pretende.
#
#   sbatch --array=0-133%16 --export=ALL,A=0.5,RUNTAG=50f job27_adapt.sh
#   sbatch --array=0-133%16 --export=ALL,A=0.5,RUNTAG=50r,ARMS="naive:0 test-adapt:running completion-adapt:running" job27_adapt.sh
#   sbatch --array=0-1 --export=ALL,A=0.5,RUNTAG=ver,INST=inst_verify.txt,SEEDS=0,ARMS="naive:0 test:0.02 completion:0.15" job27_adapt.sh
#
# LISTA: INST (default inst_eval134.txt = le 134 righe set=eval di
# inst_target23.txt + inst_target23_extra.txt, colonne set name mps zbest
# bench); il task I e' la I-esima riga con set=eval (indice da 0).
#
# RIGA RES: le stesse 38 chiavi di job23, nello stesso ordine, PIU' in coda le
# chiavi della fascia adattiva ("-" per gli altri bracci):
#   ...|rc=|wall=|adapt=|adapt_k=|n_delta=|moat=|uprime_final=|w_eff=|n_uprime_changes=
# Per i bracci adattivi w= porta la REGOLA (freeze/running) e Uprime= il valore
# di PARTENZA della riga (= U, cioe' w = 0); la riga finale sta in uprime_final
# e w_eff = moat / (U - z_LP) e' la fascia effettiva in unita' di gap.
#SBATCH --job-name=fpc_t27
#SBATCH --partition=razor
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=14G --time=10:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpg/logs/t27_%A_%a.log
export LC_ALL=C
source /nfsd/opt/gurobi.env
cd /home/fisch/fpg
PY=${PYBIN:-./venv/bin/python}
LIST=${INST:-inst_eval134.txt}
I=${SLURM_ARRAY_TASK_ID}
A=${A:-0.5}
TLP_MAX=${TLP_MAX:-5}
TLPILOT=${TLPILOT:-150}
PSEED=${PSEED:-9999}
ADAPT_K=${ADAPT_K:-5}
ARMS=${ARMS:-"naive:0 test-adapt:freeze completion-adapt:freeze"}
SEEDS=${SEEDS:-"0 1 2 3 4"}
read -r -a ARMLIST <<< "$ARMS"
NPAR=${NPAR:-${#ARMLIST[@]}}
[ -n "$RUNTAG" ] || { echo "== [$I] RUNTAG obbligatorio"; exit 1; }

num_in () {   # $1 valore  $2 min  $3 max  $4 "open" se il minimo e' escluso
  awk -v v="$1" -v lo="$2" -v hi="$3" -v op="$4" 'BEGIN{
    if (v !~ /^[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?$/) exit 1
    x = v + 0
    if (op == "open" && x <= lo + 0) exit 1
    if (op != "open" && x <  lo + 0) exit 1
    if (x >= hi + 0) exit 1
    exit 0 }'
}
num_in "$A" 0 1 open || { echo "== [$I] A='$A': serve un numero in (0,1)"; exit 1; }
for ARM in "${ARMLIST[@]}"; do
  M=${ARM%%:*}; W=${ARM#*:}
  case "$M" in
    naive) [ "$W" = "0" ] || { echo "== [$I] braccio $ARM: naive vuole w=0"; exit 1; } ;;
    test|completion) num_in "$W" 0 1 || { echo "== [$I] braccio $ARM: w in [0,1)"; exit 1; } ;;
    test-adapt|completion-adapt)
      case "$W" in freeze|running|abs) ;; *) echo "== [$I] braccio $ARM: regola freeze|running|abs"; exit 1 ;; esac ;;
    *) echo "== [$I] braccio $ARM: modo sconosciuto"; exit 1 ;;
  esac
done

OUT=out/tgt27${RUNTAG}; PILOUT=out/tgt23pilot
mkdir -p $OUT $PILOUT logs

CLEAN=$(grep -v '^#' "$LIST" | tr -d '\r')
ROWS=$(printf '%s\n' "$CLEAN" | awk -F'\t' -v i="$I" '$1=="eval"{if(++n==i+1) print}')
[ -n "$ROWS" ] || { echo "RES|?|FAIL|no_row_$I"; exit 0; }

# ------------------------------------------------------------------ un run
# $1 mode   $2 w (numero, o regola freeze|running per i modi adapt)   $3 seed
one () {
  local MODE=$1 W_=$2 SD=$3
  local UP
  case "$MODE" in
    test|completion)
      UP=$(awk -v u="$U" -v w="$W_" -v z="$ZLP" 'BEGIN{printf "%.15g", u - w*(u-z)}') ;;
    *) UP=$U ;;
  esac
  local TAG=${NAME}__${MODE}_w${W_}_s${SD}
  local J=$OUT/${TAG}.json
  local E=$OUT/${TAG}.err
  local T0=$(date +%s)
  case "$MODE" in
    naive)
      $PY fp_target.py "$MPS" --mode naive --U "$U" --time-limit $TL --seed $SD --out "$J" \
          > /dev/null 2> "$E" ;;
    test|completion)
      $PY fp_target.py "$MPS" --mode $MODE --U "$U" --Uprime "$UP" --time-limit $TL --seed $SD --out "$J" \
          > /dev/null 2> "$E" ;;
    *)
      $PY fp_target.py "$MPS" --mode $MODE --U "$U" --adapt-rule "$W_" --adapt-k $ADAPT_K \
          --time-limit $TL --seed $SD --out "$J" > /dev/null 2> "$E" ;;
  esac
  local RC=$?
  [ -s "$E" ] || rm -f "$E"
  local KV=$($PY -c '
import json, sys
K = ["success", "target_ok", "validated", "time_to_success", "t_first_feasible",
     "best_obj", "n_iter", "n_lp", "n_perturb", "n_restart",
     "n_restart_forced_flip", "n_recovered", "n_completion_lp",
     "n_completion_infeasible", "n_completion_timelimit", "n_completion_other",
     "n_bin", "n_cont", "time_total", "status", "error"]
K2 = ["adapt_rule", "adapt_k", "n_delta", "moat", "uprime_final", "w_eff",
      "n_uprime_changes"]
def g(v):
    if v is None: return "-"
    if isinstance(v, bool): return "1" if v else "0"
    if isinstance(v, float): return "%.15g" % v
    s = str(v).replace("|", "/").replace("\n", " ").replace("\t", " ").strip()
    return s[:200] if s else "-"
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    d = {"success": 0, "target_ok": 0, "status": "nojson", "error": str(e)[:120]}
print("|".join(k + "=" + g(d.get(k)) for k in K) + "|rc=%s|wall=%s|" % (sys.argv[2], sys.argv[3])
      + "|".join(k2 + "=" + g(d.get(k)) for k, k2 in zip(K2, ["adapt"] + K2[1:])))
' "$J" "$RC" "$(($(date +%s)-T0))" 2>/dev/null)
  [ -n "$KV" ] || KV="success=0|target_ok=0|validated=-|time_to_success=-|t_first_feasible=-|best_obj=-|n_iter=-|n_lp=-|n_perturb=-|n_restart=-|n_restart_forced_flip=-|n_recovered=-|n_completion_lp=-|n_completion_infeasible=-|n_completion_timelimit=-|n_completion_other=-|n_bin=-|n_cont=-|time_total=-|status=nojson|error=estrazione_fallita|rc=$RC|wall=$(($(date +%s)-T0))|adapt=-|adapt_k=-|n_delta=-|moat=-|uprime_final=-|w_eff=-|n_uprime_changes=-"
  echo "RES|$NAME|$MODE|w=$W_|seed=$SD|set=$SET|bench=$BENCH|a=$A|U=$U|Uprime=$UP|zinc=$ZINC|zlp=$ZLP|zbest=$ZB|tlp=$TLP|tl=$TL|$KV"
}

par () {
  local outs=() o spec
  for spec in "$@"; do
    o=$(mktemp "${TMPDIR:-/tmp}/fpc27run.XXXXXX")
    outs+=("$o")
    ( one $spec ) > "$o" 2>&1 &
  done
  wait
  for o in "${outs[@]}"; do cat "$o"; rm -f "$o"; done
}

process_row () {
  local ROW="$1"
  local SET NAME MPS ZBRAW BENCH
  SET=$(printf '%s' "$ROW" | cut -f1);   NAME=$(printf '%s' "$ROW" | cut -f2)
  MPS=$(printf '%s' "$ROW" | cut -f3);   ZBRAW=$(printf '%s' "$ROW" | cut -f4)
  BENCH=$(printf '%s' "$ROW" | cut -f5)
  local PJ PKV PSUCC ZINC ZLP TLP MAXI PSTAT PERR ZB TL U SD SPECS i ARM

  [ -f "$MPS" ] || { echo "RES|$NAME|FAIL|no_mps"; echo "== [$I] $NAME: $MPS assente"; exit 0; }
  echo "== [$I] $NAME set=$SET bench=$BENCH nodo=$(hostname) A=$A ARMS=$ARMS ADAPT_K=$ADAPT_K zbest_raw=$ZBRAW $(date)"

  # pilota: stessa cache e stessa logica di job23 (seme 9999, 150 s, completion, tlp-max)
  PJ=$PILOUT/${NAME}__pilot_s${PSEED}_tl${TLPILOT}_tlp${TLP_MAX}.json
  if [ ! -s "$PJ" ] || [ -n "$PILOT_FORCE" ]; then
    echo "== [$I] $NAME pilota (TL=${TLPILOT}s seme=$PSEED --pilot-completion --tlp-max $TLP_MAX) $(date)"
    if $PY fp_target.py "$MPS" --mode pilot --pilot-completion \
           --tlp-max $TLP_MAX --time-limit $TLPILOT --seed $PSEED \
           --out "${PJ}.tmp.$$" > /dev/null 2> "${PJ%.json}.err" \
       && [ -s "${PJ}.tmp.$$" ]; then
      mv -f "${PJ}.tmp.$$" "$PJ"
    else
      rm -f "${PJ}.tmp.$$"
    fi
    [ -s "${PJ%.json}.err" ] || rm -f "${PJ%.json}.err"
  else
    echo "== [$I] $NAME pilota riusato da $PJ"
  fi
  PKV=$($PY -c '
import json, sys
def g(d, k):
    v = d.get(k)
    if v is None: return ""
    if isinstance(v, bool): return "1" if v else "0"
    if isinstance(v, float): return "%.15g" % v
    return str(v).replace("|", "/").replace("\n", " ").replace("\t", " ")
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("||||||pilot_json_illeggibile"); sys.exit(0)
print("|".join([g(d, "success"), g(d, "zinc"), g(d, "zlp"), g(d, "tlp"),
                g(d, "maximize"), g(d, "status"), g(d, "error")]))
' "$PJ" 2>/dev/null)
  IFS='|' read -r PSUCC ZINC ZLP TLP MAXI PSTAT PERR <<< "$PKV"

  skip () { echo "RES|$NAME|SKIP|$1"; echo "== [$I] $NAME SKIP $1: $2"; exit 0; }
  case "$PERR" in
    skip:*) skip unsupported "$PERR" ;;
  esac
  [ "$PSTAT" = "slow" ] && skip slow "il solo primo LP costa tlp=${TLP:--} > TLP_MAX=$TLP_MAX"
  if [ "$PSUCC" != "1" ] || [ -z "$ZINC" ] || [ -z "$ZLP" ] || [ -z "$TLP" ] || [ -z "$MAXI" ]; then
    skip nopilot "succ=${PSUCC:--} zinc=${ZINC:--} zlp=${ZLP:--} tlp=${TLP:--} maximize=${MAXI:--} pilota=${PSTAT:--}/${PERR:--}"
  fi
  awk -v t="$TLP" -v m="$TLP_MAX" 'BEGIN{exit !(t+0 > m+0)}' \
    && skip slow "tlp=$TLP > TLP_MAX=$TLP_MAX"
  ZB=$(awk -v z="$ZBRAW" -v m="$MAXI" 'BEGIN{printf "%.15g", (m=="1") ? -z : z}')
  awk -v zi="$ZINC" -v zb="$ZB" 'BEGIN{z=zb+0; tol=1e-6*(z<0?-z:z); if(tol<1e-6)tol=1e-6; exit !(zi+0 <= z+tol)}' \
    && skip at_best "zinc=$ZINC <= zbest=$ZB (+tol), maximize=$MAXI"
  awk -v zb="$ZB" -v zl="$ZLP" 'BEGIN{s=(zl<0?-zl:zl); if(s<1)s=1; exit !(zb+0 < zl+0 - 1e-9*s)}' \
    && skip best_below_lp "zbest=$ZB < zlp=$ZLP (maximize=$MAXI, zbest_raw=$ZBRAW)"
  awk -v zi="$ZINC" -v zl="$ZLP" 'BEGIN{d=zi-zl; if(d<0)d=-d; s=(zi<0?-zi:zi); if(s<1)s=1; exit !(d <= 1e-9*s)}' \
    && skip zero_gap "|zinc-zlp| = |$ZINC - $ZLP| ~ 0"
  TL=$(awk -v t="$TLP" 'BEGIN{v=20*t; if(v<20)v=20; if(v>300)v=300; printf "%d", v}')
  U=$(awk -v zb="$ZB" -v zi="$ZINC" -v a="$A" 'BEGIN{printf "%.15g", zb + a*(zi-zb)}')
  echo "== [$I] $NAME eleggibile: zinc=$ZINC zlp=$ZLP tlp=$TLP maximize=$MAXI zbest=$ZB U=$U TL=$TL"

  # i bracci di un seme INSIEME (lotti di NPAR), come i tre di job23
  for SD in $SEEDS; do
    SPECS=()
    for ARM in "${ARMLIST[@]}"; do
      SPECS+=("${ARM%%:*} ${ARM#*:} $SD")
    done
    i=0
    while [ $i -lt ${#SPECS[@]} ]; do
      par "${SPECS[@]:$i:$NPAR}"
      i=$((i + NPAR))
    done
  done
  echo "== [$I] $NAME fine $(date)"
}

( process_row "$ROWS" )
