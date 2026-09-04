#!/bin/bash
# Esperimento "target" su GUROBI + fp_target.py (MF, 03/09/2026). Riscrive su
# codice NOSTRO l'esperimento che job22_target.sh fa dentro SCIP: l'utente ha la
# prima soluzione della pompa pilota, z_inc, e vuole una soluzione di costo
#
#     c'x <= U,     U = z_best + A (z_inc - z_best)     (senso di MINIMO)
#
# con A = 0.5 (meta' della strada verso il miglior valore noto di MIPLIB 2017) o
# A = 0.9. Nessun braccio vede z_best: entra solo attraverso U. TRE bracci:
#
#   naive        il vincolo STATICO c'x <= U e' aggiunto al modello PRIMA e FUORI
#                dalla pompa; poi la pompa pulita di FGL (distanza pura) gira come
#                scatola chiusa sul modello ristretto. Nessun incumbent iniziale:
#                la soluzione del pilota viola il vincolo.
#   test  w=WT   modello ORIGINALE, riga INTERNA c'x <= U' con U' = U - WT(U-z_LP):
#                la riga interna scava la "rounding moat" sotto U e la pompa punta
#                piu' in basso. x^ e' testato contro i vincoli ORIGINALI.
#   completion   come test (con w = WC), ma il recupero e' quello di FGL 2005
#         w=WC   sez. 3.2: fissa le intere a x^ e minimizza c'x sui vincoli
#                ORIGINALI (LP clone senza cutoff). Sulle istanze pure-binarie
#                coincide con test a meno del costo degli LP.
#
# NON esiste piu' il braccio "test w=0": con U' = U la riga interna taglia
# ESATTAMENTE lo stesso poliedro della riga statica di naive e la regola di uscita
# e' la stessa -- era naive lettera per lettera, e spendeva meta' del budget di
# valutazione su un duplicato. NAIVE E' IL PUNTO w=0 della griglia, per test come
# per completion.
#
# U e U' NON si muovono mai durante la corsa (nessun inseguimento dell'incumbent).
# Tutti i bracci escono appena esiste un punto ammissibile per il modello
# ORIGINALE con c'x <= U: l'esito primario e' target_ok, con LA STESSA REGOLA per
# tutti e tre, e il TEMPO speso prima di uscire e' l'altro esito.
#
# ---------------------------------------------------------- COME SI OCCUPA LA LAMA
# La policy di efficienza del DEI cancella d'ufficio i job che tengono la lama
# allocata sotto il 60% di CPU. Un run alla volta a un thread su quattro core
# esclusivi fa il 25%: si viene cancellati. Quindi si va in PARALLELO dentro il
# task, sempre con Threads=1 per run e sempre con la STESSA condizione per tutti
# i bracci -- e' questo, non la sequenzialita', a rendere i tempi confrontabili:
#
#   * i tempi sono misurati con TRE run a un thread SIMULTANEI su una lama
#     esclusiva a 4 core: stessa condizione per i tre bracci, che partono
#     insieme, finiscono nella stessa finestra e si contendono la stessa cache;
#   * il pilota della ricognizione gira con altri tre piloti, e cosi' t_LP -- e
#     il TL = clamp(20 t_LP, 20, 300) che ne deriva -- e' misurato nella stessa
#     condizione in cui gireranno poi i bracci;
#   * in taratura gli 11 run di un seme vanno in lotti di 4.
# Cade con questo la randomizzazione dell'ordine dei bracci: i bracci non hanno
# piu' un ordine, sono simultanei.
# ATTENZIONE alla MEMORIA: --mem=14G resta, ma ora e' per TRE (in taratura
# QUATTRO) processi Gurobi insieme. Sulle istanze grosse -- ds,
# proteindesign121pgb11p9, rmine11, tutte nella lista tune -- il rischio OOM e'
# reale: se un task muore per OOM, alzare --mem o scendere a 2 run in parallelo.
#
# ------------------------------------------------------------------- PROTOCOLLO
# Tre fasi, scelte con PHASE, e OGNUNA HA IL SUO --array, passato sulla riga di
# sbatch (prevale su un eventuale #SBATCH --array, che infatti qui non c'e').
# Le tre righe da lanciare, in quest'ordine:
#
#     sbatch --array=0-107%32 --export=ALL,PHASE=recon job23_gurobi.sh
#     sbatch --array=0-19%20  --export=ALL,PHASE=tune,A=0.5,RUNTAG=50 job23_gurobi.sh
#     sbatch --array=0-409%32 --export=ALL,PHASE=eval,A=0.5,RUNTAG=50,WT=0.10,WC=0.10 job23_gurobi.sh
#
#   PHASE=recon  SOLO il pilota, nessun braccio: dice quante istanze
#                sopravvivono e perche' le altre no, PRIMA di impegnare la
#                campagna. Il task I lavora le righe 4I..4I+3 di TUTTA la lista,
#                quattro istanze in parallelo, ciascuna col suo pilota: 430
#                righe -> 108 task (l'ultimo ne ha due). Il JSON del pilota
#                resta in cache per le fasi successive.
#   PHASE=tune   il task I e' la I-esima riga con set=tune (20 istanze fuori dal
#                Benchmark Set, estratte con seme 4242) -> --array=0-19. Semi
#                10-14, w in WGRID: naive + test x WGRID + completion x WGRID =
#                11 run per seme, in lotti di 4 in parallelo.
#   PHASE=eval   il task I e' la I-esima riga con set=eval -> --array=0-409.
#                Semi 0-4: naive, test w=WT e completion w=WC, i tre IN
#                PARALLELO nello stesso task e quindi sulla stessa lama. WT e WC
#                sono OBBLIGATORI (senza, exit 1). Una sola passata: bracci in
#                sbatch diversi girerebbero su lame diverse
#                (--partition=arrow,razor) e il TEMPO, che e' l'esito primario,
#                sarebbe confondato con la velocita' della lama.
# Un indice fuori intervallo esce con RES|?|FAIL|no_row_<I>.
#
# Come si scelgono WT e WC dalla taratura -- un valore PER BRACCIO:
#   per ciascun braccio (test, completion) e ciascun w della griglia si contano le
#   coppie istanza x seme con target_ok=1 sulle righe set=tune; vince il w col
#   NUMERO MASSIMO di coppie riuscite e, a parita', quello con la MEDIANA di
#   time_to_success piu' bassa. naive e' il candidato w=0 (stesso poliedro, stessa
#   uscita): se batte tutti i w>0 di un braccio, quel braccio non ha fascia e va
#   riportato cosi', invece di scegliere comunque un vincitore fra i soli w>0.
#
# -------------------------------------------------------------- CHECKLIST DEPLOY
#   1. python mk_target23.py > inst_target23.txt          (430 righe di dati)
#   2. rsync verso ~/fpg/ di: fp_target.py, fp.py, mk_target23.py,
#      inst_target23.txt, benchmark-v2.test, miplib2017.solu, job23_gurobi.sh.
#      fp.py SERVE: fp_target.py fa "from fp import violation", e senza il file
#      nella stessa cartella ogni run muore con ImportError PRIMA di scrivere
#      il JSON.
#   3. mkdir -p ~/fpg/logs  PRIMA di sbatch: SLURM apre --output prima che lo
#      script parta, e senza la cartella il task muore senza lasciare traccia.
#   4. gli --array delle tre righe sopra sono dimensionati su 430 righe di dati
#      (20 tune, 410 eval): se la lista cambia vanno rifatti i conti --
#      recon 0-(ceil(N/4)-1), tune 0-(Ntune-1), eval 0-(Neval-1).
#
# Il PILOTA gira DENTRO il task (fp_target.py --mode pilot --pilot-completion,
# cioe' col recupero di FGL sez. 3.2, che massimizza le istanze sopravvissute;
# seme 9999, mai uno dei semi di valutazione 0-4 o di taratura 10-14; 150 s;
# --tlp-max, che fa uscire l'istanza lenta subito dopo il primo LP) e da' z_inc,
# z_LP, t_LP e il senso del modello; da li' escono TL = clamp(20 t_LP, 20, 300) e
# l'eleggibilita' dell'istanza. Il suo JSON sta in out/tgt23pilot/, non dipende
# ne' da A ne' da W, ed e' scritto in modo ATOMICO (su ${PJ}.tmp.$$ e poi mv -f,
# cosi' una fase che parte mentre un'altra scrive non legge mai un file troncato):
# le fasi successive lo riusano, e tutte le passate di un'istanza condividono lo
# stesso TL (PILOT_FORCE=1 lo rifa').
#
# Una riga per run, 21 chiavi dal JSON, SEMPRE le stesse e SEMPRE in quest'ordine
# (anche nel fallback senza JSON, dove le mancanti valgono "-"):
#   RES|<inst>|<mode>|w=|seed=|set=|bench=|a=|U=|Uprime=|zinc=|zlp=|zbest=|tlp=|tl=
#       |success=|target_ok=|validated=|time_to_success=|t_first_feasible=
#       |best_obj=|n_iter=|n_lp=|n_perturb=|n_restart=|n_restart_forced_flip=
#       |n_recovered=|n_completion_lp=|n_completion_infeasible=
#       |n_completion_timelimit=|n_completion_other=|n_bin=|n_cont=|time_total=
#       |status=|error=|rc=|wall=
# zbest e' gia' nel senso di MINIMO del modello convertito (negato se il modello
# era di massimo). L'esito primario e' target_ok = esiste una soluzione
# ammissibile del modello ORIGINALE con c'x <= U; success ne e' ormai una copia
# (prima naive usava un metro suo, piu' largo). validated=1 dice che quel punto
# e' stato RIVALIDATO in modo indipendente: modello riletto dall'MPS, tutte le
# variabili fissate al punto, risolto coi default di Gurobi (FeasibilityTol
# assoluta 1e-6, piu' stretta della tolleranza relativa del test interno). Il suo
# LP sta fuori dal budget e fuori da time_total. n_lp conta i soli LP di
# proiezione RISOLTI (il primo LP sta in tlp) e vale sempre n_lp = n_iter - 1, in
# tutti i modi. n_restart_forced_flip conta i restart che non avrebbero ribaltato
# niente e sono stati forzati a farlo: e' la spia del livelock.
# ATTENZIONE: n_recovered e n_feas NON sono confrontabili fra naive e gli altri
# bracci (per naive contano gli x^ ammissibili per il modello RISTRETTO). Per
# confrontare si usano target_ok e validated.
# n_cont separa il caso pure-binario, dove completion e' per costruzione
# identico a test, dal caso misto, l'unico dove il recupero di FGL puo' fare la
# differenza. wall= sono i secondi di orologio del run, per confrontare il tempo
# dichiarato dal JSON con quello vero -- e, con i run in parallelo, per vedere
# quanto si sono dati fastidio.
#
# Istanze non eleggibili: una riga sola e NUDA, con la diagnostica su una riga "==",
#   RES|<inst>|SKIP|unsupported   fuori perimetro: intere generali, o vincoli
#                                 quadratici/SOS/generali (indicator compresi)
#   RES|<inst>|SKIP|nopilot       il pilota e' andato in fondo senza trovare
#                                 soluzione, oppure il JSON e' assente/troncato o
#                                 non ha il campo maximize (senza il quale zbest
#                                 non verrebbe negato sui modelli di massimo)
#   RES|<inst>|SKIP|slow          t_LP > TLP_MAX (5 s)
#   RES|<inst>|SKIP|at_best       il pilota e' gia' al miglior valore noto
#   RES|<inst>|SKIP|best_below_lp z_best SOTTO il bound LP: i due numeri non si
#                                 riferiscono allo stesso modello (dato sporco,
#                                 es. app2-1, drayage-100-23). U cadrebbe sotto il
#                                 bound, nessuna soluzione con c'x<=U esisterebbe e
#                                 l'istanza entrerebbe nell'aggregato come
#                                 "fallimento di tutti" invece che come dato sporco
#   RES|<inst>|SKIP|zero_gap      |z_inc - z_LP| ~ 0: U' ~ U ~ z_LP, nessuna fascia
# (NB: un errore di SEGNO su un modello di massimo -- zbest non negato -- si
# manifesta come at_best, non come best_below_lp: zbest resterebbe grande e il
# pilota sembrerebbe gia' al meglio. best_below_lp intercetta il caso opposto e i
# .solu sporchi.)
#SBATCH --job-name=fpc_t23
#SBATCH --partition=razor
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=14G --time=10:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpg/logs/t23_%A_%a.log
# LC_ALL=C: i confronti numerici e i printf "%.15g" di awk non devono dipendere
# dal locale -- con la virgola decimale un "0.10" si legge 0 e U' salta.
export LC_ALL=C
source /nfsd/opt/gurobi.env
cd /home/fisch/fpg
PY=${PYBIN:-./venv/bin/python}
LIST=${INST:-inst_target23.txt}
I=${SLURM_ARRAY_TASK_ID}
PHASE=${PHASE:-recon}
A=${A:-0.5}
TLP_MAX=${TLP_MAX:-5}
TLPILOT=${TLPILOT:-150}
PSEED=${PSEED:-9999}
# NPAR = i core della lama: righe per task in recon, run per lotto in tune.
# Cambiarlo cambia anche l'--array della ricognizione (0-(ceil(N/NPAR)-1)).
NPAR=${NPAR:-4}
case "$PHASE" in
  recon|tune|eval) ;;
  *) echo "== [$I] PHASE='$PHASE' sconosciuta: usare recon|tune|eval"; exit 1 ;;
