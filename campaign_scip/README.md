# `campaign_scip/` — the factorial campaign inside SCIP (Sections 5-6)

This is the campaign the paper is built on: **463 MIPLIB 2017 instances** with at
least 80 % binary variables, **12 arms × 5 seeds**, horizon
`TL = clamp(20 · t_LP, 20, 300)` seconds, binary `scip_f5` (see `../scip/`).

After the declared exclusions the analysed testbed is **424 instances,
25,440 runs**, split into two strata by an independent pilot run:
**E1 = 176** instances (the pilot finds a solution) and **E2 = 248** (it does not).

## The twelve arms

The design is factorial: three ways of treating the rounded point x̂ × five
cutoff levels, plus two fallback variants.

| arm | cutoff λ | treatment of x̂ |
|---|---|---|
| `bare` | none | none — SCIP's feasibility pump, run to the time limit |
| `cut50` | 0.5 | none |
| `recbare` | none | direct test of x̂ against the original constraints |
| `rec50` | 0.5 | direct test |
| `rec75` | 0.75 | direct test (sensitivity) |
| `rec90` | 0.90 | direct test (sensitivity) |
| `rec95` | 0.95 | direct test (the "moat" level, without the name) |
| `recbare_f` | none | FGL completion (fix the integers, minimise cᵀx) |
| `rec50_f` | 0.5 | FGL completion — faithful FGL: cutoff + post-processing |
| `rec95_f` | 0.95 | FGL completion |
| `cut50_fb` | 0.5 | none, with **fallback** on cᵀx̂ before the incumbent |
| `rec50_fb` | 0.5 | direct test, same fallback |

λ is in the **v2 convention**: λ = 1 puts the cutoff U at the incumbent (the
loosest), λ = 0 puts it at the current dual bound z_low.

Design decisions worth knowing when reading the results:

* **Treatment-blind delivery.** Every arm hands the integer iterate to SCIP the
  moment it appears (counter `ifound`). The bare arm used to deliver only at the
  time limit, and that alone produced the false conclusion that the cutoff is inert.
* **No outcome-based filtering.** All 463 instances run all twelve arms; the
  pilot stratifies E1/E2 *afterwards*, it never decides who runs.
* **Randomised arm order** per (instance, seed), same binary for all arms, md5 of
  the binary logged.
* **The probe** measures only the first LP: `set separating emphasis off` (which
  changes neither `t_LP` nor `z_LP`) plus `limits/time 600` as a net. Whoever
  does not pass leaves the testbed **and is declared**. Presolve is never touched.
* **5 seeds** through `randomization/randomseedshift`; median over seeds inside
  the instance, then **paired comparison per instance** with Holm, always
  reported together with the per-run count.

## Running it

```bash
mkdir -p ~/fpc/logs                     # SLURM opens --output before the job starts
sbatch job21_factorial.sh               # #SBATCH --array=0-297%32, partition arrow,razor
sbatch validate_sols.sh                 # independent revalidation of every .sol, on allgroups
```

Both scripts use absolute paths under `/home/fisch/fpc` and read the instances
from the cluster; adapt them to your site. `SCIPBIN`, `INST`, `SEEDS` and
`TPROBE` can be overridden from the environment.

## Aggregating it (this is what needs no cluster)

```bash
python collect_res.py logs/fact_<jobid>_*.log > results_fact.txt
python agg_fact.py results_fact.txt --valid validated.txt
python mk_tabs_fact.py                     # writes the four .tex bodies into ../paper
```

`collect_res.py` keeps **one pass per instance**, the one from the highest job
id. This matters: a campaign that was cancelled and relaunched lives on two job
ids, and while the rows keyed on (instance, arm, seed) would simply overwrite
each other, the `probe|FAIL` and `SKIP` rows have no such key and the stale one
would survive next to the fresh one.

`agg_fact.py` is where every definition lives — parsing, the E1/E2 strata, gamma
and gap, the prolonged primal integral, the median over seeds inside an
instance, the exact sign test and Holm. `mk_tabs_fact.py` imports it rather than
duplicating anything, so the numbers in the tables and those in the aggregator's
Markdown report agree digit by digit. Its report also prints, and the paper
quotes from it:

