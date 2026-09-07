#!/bin/bash
#SBATCH --job-name=fpc_gs12
#SBATCH --partition=razor
#SBATCH --array=0-59%14
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=12G --time=01:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpc/logs/gs12_%A_%a.log

# Censimento della fascia sui semi 1 e 2 CON il dettaglio per iterazione (.csv).
# Motivo: la posizione nella fascia (Tabella 1, colonne di destra, e Figura 1) era
# misurata sul solo seme 0 (audit avversariale di ChatGPT, rilievo M7); i .csv
# dei semi 1-2 non sono mai stati scritti (job03: --summary-only). Stesso fp.py,
# stessi parametri dei .json esistenti (max-iter 2000, time-limit 120 s, thread 1,
# z_ref trovato dalla fase A della pompa con lo stesso seme), cut_mode=cutoff ai
# tre livelli. Output in out/grid_s12/ e NON in out/grid/ (archiviata il 03/09):
# i .json nuovi si confrontano in locale con fpc/grid/*_s1.json e *_s2.json.
#
# razor --exclusive perche' allgroups e' lenta col fairshare a 0.0025 e arrow e'
# occupata da un collega (04/09 sera); non si misurano tempi. Le tre configurazioni
# di un seme girano IN PARALLELO sulla lama (3 processi su 4 core: efficienza 75%,
# sopra la soglia del 60% della policy DEI); due batch, uno per seme.
#
# ⚠️ CONVENZIONE: fp.py e i nomi dei file usano la VECCHIA convenzione di lambda
# (grid/CONVENZIONE.md): il file lam0.25 e' lambda_v2 = 0.75 (cutoff LASCO) e
# lam0.75 e' lambda_v2 = 0.25 (aggressivo). agg_band.py converte da solo.

source /nfsd/opt/gurobi.env
cd /home/fisch/fpc
PY=./venv/bin/python
I=${SLURM_ARRAY_TASK_ID}
mkdir -p out/grid_s12

MPS=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $3}')
FAM=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $1}')
NAME=$(basename "$MPS" .mps.gz)
echo "== [$I] $FAM/$NAME  nodo=$(hostname)  $(date)"

run () {  # $1 lambda (v1)  $2 seed
  local TAG="${NAME}__cutoff_lam$1_s$2"
  $PY fp.py "$MPS" --cut-mode cutoff --lam "$1" --seed "$2" \
      --threads 1 --max-iter 2000 --time-limit 120 \
      --out "out/grid_s12/$TAG" > "out/grid_s12/$TAG.log" 2>&1
  echo "== $TAG: rc=$? $(ls -la out/grid_s12/$TAG.csv 2>/dev/null | awk '{print $5" byte"}') $(date +%T)"
}

for S in 1 2; do
  run 0.25 $S &
  run 0.5  $S &
  run 0.75 $S &
  wait
done
echo "== [$I] $NAME fatto: $(date)"