esac

# --- guardie numeriche sui parametri della campagna. Un "0,5", un refuso o un
#     valore fuori intervallo devono fermare il task SUBITO: se passassero, awk
#     leggerebbe "0,5" come 0 e U verrebbe calcolato in silenzio con A=0, cioe'
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
if [ "$PHASE" = "eval" ]; then
  { [ -n "$WT" ] && [ -n "$WC" ]; } || {
    echo "== [$I] PHASE=eval richiede WT e WC, i due w scelti in taratura (uno per braccio)"
    exit 1; }
  num_in "$WT" 0 1 || { echo "== [$I] WT='$WT': serve un numero in [0,1)"; exit 1; }
  num_in "$WC" 0 1 || { echo "== [$I] WC='$WC': serve un numero in [0,1)"; exit 1; }
fi

# RUNTAG distingue campagne con soglie diverse (es. RUNTAG=50 per A=0.5), che
# altrimenti sovrascriverebbero i .json con gli stessi nomi
OUT=out/tgt23${RUNTAG}; PILOUT=out/tgt23pilot
mkdir -p $OUT $PILOUT logs

# --- le righe di QUESTO task, secondo la fase (vedi PROTOCOLLO in testa).
#     tr -d '\r': una lista passata da Windows avrebbe un \r attaccato
#     all'ultimo campo, e il confronto su bench sarebbe sbagliato in silenzio.
CLEAN=$(grep -v '^#' "$LIST" | tr -d '\r')
case "$PHASE" in
  recon) ROWS=$(printf '%s\n' "$CLEAN" | awk -v i="$I" -v p="$NPAR" \
                'NR > p*i && NR <= p*(i+1)') ;;
  tune)  ROWS=$(printf '%s\n' "$CLEAN" | awk -F'\t' -v i="$I" \
                '$1=="tune"{if(++n==i+1) print}') ;;
  eval)  ROWS=$(printf '%s\n' "$CLEAN" | awk -F'\t' -v i="$I" \
                '$1=="eval"{if(++n==i+1) print}') ;;