* the **independent validation** summary read from `validated.txt`;
* the **declared exclusions**: 37 instances whose first LP is not solved within
  the 600 s of the probe, and 2 with an incomplete arm × seed grid because of a
  numerical error in SCIP (`supportcase1` 15/60, `neos-3135526-osun` 48/60);
* the medians, counts, cost of the completion, the pure 0-1 / mixed split and the
  split by size that the running text of Sections 6-8 cites.

`mk_tabs_fact.py` writes into `../paper` by default; `--out DIR` writes elsewhere.
The two `%%` provenance lines at the top of each generated `.tex` record the
command and the **absolute** path of the input, so they legitimately differ from
machine to machine: compare from line 3 on.

## The mandatory invariants

* ✅ **`validate_sols.sh` before any table.** Every `.sol` is re-read on a fresh
  SCIP and on the **original** model. This is needed because in Release builds
  SCIP does *not* re-check the incumbent against the original problem
  (`scip_sol.c:4174`, under `#ifdef`), and dual reductions preserve the optimum,
  not the feasible set. Result of the closed run (job 4934742, 16 shards →
  `validated.txt`): **28,198 `.sol` checked, 0 infeasible, 0 with a recomputed
  objective worse than the declared one, 6 better** (the run under-reported
  itself). `agg_fact.py --valid` is fatal only on infeasible or worse.
* ✅ **Fatal invariant `primal ≥ z_LP − tol`**: 0 violations over the 10,218 runs
  with a solution.
* ✅ **Exclusions declared, never silent** (see above). `agg_fact.py` analyses
  only the complete grid and `mk_tabs_fact.py` uses `A.complete_instances()`.
* ⚠️ **Nothing is separated during the campaign**: `calls=0 applied=0 nodes=1` in
  the logs. The pump is reached after the first LP and the solve ends there, so
  the projection is on the **pure LP relaxation**, `z_low == z_LP` exactly, and
  the completion clone carries only the original constraints.

## `replay_tl.py`

Replays the campaign at a shorter horizon **without re-running anything**: the
SCIP display table in the raw logs prints a line at every new incumbent with its
time and primal bound, so the primal bound at T′ ≤ TL is readable from the log —
the run is deterministic, and truncating is an exact replay, not a simulation.

```bash
python replay_tl.py results_wide.txt --factor 0.1 > results_wide_tl10.txt
```

⚠️ **It needs the raw SCIP logs, which are not in this package** (see §4 of the
top-level README). It is shipped because the paper reports the sensitivity of the
horizon (12 runs worsened out of 10,156 at the lowered cap), and because it is
the only way to redo that check. Also note that the arms without `tryrounded`
(`bare`, `cut50`) deliver only when they leave the loop: replaying them measures
when the run *reports* a solution, not when it finds it. The replay is valid on
the three recovery arms only.

## Files

| file | role |
|---|---|
| `job21_factorial.sh` | the campaign; SLURM array, 463 instances × 12 arms × 5 seeds |
| `validate_sols.sh` | revalidation of every `.sol` on a fresh SCIP and the original model |
| `collect_res.py` | raw logs → `results_fact.txt`, one pass per instance |
| `agg_fact.py` | all the definitions; invariants, exclusions, the Markdown report |
| `mk_tabs_fact.py` | the four `.tex` table bodies (imports `agg_fact`) |
| `replay_tl.py` | shorter-horizon replay from the raw logs (logs not shipped) |
| `inst_wide.txt` | the 463 instances: family, size, path |
| `miplib2017.solu` | MIPLIB 2017 reference values |
| `benchmark-v2.test` | the MIPLIB 2017 Benchmark Set, used to split primary from secondary |
| `results_fact.txt` | **the raw results**: 28,243 `RES|` rows, the source of every table |
| `validated.txt` | **the validation outcome**: 28,198 `VALID|` rows |
