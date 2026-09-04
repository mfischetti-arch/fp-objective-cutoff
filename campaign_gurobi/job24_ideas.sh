#!/bin/bash
# Esperimento "idee" su GUROBI + fp_target.py --pressure (MF, 04/09/2026).
# Copia adattata di job23_gurobi.sh: STESSO scenario (l'utente ha la prima
# soluzione del pilota, z_inc, e vuole c'x <= U con U = z_best + A(z_inc-z_best)
# nel senso di MINIMO), STESSO pilota e STESSA cache dei piloti; cambia una cosa
# sola, ed e' il punto dell'esperimento:
#
#   la riga interna dell'LP di proiezione NON e' piu' una sola, e non e' piu'
#   per forza c'x <= U'.
#
# L'idea, di MF: quella riga e' INVALIDA per il problema originale e puo'
# permetterselo, perche' il recupero (test diretto di x^ e completamento con le
# intere fissate) lavora sempre sui vincoli ORIGINALI e l'uscita chiede c'x <= U
# su quel modello. Se la riga serve solo a fare PRESSIONE -- verso
# l'integer-feasibility e verso il basso -- allora c'x <= U' e' UNA pressione
# fra tante, e vale la pena provarne altre. Le SPEC sono in fp_target.py
# (--pressure, e la sua docstring le spiega una per una):
#
#   cut:w          la riga di oggi, c'x <= U - w G,  G = U - z_LP
#   reflect:a[:b]  la stessa riga, ADATTIVA: ogni punto ammissibile di valore
#                  v > U (inutile) la fa scendere allo specchio 2U - v
#   lb:k[:grow]    local branching attorno all'incumbent del pilota
#   lbmove:k[:grow]  la stessa palla, ma col CENTRO che insegue il miglior
#                  punto trovato dal recupero (anche se sta sopra U)
#   sgn:w          il cutoff nei soli SEGNI dei costi
#   card:k         meno binarie a 1 di quante ne ha l'incumbent
#   nogood:m       righe tabu sulle ultime m x^ scartate
#
# Un BRACCIO qui e' "<modo>[:<pressure>]", modo in naive|test|completion:
#   naive                                 il termine di paragone di sempre
#   completion:cut:0.05                   il vincitore della campagna a=0.9
#   completion:reflect:0.02+lb:0.1        due pressioni insieme
# Per naive niente pressione (la riga c'x <= U e' statica e sta dentro il
# modello: fp_target.py rifiuta --pressure e la riga RES lo direbbe con
# status=error). I bracci si passano in ARMS, separati da ';'.
#
# ---------------------------------------------------------- COME SI OCCUPA LA LAMA
# Identica a job23: la policy di efficienza del DEI cancella i job che tengono
# la lama sotto il 60% di CPU, quindi i bracci girano in LOTTI DI NPAR=4
# processi simultanei, un thread ciascuno, come la taratura di job23. Tutti i
# bracci di un seme partono nella stessa finestra e si contendono la stessa
# cache: e' questo a rendere confrontabili i tempi. ATTENZIONE alla MEMORIA:
# --mem=14G e' per QUATTRO processi Gurobi insieme.
#
# ------------------------------------------------------------------- PROTOCOLLO
# Una fase sola, un'istanza per task, l'--array sulla riga di lancio:
#
#     sbatch --array=0-127%32 --export=ALL,A=0.9,RUNTAG=ideas job24_ideas.sh
#
# La lista e' ${INST:-inst_ideas.txt}, stesso formato di inst_target23.txt
# (set name mps zbest bench, separati da TAB); il task I lavora la I-esima riga
# di dati, QUALUNQUE sia il suo 'set' -- qui non c'e' taratura da separare, e il
# campo passa dritto nella riga RES. --array = 0-(numero di righe di dati - 1).
# Un indice fuori intervallo esce con RES|?|FAIL|no_row_<I>.
#
# Variabili d'ambiente: A (0.9), RUNTAG (ideas), SEEDS ("0 1 2"), ARMS, NPAR (4),
# INST, TLPILOT (150), TLP_MAX (5), PSEED (9999), PILOT_FORCE, PYBIN.
#
# -------------------------------------------------------------------- IL PILOTA
# Come in job23, e con la STESSA cache (out/tgt23pilot/): stesso seme 9999,
# stesso TLPILOT, stesso TLP_MAX, quindi lo stesso file, riusato fra le due
# campagne. Ma qui il pilota deve produrre anche l'INCUMBENT: fp_target.py
# scrive il punto trovato in <out>.inc accanto al JSON (una riga per binaria a
# 1, con l'indice della variabile nel modello), ed e' quel file che le SPEC
# lb/sgn/card leggono con --incumbent. Se il .inc manca accanto a un JSON di
# cache che dichiara success=1, il pilota va RIFATTO: stesso --out e stesso seme
# 9999, cosi' il JSON viene riscritto identico e il .inc compare. Se invece il
# pilota di cache non aveva trovato niente, l'istanza e' SKIP|nopilot e non si
# rifa' niente (sarebbero 150 s buttati a ogni lancio).
#
# Guardie di eleggibilita' identiche a job23 -- unsupported, nopilot, slow,
# at_best, best_below_lp, zero_gap -- piu' una nuova:
#   RES|<inst>|SKIP|noinc         il pilota dichiara successo ma il .inc non
#                                 c'e' (disco pieno, scrittura fallita): senza
#                                 incumbent i bracci lb/sgn/card partirebbero
#                                 con status=error e avvelenerebbero l'aggregato
# U = zbest + A (zinc - zbest) e TL = clamp(20 t_LP, 20, 300) come in job23.
#
# --------------------------------------------------------------- LA RIGA RES
# Una riga per run, SEMPRE le stesse chiavi e SEMPRE in quest'ordine (anche nel
# fallback senza JSON, dove le mancanti valgono "-"):
#   RES|<inst>|<braccio intero>|w=-|seed=|set=|bench=|a=|U=|Uprime=|zinc=|zlp=
#       |zbest=|tlp=|tl=|<le 21 chiavi di job23>|pressure=|n_uprime_changes=
#       |uprime_final=|n_lb_relax=|n_nogood_added=|n_card_relax=|n_lp_extra=
#       |n_center_moves=|rc=|wall=
# Il braccio intero (p.es. completion:reflect:0.02+lb:0.1) sta nel campo che in
# job23 era il modo: e' la chiave con cui l'aggregatore raggruppa. w= e Uprime=
# valgono "-" perche' qui NON esiste un w unico per la corsa: la riga
# sull'obiettivo, quando c'e', la descrive uprime_final (e reflect la muove).
# L'esito primario resta target_ok, confermato da validated; n_recovered e
# n_feas NON sono confrontabili fra bracci diversi.
#SBATCH --job-name=fpc_t24
#SBATCH --partition=razor
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=14G --time=06:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpg/logs/t24_%A_%a.log
# LC_ALL=C: i confronti numerici e i printf "%.15g" di awk non devono dipendere
# dal locale -- con la virgola decimale un "0.05" si legge 0 e U' salta.
export LC_ALL=C
source /nfsd/opt/gurobi.env
cd /home/fisch/fpg
PY=${PYBIN:-./venv/bin/python}
LIST=${INST:-inst_ideas.txt}
I=${SLURM_ARRAY_TASK_ID}
A=${A:-0.9}
RUNTAG=${RUNTAG:-ideas}
TLP_MAX=${TLP_MAX:-5}
TLPILOT=${TLPILOT:-150}
PSEED=${PSEED:-9999}
# NPAR = i core della lama: quanti bracci girano insieme.
NPAR=${NPAR:-4}
# I BRACCI. Il primo e' il termine di paragone di sempre; il secondo e' la
# fascia che ha vinto ad a=0.9 e fa da secondo metro nell'aggregatore.
ARMS=${ARMS:-"naive;completion:cut:0.05;completion:reflect:0.02;completion:reflect:0.02+lb:0.1;completion:lb:0.1;completion:sgn:0.05;completion:card:0.05;completion:nogood:50;completion:reflect:0.02+nogood:50"}

