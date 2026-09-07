# grid_s12/ — censimento della fascia sui semi 1 e 2, con i CSV per giro

Prodotto da `job25_grid_s12.sh` (job 4939591, razor, 04/09/2026, 60 task, 3 run in parallelo per
lama) con il `fp.py` del 03/09 (commit del repo), `--cut-mode cutoff`, `--max-iter 2000`,
`--time-limit 120`, `--threads 1`, semi 1 e 2, tre livelli. 37 istanze producono csv+json
(222+222 file); per le altre la fase A non trova una prima soluzione (`no_firstsol`) o il gap
di integralità è nullo (`[skip]`), come nei dati originali. Un `.log` per run (stdout di fp.py).

⚠️ **Convenzione dei nomi: v2** (`lam=1` → cutoff all'incumbent), perché `fp.py` è passato alla
v2 il 01/09 e sul cluster è stato aggiornato il 03/09; i json hanno `lam_conv: "v2"`. La cartella
`grid/` (seme 0 e i json dei semi 1–2 di job03/job20) è invece nominata in **v1**: lo stesso
livello sta in `grid/*lam0.25*` e in `grid_s12/*lam0.75*`. Verificato sui json con
`(ub − z_lp)/(z_ref − z_lp)`: 0.75 in `grid/*lam0.25*`, 0.25 in `grid_s12/*lam0.25*`.
`agg_band_seeds.py` fa la conversione (`lam_file`); `agg_band.py` legge questi json in v2 grazie
al campo `lam_conv`, ma seleziona i **csv per nome**, quindi non va puntato qui senza convertire.

Lettura: `python agg_band_seeds.py` (posizioni per seme e per istanza sui tre semi, confronto
dei json con `grid/`), `--dump ../paper/band_positions_3seeds.csv` per la Figura 1 a tre semi.
