#!/bin/bash
#SBATCH --job-name=fpc_grid4
#SBATCH --partition=razor
#SBATCH --array=0-59
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=12G --time=02:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpc/logs/g4_%A_%a.log

# Griglia definitiva. Rispetto a job03:
#  - il seed della fase B e' diverso da quello della fase A (altrimenti in
#    modalita' `none` la fase B ripercorre la fase A e non puo' che ritrovare
#    la stessa soluzione: confronto truccato a favore di chi cambia traiettoria)
#  - c'e' la rounding-moat progressiva
#  - time-limit 120 s per run invece di 600: 27 configurazioni x 120 s stanno
#    dentro le 2 ore di walltime, 600 no (in job03 dieci task sono rimasti
#    appesi proprio per questo)
#
# 27 configurazioni per istanza:
#   none        x 3 seed
#   cutoff      x 3 lambda x 3 seed
#   moat        x 3 lambda x 3 seed
#   progressive x 3 seed x 2 larghezze minime di fascia
# Il dettaglio per iterazione si tiene solo per seed 0 e lambda 0.5: serve alle
# figure, non ai 1620 run.

source /nfsd/opt/gurobi.env
cd /home/fisch/fpc
PY=./venv/bin/python
I=${SLURM_ARRAY_TASK_ID}
mkdir -p out/grid

MPS=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $3}')
FAM=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $1}')
NAME=$(basename "$MPS" .mps.gz)
echo "== [$I] $FAM/$NAME  nodo=$(hostname)  $(date)"

run () {  # $1 modo  $2 lambda  $3 seed  $4 wmin
  local TAG="${NAME}__$1_lam$2_s$3${4:+_w$4}"
  local CSV="--summary-only"
  [ "$3" = "0" ] && [ "$2" = "0.5" ] && CSV=""
  $PY fp.py "$MPS" --cut-mode "$1" --lam "$2" --seed "$3" \
      ${4:+--moat-wmin $4} \
      --threads 1 --max-iter 2000 --time-limit 120 \
      --out "out/grid/$TAG" $CSV
}

for S in 0 1 2; do
  run none 0.5 $S
  for L in 0.25 0.5 0.75; do
    run cutoff $L $S
    run moat   $L $S
  done
  for W in 0.05 0.15; do
    run progressive 0.5 $S $W
  done
done
echo "== [$I] $NAME fatto: $(date)"
