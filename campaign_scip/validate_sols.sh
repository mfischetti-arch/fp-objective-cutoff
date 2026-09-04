#!/bin/bash
# Valida OGNI soluzione scritta dalla campagna su un SCIP FRESCO e sul modello
# ORIGINALE, come vuole l'audit (§4.4 punto 4, §13-A punto 3). E' la verifica
# che avrebbe intercettato il bug di SCIPrecomputeSolObj: il vettore era
# ammissibile, il valore no --- e un check indipendente sul modello originale
# confronta il valore ricalcolato con quello che il run ha dichiarato.
#
#     ssh dei 'cd fpc && sbatch validate_sols.sh'          # allgroups, non misura tempi
#
# Ricetta (provata a mano il 02/09 su b-ball, sia con un .sol buono sia con uno
# manomesso): `read mps; read x.sol; set limits nodes 0; optimize`. SCIP accetta
# il .sol come candidato e lo CONTROLLA all'avvio del solve: stampa
#   "1/1 feasible solution given by solution candidate storage, new primal bound X"
# oppure
#   "solution violates original bounds of variable <x15> [0,1] solution value <7>"
#   "all 1 solutions given by solution candidate storage are infeasible".
#
# Per ogni .sol una riga
#   VALID|<istanza>|<braccio>|seed=<s>|feasible=<0/1>|obj=<valore ricalcolato>|claimed=<primal del run>|delta=<obj-claimed>
# e in coda un riepilogo. `delta` deve essere ~0 su ogni riga feasible: se non lo
# e', il run ha dichiarato un valore che non e' quello della sua soluzione.
#SBATCH --job-name=fpc_valid --partition=allgroups --array=0-15
#SBATCH --ntasks=1 --cpus-per-task=1 --mem=8G --time=04:00:00
#SBATCH --output=/home/fisch/fpc/logs/valid_%A_%a.log
cd /home/fisch/fpc
SCIP=${SCIPBIN:-/home/fisch/scipwork/bin/scip_f5}
RES=${RES:-results_fact.txt}
SH=${SLURM_ARRAY_TASK_ID:-0}; NSH=${NSHARD:-16}

n=0
grep "^RES|" "$RES" | grep "|sol=sols/" | while IFS='|' read -r _ NAME TAG SEED rest; do
  n=$((n+1)); [ $((n % NSH)) -eq $SH ] || continue
  # ATTENZIONE: `grep -o 'sol=...'` prende anche il `sol=` dentro `nsol=`, e in
  # questo formato `nsol=` viene PRIMA: il percorso diventava "2" e ogni riga
  # usciva come `missing`. Si spezza sul separatore e si ancora l'inizio campo.
  SOL=$(echo "$rest" | tr '|' '\n' | grep -m1 '^sol=' | cut -d= -f2)
  CLAIM=$(echo "$rest" | tr '|' '\n' | grep -m1 '^primal=' | cut -d= -f2)
  NSOL=$(echo "$rest" | tr '|' '\n' | grep -m1 '^nsol=' | cut -d= -f2)
  # un run senza soluzione scrive comunque un .sol vuoto: niente da validare
  [ "${NSOL:-0}" -gt 0 ] || { echo "VALID|$NAME|$TAG|$SEED|feasible=NA|obj=NA|claimed=$CLAIM|delta=NA|nosol"; continue; }
  MPS=$(grep -v '^#' inst_wide.txt | awk -F'\t' -v n="$NAME" '{split($3,a,"/"); sub(/\.mps\.gz$/,"",a[length(a)]); if(a[length(a)]==n) print $3}' | head -1)
  [ -f "$SOL" ] && [ -n "$MPS" ] || { echo "VALID|$NAME|$TAG|$SEED|feasible=NA|obj=NA|claimed=$CLAIM|delta=NA|missing"; continue; }
  OUT=$($SCIP -c "set limits nodes 0" -c "set display verblevel 4" -c "read $MPS" -c "read $SOL" -c "optimize" -c "quit" 2>&1)
  if echo "$OUT" | grep -q "feasible solution given by solution candidate storage"; then
    OBJ=$(echo "$OUT" | grep -m1 "new primal bound" | grep -o 'primal bound [-+0-9.e]*' | awk '{print $3}')
    # ATTENZIONE: `obj` e' letto dalla riga di display di SCIP, che stampa SEI
    # cifre significative. Su un obiettivo dell'ordine di 1e9 lo scarto assoluto
    # e' dell'ordine di 1e4 per pura arrotondatura di stampa: va letto RELATIVO,
    # ed e' per questo che si emette anche rdelta.
    D=$(awk -v a="$OBJ" -v b="$CLAIM" 'BEGIN{printf "%.6g", a-b}')
    R=$(awk -v a="$OBJ" -v b="$CLAIM" 'BEGIN{m=(a<0?-a:a); n=(b<0?-b:b); if(n>m)m=n; if(m<1)m=1; d=a-b; if(d<0)d=-d; printf "%.3g", d/m}')
    echo "VALID|$NAME|$TAG|$SEED|feasible=1|obj=$OBJ|claimed=$CLAIM|delta=$D|rdelta=$R"
  else
    WHY=$(echo "$OUT" | grep -m1 -iE "violates|infeasible" | cut -c1-90)
    echo "VALID|$NAME|$TAG|$SEED|feasible=0|obj=NA|claimed=$CLAIM|delta=NA|$WHY"
  fi
done
