#!/bin/bash
#SBATCH --job-name=fpc_g120
#SBATCH --partition=allgroups
#SBATCH --array=0-59%12
#SBATCH --ntasks=1 --cpus-per-task=1 --mem=8G --time=01:00:00
#SBATCH --output=/home/fisch/fpc/logs/g120_%A_%a.log

# La misura che manca al numero dell'abstract: la POSIZIONE nella fascia agli altri due
# livelli del cutoff. job03_grid.sh teneva il dettaglio per iterazione (.csv) solo per
# seme 0 e lambda 0.5; qui si rifanno, per cut_mode=cutoff e seme 0, le due configurazioni
# lambda 0.25 e 0.75 con il csv acceso. Stesso fp.py, stessi parametri, stessa cartella
# out/grid/ (i .json di sintesi vengono sovrascritti con valori identici: fp.py e'
# deterministico a parita' di seme).
#
# ⚠️ CONVENZIONE: fp.py e i nomi dei file usano la VECCHIA convenzione di lambda
# (grid/CONVENZIONE.md): il file lam0.25 e' lambda_v2 = 0.75 (cutoff LASCO, vicino
# all'incumbent) e lam0.75 e' lambda_v2 = 0.25 (aggressivo). agg_band.py converte da solo.
#
# Un task per istanza (60 righe di inst_list.txt, 58 distinte), ~1 minuto ciascuna con un
# thread: non misura tempi, quindi allgroups e non razor.

source /nfsd/opt/gurobi.env
cd /home/fisch/fpc
PY=./venv/bin/python
I=${SLURM_ARRAY_TASK_ID}
mkdir -p out/grid

MPS=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $3}')
FAM=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $1}')
NAME=$(basename "$MPS" .mps.gz)
echo "== [$I] $FAM/$NAME  nodo=$(hostname)  $(date)"

for LAM in 0.25 0.75; do
  TAG="${NAME}__cutoff_lam${LAM}_s0"
  $PY fp.py "$MPS" --cut-mode cutoff --lam "$LAM" --seed 0 \
      --threads 1 --max-iter 2000 --time-limit 120 --out "out/grid/$TAG"
  echo "== $TAG: $(ls -la out/grid/$TAG.csv 2>/dev/null | awk '{print $5" byte"}')"
done
echo "== [$I] $NAME fatto: $(date)"