esac
[ -n "$ROWS" ] || { echo "RES|?|FAIL|no_row_$I"; exit 0; }

# ------------------------------------------------------------------ un run
# $1 mode (naive|test|completion)   $2 w   $3 seed
one () {
  local MODE=$1 W_=$2 SD=$3
  # U' = U - w (U - z_LP), FISSO per tutta la corsa. Per naive non serve (il
  # vincolo statico e' a U) ma si riporta lo stesso per uniformita' della riga.
  local UP=$(awk -v u="$U" -v w="$W_" -v z="$ZLP" 'BEGIN{printf "%.15g", u - w*(u-z)}')
  local TAG=${NAME}__${MODE}_w${W_}_s${SD}
  local J=$OUT/${TAG}.json
  # un .err PER RUN: con i run in parallelo un file condiviso in append
  # mescolerebbe le righe di tre processi. Se resta vuoto (ed e' il caso
  # normale: fp_target.py non stampa piu' nulla per iterazione) si cancella.
  local E=$OUT/${TAG}.err
  local T0=$(date +%s)
  if [ "$MODE" = "naive" ]; then
    $PY fp_target.py "$MPS" --mode naive --U "$U" --time-limit $TL --seed $SD --out "$J" \
        > /dev/null 2> "$E"
  else
    $PY fp_target.py "$MPS" --mode $MODE --U "$U" --Uprime "$UP" --time-limit $TL --seed $SD --out "$J" \
        > /dev/null 2> "$E"
  fi
  local RC=$?
  [ -s "$E" ] || rm -f "$E"
  # target_ok e validated sono gli ESITI da confrontare fra bracci (n_recovered e
  # n_feas NO: per naive contano gli x^ ammissibili per il modello RISTRETTO).
  # n_bin/n_cont separano il caso pure-binario, dove completion e' per
  # costruzione identico a test, dal caso misto.
  local KV=$($PY -c '
import json, sys
K = ["success", "target_ok", "validated", "time_to_success", "t_first_feasible",
     "best_obj", "n_iter", "n_lp", "n_perturb", "n_restart",
     "n_restart_forced_flip", "n_recovered", "n_completion_lp",
     "n_completion_infeasible", "n_completion_timelimit", "n_completion_other",
     "n_bin", "n_cont", "time_total", "status", "error"]
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
  [ -n "$KV" ] || KV="success=0|target_ok=0|validated=-|time_to_success=-|t_first_feasible=-|best_obj=-|n_iter=-|n_lp=-|n_perturb=-|n_restart=-|n_restart_forced_flip=-|n_recovered=-|n_completion_lp=-|n_completion_infeasible=-|n_completion_timelimit=-|n_completion_other=-|n_bin=-|n_cont=-|time_total=-|status=nojson|error=estrazione_fallita"
  echo "RES|$NAME|$MODE|w=$W_|seed=$SD|set=$SET|bench=$BENCH|a=$A|U=$U|Uprime=$UP|zinc=$ZINC|zlp=$ZLP|zbest=$ZB|tlp=$TLP|tl=$TL|$KV|rc=$RC|wall=$(($(date +%s)-T0))"
}

# ---------------------------------------------------------- un lotto parallelo
# Ogni argomento e' un run, "<mode> <w> <seed>". Partono INSIEME (un thread
# ciascuno) e le righe RES escono in ordine deterministico quando sono finiti
# tutti: e' la simultaneita' a mettere i bracci nella stessa condizione, non piu'
# l'ordine randomizzato.
par () {
  local outs=() o spec
  for spec in "$@"; do
    o=$(mktemp "${TMPDIR:-/tmp}/fpc23run.XXXXXX")
    outs+=("$o")
    ( one $spec ) > "$o" 2>&1 &
  done
  wait
  for o in "${outs[@]}"; do cat "$o"; rm -f "$o"; done
}

# ------------------------------------------------------- una riga della lista
# $1 = la riga (campi separati da tab). Pilota, eleggibilita' e -- se non siamo
# in ricognizione -- i bracci. Va SEMPRE chiamata in una subshell: le uscite per
# SKIP sono "exit 0" e devono fermare la riga, non il task.
process_row () {
  local ROW="$1"
  local SET NAME MPS ZBRAW BENCH
  SET=$(printf '%s' "$ROW" | cut -f1);   NAME=$(printf '%s' "$ROW" | cut -f2)
  MPS=$(printf '%s' "$ROW" | cut -f3);   ZBRAW=$(printf '%s' "$ROW" | cut -f4)
  BENCH=$(printf '%s' "$ROW" | cut -f5)
  local PJ PKV PSUCC ZINC ZLP TLP MAXI PSTAT PERR ZB TL U SD W_ SPECS i

  [ -f "$MPS" ] || { echo "RES|$NAME|FAIL|no_mps"; echo "== [$I] $NAME: $MPS assente"; exit 0; }
  echo "== [$I] $NAME set=$SET bench=$BENCH nodo=$(hostname) PHASE=$PHASE A=$A WT=${WT:--} WC=${WC:--} zbest_raw=$ZBRAW $(date)"

  # ------------------------------------------------------------------ pilota
  # seme 9999 (mai uno dei semi 0-4 di valutazione o 10-14 di taratura: una
  # replica non deve ripartire dalla sequenza casuale che ha prodotto z_inc),
  # 150 s, nessun cutoff, recupero di FGL sez. 3.2 (--pilot-completion: senza,
  # il pilota riconosce una soluzione solo testando l'arrotondamento, che sulle
  # istanze con continue e' il recupero debole e puo' svuotare il testbed), e
  # --tlp-max, che fa uscire l'istanza lenta SUBITO DOPO il primo LP invece di
  # spendere l'intero budget per scoprirlo.
  # Il nome del file di cache porta TLPILOT e TLP_MAX: sono i due parametri che
  # cambiano l'esito del pilota, e riusare la cache di una ricognizione fatta
  # con soglie diverse darebbe zinc e TL che non corrispondono a quei valori.
  # Scrittura ATOMICA su .tmp.$$ + mv -f: se una fase parte mentre un'altra sta
  # ancora scrivendo, json.load non deve mai vedere un file troncato (l'istanza
  # uscirebbe come SKIP|nopilot pur essendo eleggibile: perdita silenziosa).
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
  # scrive come status=error con un messaggio che inizia per "skip:". E' una
  # causa DIVERSA dal pilota che non trova soluzione, e va contata a parte.
  case "$PERR" in
    skip:*) skip unsupported "$PERR" ;;
  esac
  # istanza lenta riconosciuta dal pilota stesso dopo il primo LP (--tlp-max)
  [ "$PSTAT" = "slow" ] && skip slow "il solo primo LP costa tlp=${TLP:--} > TLP_MAX=$TLP_MAX"
  # MAXI vuoto = JSON senza il campo "maximize": senza di quello zbest non
  # verrebbe negato sui modelli di massimo, e U sarebbe sbagliato in silenzio
  if [ "$PSUCC" != "1" ] || [ -z "$ZINC" ] || [ -z "$ZLP" ] || [ -z "$TLP" ] || [ -z "$MAXI" ]; then
    skip nopilot "succ=${PSUCC:--} zinc=${ZINC:--} zlp=${ZLP:--} tlp=${TLP:--} maximize=${MAXI:--} pilota=${PSTAT:--}/${PERR:--}"
  fi
  awk -v t="$TLP" -v m="$TLP_MAX" 'BEGIN{exit !(t+0 > m+0)}' \
    && skip slow "tlp=$TLP > TLP_MAX=$TLP_MAX"
  # z_best del .solu NEGATO se il modello era di massimo: fp_target.py converte
  # tutto a minimo e zinc/zlp/U vivono in quel senso
  ZB=$(awk -v z="$ZBRAW" -v m="$MAXI" 'BEGIN{printf "%.15g", (m=="1") ? -z : z}')
  # pilota gia' al miglior valore noto: U non ha senso, l'istanza esce. E' anche
  # la spia di un errore di SEGNO su un modello di massimo: se zbest non venisse
  # negato resterebbe grande, e il pilota sembrerebbe gia' al meglio.
  awk -v zi="$ZINC" -v zb="$ZB" 'BEGIN{z=zb+0; tol=1e-6*(z<0?-z:z); if(tol<1e-6)tol=1e-6; exit !(zi+0 <= z+tol)}' \
    && skip at_best "zinc=$ZINC <= zbest=$ZB (+tol), maximize=$MAXI"
  # z_best SOTTO il bound LP: i due numeri non si riferiscono allo stesso modello
  # (dato sporco: app2-1, drayage-100-23). U cadrebbe sotto il bound, nessuna
  # soluzione con c'x<=U esisterebbe, e l'istanza entrerebbe nell'aggregato come
  # "fallimento di tutti" invece che come dato da buttare (e su test/completion
  # U' scenderebbe sotto z_LP -> LP di proiezione vuoto -> status=error).
  # Va PRIMA del calcolo di U.
  awk -v zb="$ZB" -v zl="$ZLP" 'BEGIN{s=(zl<0?-zl:zl); if(s<1)s=1; exit !(zb+0 < zl+0 - 1e-9*s)}' \
    && skip best_below_lp "zbest=$ZB < zlp=$ZLP (maximize=$MAXI, zbest_raw=$ZBRAW)"
  # gap nullo fra pilota e bound: U' ~ U ~ z_LP, nessuna fascia da scavare
  awk -v zi="$ZINC" -v zl="$ZLP" 'BEGIN{d=zi-zl; if(d<0)d=-d; s=(zi<0?-zi:zi); if(s<1)s=1; exit !(d <= 1e-9*s)}' \
    && skip zero_gap "|zinc-zlp| = |$ZINC - $ZLP| ~ 0"
  TL=$(awk -v t="$TLP" 'BEGIN{v=20*t; if(v<20)v=20; if(v>300)v=300; printf "%d", v}')
  U=$(awk -v zb="$ZB" -v zi="$ZINC" -v a="$A" 'BEGIN{printf "%.15g", zb + a*(zi-zb)}')
  echo "== [$I] $NAME eleggibile: zinc=$ZINC zlp=$ZLP tlp=$TLP maximize=$MAXI zbest=$ZB U=$U TL=$TL"

  # PHASE=recon: la ricognizione finisce qui. Nessun braccio, e il JSON del
  # pilota resta in cache per le fasi tune/eval.
  [ "$PHASE" = "recon" ] && { echo "== [$I] $NAME fine ricognizione $(date)"; exit 0; }

  if [ "$PHASE" = "tune" ]; then
    # TARATURA. naive e' il punto w=0 della griglia -- per test come per
    # completion -- e va eseguito: senza, si potrebbe solo scegliere il migliore
    # fra cinque w>0, mai verificare che UNO di essi batta la fascia nulla, e la
    # valutazione partirebbe da un W arbitrario anche se nessun w>0 aiutasse.
    # 1 + 5 + 5 = 11 run per seme, in LOTTI DI NPAR in parallelo (3 lotti per
    # seme: 4 + 4 + 3), 55 run in tutto.
    for SD in ${SEEDS_TUNE:-10 11 12 13 14}; do
      SPECS=("naive 0 $SD")
      for W_ in ${WGRID:-0.02 0.05 0.10 0.15 0.20}; do
        SPECS+=("test $W_ $SD" "completion $W_ $SD")
      done
      i=0
      while [ $i -lt ${#SPECS[@]} ]; do
        par "${SPECS[@]:$i:$NPAR}"
        i=$((i + NPAR))
      done
    done
  else
    # VALUTAZIONE. I TRE bracci nello STESSO task e IN PARALLELO: stessa lama,
    # stessa finestra temporale, stessa contesa -- la condizione identica che
    # rende confrontabili i tempi, e insieme il 75% di CPU che la policy di
    # efficienza del DEI pretende. Niente piu' ordine randomizzato: non c'e' un
    # ordine, i tre partono insieme.
    for SD in ${SEEDS:-0 1 2 3 4}; do
      par "naive 0 $SD" "test $WT $SD" "completion $WC $SD"
    done
  fi
  echo "== [$I] $NAME fine $(date)"
}

# ------------------------------------------------------------------- dispatch
if [ "$PHASE" = "recon" ]; then
  # NPAR righe per task, i piloti in PARALLELO: cosi' t_LP -- e il
  # TL = clamp(20 t_LP, 20, 300) che ne discende -- e' misurato nella stessa
  # condizione di contesa in cui gireranno poi i bracci. L'output di ogni riga
  # va in un file suo e viene stampato in ordine alla fine: tre processi che
  # scrivono sullo stesso log mescolerebbero le righe.
  OUTS=()
  while IFS= read -r R; do
    [ -n "$R" ] || continue
    O=$(mktemp "${TMPDIR:-/tmp}/fpc23row.XXXXXX")
    OUTS+=("$O")
    ( process_row "$R" ) > "$O" 2>&1 &
  done <<< "$ROWS"
  wait
  for O in "${OUTS[@]}"; do cat "$O"; rm -f "$O"; done
else
  # tune ed eval: una riga sola per task (la selezione l'ha gia' fatta l'awk di
  # sopra). La subshell serve perche' le uscite per SKIP sono "exit 0".
  ( process_row "$ROWS" )
fi
