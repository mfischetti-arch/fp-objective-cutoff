# `prototype/` — the from-scratch pump of Section 2 (Table 1 and Figure 1)

Section 2 does not measure a solver: it measures the **phenomenon**. A
feasibility pump written from scratch on top of Gurobi's LP solver, instrumented
so that at every iteration it records where the rounded point x̂ falls with
respect to the objective cutoff U, and in particular how many x̂ are **feasible
for the original problem and better than the incumbent** and are nevertheless
thrown away because they sit above U.

The whole point of the measurement is that **the cutoff never enters the
feasibility test**: `feas = 1` means `viol_max ≤ feas_tol` (10⁻⁶) on the
original constraints, cutoff excluded.

## What is here

| file | role |
|---|---|
| `fp.py` | the instrumented from-scratch pump (FGL 2005 objective term, FP 2.0 perturbation and restart, Achterberg-Berthold geometric α, both terms normalised in the Euclidean norm) |
| `agg_band.py` | the aggregator: the three tables on the band between the cutoff and the incumbent |
| `inst_list.txt` | the 37 instances, one per line: `family ⟨tab⟩ size band ⟨tab⟩ path ⟨tab⟩ n ⟨tab⟩ ncons ⟨tab⟩ nnz` |
| `grid/` | **the raw runs**: 999 `.json` (one per run) and 259 `.csv` (one per iteration trace), ~65 MB |

The grid covers three families — OR-Library set covering, MIPLIB 2003, MIPLIB
2017 — three cutoff levels and three seeds, all at a 120 s limit. `agg_band.py`
reads the family of an instance from `inst_list.txt` (field 0 keyed on the
basename of field 2), so that file is required even though it is only metadata.

## Regenerating Table 1 and Figure 1

```bash
python agg_band.py                        # Markdown, the default definition
python agg_band.py --latex                # booktabs bodies, pasted into the manuscript
python agg_band.py --band-lam 0.25        # the extra column at lambda_v2 = 0.75
python agg_band.py --band-lam 0.75        # the extra column at lambda_v2 = 0.25
python agg_band.py --hist --dump band_positions.csv   # the input of the figure
```

then, for the figure itself:

```bash
cd ../paper && python figs_v2.py          # reads band_positions.csv -> fig5_band.pdf
```

The copy of `band_positions.csv` shipped in `paper/` is byte-identical to the one
this command produces.

⚠️ **λ convention.** The files in `grid/` were written in the **v1** convention
(λ weighted z_LP); the paper uses **v2** (λ = 1 → U at the incumbent, λ = 0 → U
at z_LP). `agg_band.py` converts on the fly for every `.json` without a
`"lam_conv": "v2"` field, but **`--band-lam` takes the v1 value, the one in the
file name**: `--band-lam 0.25` means λ_v2 = 0.75 (the loose cutoff) and
`--band-lam 0.75` means λ_v2 = 0.25. The tables it prints are already labelled
in v2.

## What the aggregator prints

* **A** — how large the loss is: the fraction `n_killed / n_feas` of feasible
  roundings that the cutoff discards, per family and per λ. Median over seeds
  inside an instance, then over instances; instances with `n_feas = 0` are
  counted apart in the *escluse* column, never silently dropped.
* **B** — **where** the lost points fall inside the band `[U, z_inc]`:
  `pos = (cᵀx̂ − U)/(z_inc − U)`, 0 meaning "resting on the cutoff", 1 meaning
  "resting on the incumbent". The canonical definition, the one the paper
  reports, is: mode `cutoff`, λ = 0.5, seed 0, `U = ub_eff`, `z_inc = zref`
  (the *external* incumbent the cutoff was built from, fixed for the whole run),
  and the rows counted by `n_killed_improving` — feasible, above the cutoff, and
  below z_ref. Those lie inside the band by construction, so no clamping is
  needed. **Median 0.057 over the 31 instances that produce such points (5,197
  points in all), with the per-instance median in the lower half of the band on
  29 of the 31.**
* **B2** — every other combination of the definition (top of the band, row
  filter, clamping), because the position does not have a unique definition and
  the paper says which one it reports and what the alternatives give.
* **C** — the number the first version of the paper reported: per-instance median
  of `n_killed_improving`.

`agg_band.py` re-checks six of its own numbers against the values fixed on
2026-09-01 and prints `OK` for each: if the data or the code drift, the check
line says so.

## Not included

The SLURM jobs that produced `grid/` (`job03_grid.sh`, `job04_grid.sh`,
`job17_grid3.sh`, `job20_grid120.sh`) and the earlier aggregator `agg_grid.py`
are part of the exploratory material and are not shipped; the data they produced
are, in full. See §4 of the top-level README.
