#!/bin/bash
#SBATCH --job-name=fpc_grid
#SBATCH --partition=razor
#SBATCH --array=0-59
#SBATCH --ntasks=1 --cpus-per-task=4 --mem=12G --time=02:00:00
#SBATCH --exclusive
#SBATCH --output=/home/fisch/fpc/logs/grid_%A_%a.log

# La griglia: un'istanza per lama, le sue configurazioni in sequenza.
#
# --exclusive e un solo processo per volta: nessun altro tocca cache e banda di
# memoria della lama, quindi i wall-clock sono puliti. E' il motivo per cui si
# usa razor. I 4 core allocati restano in parte fermi (il dual simplex in warm
# start e' seriale, misurato in job02: 1 thread e 4 danno lo stesso tempo), ma i
# task durano un minuto e la policy di efficienza guarda ben altro.
#
# 21 configurazioni per istanza:
#   none   x 3 seed              (lambda non entra nell'ottimizzazione)
#   cutoff x 3 lambda x 3 seed
#   moat   x 3 lambda x 3 seed
# Il dettaglio per iterazione (.csv) si tiene solo per seed 0 e lambda 0.5: e'
# quello che serve alle figure. Per tutto il resto basta il .json di sintesi.

source /nfsd/opt/gurobi.env
cd /home/fisch/fpc
PY=./venv/bin/python
I=${SLURM_ARRAY_TASK_ID}
mkdir -p out/grid

MPS=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $3}')
FAM=$(grep -v '^#' inst_list.txt | awk -F'\t' 'NR=='$((I+1))' {print $1}')
NAME=$(basename "$MPS" .mps.gz)
echo "== [$I] $FAM/$NAME  nodo=$(hostname)  $(date)"

run () {  # $1 modo  $2 lambda  $3 seed
  local TAG="${NAME}__$1_lam$2_s$3"
  local CSV="--summary-only"
  [ "$3" = "0" ] && [ "$2" = "0.5" ] && CSV=""
  $PY fp.py "$MPS" --cut-mode "$1" --lam "$2" --seed "$3" \
      --threads 1 --max-iter 2000 --time-limit 600 \
      --out "out/grid/$TAG" $CSV
}

for S in 0 1 2; do
  run none 0.5 $S
  for L in 0.25 0.5 0.75; do
    run cutoff $L $S
    run moat   $L $S
  done
done
echo "== [$I] $NAME fatto: $(date)"