# --- guardie numeriche sui parametri della campagna. Un "0,9", un refuso o un
#     valore fuori intervallo devono fermare il task SUBITO: se passassero, awk
#     leggerebbe "0,9" come 0 e U verrebbe calcolato in silenzio con A=0, cioe'
#     U = z_best, un bersaglio che non raggiunge nessuno.
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

# --- i bracci, validati PRIMA di spendere il pilota: un modo sbagliato o una
#     pressione su naive devono fermare il task, non produrre 5 righe di
#     status=error che l'aggregatore poi dichiara invariante violata.
OLDIFS=$IFS; IFS=';'; read -r -a ARM_LIST <<< "$ARMS"; IFS=$OLDIFS
[ ${#ARM_LIST[@]} -gt 0 ] || { echo "== [$I] ARMS vuoto"; exit 1; }
for ARM in "${ARM_LIST[@]}"; do
  M=${ARM%%:*}
  case "$M" in
    naive) [ "$M" = "$ARM" ] || { echo "== [$I] braccio '$ARM': naive non ammette pressione (la riga c'x <= U e' statica e sta dentro il modello)"; exit 1; } ;;
    test|completion) ;;
    *) echo "== [$I] braccio '$ARM': modo '$M' sconosciuto (naive|test|completion)"; exit 1 ;;
  esac
done

# RUNTAG distingue campagne diverse, che altrimenti si sovrascriverebbero i
# .json con gli stessi nomi. Il PILOTA sta nella cache di job23: e' lo stesso
# pilota, stesso seme, stessi TLPILOT/TLP_MAX, e non si rifa' due volte.
OUT=out/tgt24${RUNTAG}; PILOUT=out/tgt23pilot
mkdir -p $OUT $PILOUT logs

# --- la riga di QUESTO task. tr -d '\r': una lista passata da Windows avrebbe
#     un \r attaccato all'ultimo campo, e il confronto su bench sarebbe
#     sbagliato in silenzio.
CLEAN=$(grep -v '^#' "$LIST" | tr -d '\r')
ROW=$(printf '%s\n' "$CLEAN" | awk -v i="$I" 'NF && NR==i+1')
[ -n "$ROW" ] || { echo "RES|?|FAIL|no_row_$I"; exit 0; }

# ------------------------------------------------------------------ un run
# $1 = braccio intero (es. completion:reflect:0.02+lb:0.1)   $2 = seme
one () {
  local ARM=$1 SD=$2
  local MODE=${ARM%%:*}
  local PRES=""
  [ "$MODE" = "$ARM" ] || PRES=${ARM#*:}
  # il nome del file non puo' contenere ':' ne' '+' su ogni filesystem
  local SAFE=$(printf '%s' "$ARM" | tr ':+' '__')
  local TAG=${NAME}__${SAFE}_s${SD}
  local J=$OUT/${TAG}.json
  # un .err PER RUN: con i run in parallelo un file condiviso in append
  # mescolerebbe le righe di quattro processi. Se resta vuoto (ed e' il caso
  # normale) si cancella.
  local E=$OUT/${TAG}.err
  local T0=$(date +%s)
  local ARGS=("$MPS" --mode "$MODE" --U "$U" --time-limit $TL --seed $SD --out "$J")
  if [ -n "$PRES" ]; then
    ARGS+=(--pressure "$PRES")
    # --incumbent sempre quando c'e' una pressione: lb e card lo pretendono,
    # sgn lo usa se c'e' (e senza ripiega sul primo arrotondamento), le altre
    # SPEC lo ignorano.
    [ -s "$INC" ] && ARGS+=(--incumbent "$INC")
  fi
  $PY fp_target.py "${ARGS[@]}" > /dev/null 2> "$E"
  local RC=$?
  [ -s "$E" ] || rm -f "$E"
  # le 21 chiavi di job23 PIU' le sette della pressione. Sulle righe dei bracci
  # senza pressione (naive) le sette valgono "-": la chiave non esiste nel JSON,
  # ed e' voluto -- senza --pressure fp_target.py deve scrivere ESATTAMENTE il
  # JSON di prima, cosi' questa campagna e quelle di job23 sono confrontabili.
  local KV=$($PY -c '
import json, sys
K = ["success", "target_ok", "validated", "time_to_success", "t_first_feasible",
     "best_obj", "n_iter", "n_lp", "n_perturb", "n_restart",
     "n_restart_forced_flip", "n_recovered", "n_completion_lp",
     "n_completion_infeasible", "n_completion_timelimit", "n_completion_other",
     "n_bin", "n_cont", "time_total", "status", "error",
     "pressure", "n_uprime_changes", "uprime_final", "n_lb_relax",
     "n_nogood_added", "n_card_relax", "n_lp_extra", "n_center_moves"]
def g(v):
    if v is None: return "-"
    if isinstance(v, bool): return "1" if v else "0"
    if isinstance(v, float): return "%.15g" % v
    s = str(v).replace("|", "/").replace("\n", " ").replace("\t", " ").strip()
    return s[:200] if s else "-"
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    # STESSE chiavi e STESSA arita della riga normale, le mancanti a "-": un
    # parser che conta i campi non deve inciampare sul run andato male
    d = {"success": 0, "target_ok": 0, "status": "nojson", "error": str(e)[:120]}
print("|".join(k + "=" + g(d.get(k)) for k in K))
' "$J" 2>/dev/null)
  [ -n "$KV" ] || KV="success=0|target_ok=0|validated=-|time_to_success=-|t_first_feasible=-|best_obj=-|n_iter=-|n_lp=-|n_perturb=-|n_restart=-|n_restart_forced_flip=-|n_recovered=-|n_completion_lp=-|n_completion_infeasible=-|n_completion_timelimit=-|n_completion_other=-|n_bin=-|n_cont=-|time_total=-|status=nojson|error=estrazione_fallita|pressure=-|n_uprime_changes=-|uprime_final=-|n_lb_relax=-|n_nogood_added=-|n_card_relax=-|n_lp_extra=-|n_center_moves=-"
  echo "RES|$NAME|$ARM|w=-|seed=$SD|set=$SET|bench=$BENCH|a=$A|U=$U|Uprime=-|zinc=$ZINC|zlp=$ZLP|zbest=$ZB|tlp=$TLP|tl=$TL|$KV|rc=$RC|wall=$(($(date +%s)-T0))"
}

# ---------------------------------------------------------- un lotto parallelo
# Ogni argomento e' un run, "<braccio> <seme>". Partono INSIEME (un thread
# ciascuno) e le righe RES escono in ordine deterministico quando sono finiti
# tutti: e' la simultaneita' a mettere i bracci nella stessa condizione.
par () {
  local outs=() o spec
  for spec in "$@"; do
    o=$(mktemp "${TMPDIR:-/tmp}/fpc24run.XXXXXX")
    outs+=("$o")
    ( one $spec ) > "$o" 2>&1 &
  done
  wait
  for o in "${outs[@]}"; do cat "$o"; rm -f "$o"; done
}

# ------------------------------------------------------- una riga della lista
# Va SEMPRE chiamata in una subshell: le uscite per SKIP sono "exit 0" e devono
# fermare la riga, non il task.
process_row () {
  local ROW="$1"
  local SET NAME MPS ZBRAW BENCH
  SET=$(printf '%s' "$ROW" | cut -f1);   NAME=$(printf '%s' "$ROW" | cut -f2)
  MPS=$(printf '%s' "$ROW" | cut -f3);   ZBRAW=$(printf '%s' "$ROW" | cut -f4)
  BENCH=$(printf '%s' "$ROW" | cut -f5)
  local PJ INC NEED PSUCC0 PKV PSUCC ZINC ZLP TLP MAXI PSTAT PERR ZB TL U SD SPECS i

  [ -f "$MPS" ] || { echo "RES|$NAME|FAIL|no_mps"; echo "== [$I] $NAME: $MPS assente"; exit 0; }
  echo "== [$I] $NAME set=$SET bench=$BENCH nodo=$(hostname) A=$A RUNTAG=$RUNTAG zbest_raw=$ZBRAW $(date)"
  echo "== [$I] $NAME bracci: $ARMS"

  # ------------------------------------------------------------------ pilota
  # Stessa cache di job23 (stesso seme, stesso TLPILOT, stesso TLP_MAX: stesso
  # file). Scrittura ATOMICA su .tmp.$$ + mv -f, e il .inc segue il JSON.
  PJ=$PILOUT/${NAME}__pilot_s${PSEED}_tl${TLPILOT}_tlp${TLP_MAX}.json
  INC=${PJ}.inc
  NEED=0
  [ -s "$PJ" ] || NEED=1
  [ -n "$PILOT_FORCE" ] && NEED=1
  if [ "$NEED" = 0 ] && [ ! -s "$INC" ]; then
    # cache di job23, fatta prima che esistesse il .inc: si rifa' il pilota SOLO
    # se aveva trovato qualcosa (altrimenti il .inc non comparirebbe comunque e
    # si butterebbero 150 s a ogni lancio).
    PSUCC0=$($PY -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get("success") or 0)
except Exception: print(0)' "$PJ" 2>/dev/null)
    [ "$PSUCC0" = "1" ] && { NEED=1; echo "== [$I] $NAME pilota da rifare: manca l'incumbent $INC"; }
  fi
  if [ "$NEED" = 1 ]; then
    echo "== [$I] $NAME pilota (TL=${TLPILOT}s seme=$PSEED --pilot-completion --tlp-max $TLP_MAX) $(date)"
    if $PY fp_target.py "$MPS" --mode pilot --pilot-completion \
           --tlp-max $TLP_MAX --time-limit $TLPILOT --seed $PSEED \
           --out "${PJ}.tmp.$$" > /dev/null 2> "${PJ%.json}.err" \
       && [ -s "${PJ}.tmp.$$" ]; then
      # prima il .inc, poi il JSON: chi vede il JSON deve gia' poter contare
      # sull'incumbent, mai il contrario
      [ -s "${PJ}.tmp.$$.inc" ] && mv -f "${PJ}.tmp.$$.inc" "$INC"
      mv -f "${PJ}.tmp.$$" "$PJ"
    fi
    rm -f "${PJ}.tmp.$$" "${PJ}.tmp.$$.inc"
    [ -s "${PJ%.json}.err" ] || rm -f "${PJ%.json}.err"
  else
    echo "== [$I] $NAME pilota riusato da $PJ (incumbent $INC)"
  fi
  # estrazione dal JSON con python, non con grep: i campi sono numeri a 15 cifre
  # e null, e un grep li prenderebbe dalla chiave sbagliata. Separatore "|" e NON
  # tab: il tab e' IFS-whitespace, bash lo collassa e un campo null (zinc del
  # pilota fallito) sfalserebbe tutti i successivi.
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

  # una riga RES|<inst>|SKIP|<motivo> NUDA, la diagnostica su una riga "=="
  skip () { echo "RES|$NAME|SKIP|$1"; echo "== [$I] $NAME SKIP $1: $2"; exit 0; }

  # fuori perimetro (intere generali, quadratici/SOS/generali): fp_target.py lo
  # scrive come status=error con un messaggio che inizia per "skip:".
  case "$PERR" in
    skip:*) skip unsupported "$PERR" ;;
  esac
  [ "$PSTAT" = "slow" ] && skip slow "il solo primo LP costa tlp=${TLP:--} > TLP_MAX=$TLP_MAX"
  # MAXI vuoto = JSON senza il campo "maximize": senza di quello zbest non
  # verrebbe negato sui modelli di massimo, e U sarebbe sbagliato in silenzio
  if [ "$PSUCC" != "1" ] || [ -z "$ZINC" ] || [ -z "$ZLP" ] || [ -z "$TLP" ] || [ -z "$MAXI" ]; then
    skip nopilot "succ=${PSUCC:--} zinc=${ZINC:--} zlp=${ZLP:--} tlp=${TLP:--} maximize=${MAXI:--} pilota=${PSTAT:--}/${PERR:--}"
  fi
  awk -v t="$TLP" -v m="$TLP_MAX" 'BEGIN{exit !(t+0 > m+0)}' \
    && skip slow "tlp=$TLP > TLP_MAX=$TLP_MAX"
  # z_best del .solu NEGATO se il modello era di massimo
  ZB=$(awk -v z="$ZBRAW" -v m="$MAXI" 'BEGIN{printf "%.15g", (m=="1") ? -z : z}')
  awk -v zi="$ZINC" -v zb="$ZB" 'BEGIN{z=zb+0; tol=1e-6*(z<0?-z:z); if(tol<1e-6)tol=1e-6; exit !(zi+0 <= z+tol)}' \
    && skip at_best "zinc=$ZINC <= zbest=$ZB (+tol), maximize=$MAXI"
  awk -v zb="$ZB" -v zl="$ZLP" 'BEGIN{s=(zl<0?-zl:zl); if(s<1)s=1; exit !(zb+0 < zl+0 - 1e-9*s)}' \
    && skip best_below_lp "zbest=$ZB < zlp=$ZLP (maximize=$MAXI, zbest_raw=$ZBRAW)"
  awk -v zi="$ZINC" -v zl="$ZLP" 'BEGIN{d=zi-zl; if(d<0)d=-d; s=(zi<0?-zi:zi); if(s<1)s=1; exit !(d <= 1e-9*s)}' \
    && skip zero_gap "|zinc-zlp| = |$ZINC - $ZLP| ~ 0"
  # l'incumbent: il pilota ha dichiarato successo, quindi il .inc DEVE esserci.
  # Se non c'e' i bracci lb/sgn/card uscirebbero con status=error, e una sola
  # istanza cosi' fa dichiarare all'aggregatore "invarianti violate".
  [ -s "$INC" ] || skip noinc "il pilota dichiara successo ma $INC non c'e' (scrittura fallita?)"
  TL=$(awk -v t="$TLP" 'BEGIN{v=20*t; if(v<20)v=20; if(v>300)v=300; printf "%d", v}')
  U=$(awk -v zb="$ZB" -v zi="$ZINC" -v a="$A" 'BEGIN{printf "%.15g", zb + a*(zi-zb)}')
  echo "== [$I] $NAME eleggibile: zinc=$ZINC zlp=$ZLP tlp=$TLP maximize=$MAXI zbest=$ZB U=$U TL=$TL"

  # ------------------------------------------------------------------ i bracci
  # Per ogni seme, tutti i bracci in lotti di NPAR simultanei. Dentro un lotto
  # la condizione e' identica per tutti; fra un lotto e l'altro c'e' un wait.
  for SD in ${SEEDS:-0 1 2}; do
    SPECS=()
    for ARM in "${ARM_LIST[@]}"; do SPECS+=("$ARM $SD"); done
    i=0
    while [ $i -lt ${#SPECS[@]} ]; do
      par "${SPECS[@]:$i:$NPAR}"
      i=$((i + NPAR))
    done
  done
  echo "== [$I] $NAME fine $(date)"
}

( process_row "$ROW" )
