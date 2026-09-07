# `campaign_gurobi/` — experiment E3, the target experiment (Section 7), and the objective sweep of the conclusions

E3 rewrites, on **our own code and on Gurobi**, the experiment that inside SCIP
is entangled with the design of the main campaign. The user has the first
solution of a pilot pump, with value z_inc, and wants a solution of cost

```
c'x <= U,      U = z_best + a (z_inc - z_best)          (minimisation sense)
```

with `a = 0.5` (halfway to the best known MIPLIB 2017 value) or `a = 0.9`. **No
arm ever sees z_best**: it enters only through U. U never moves during a run —
there is no chasing of the incumbent — and all three arms exit as soon as a point
feasible for the **original** model with cᵀx ≤ U exists, so the primary outcome
`target_ok` obeys the same rule for everybody and the time spent before exiting
is the other outcome.

Rewriting it outside SCIP was deliberate: in SCIP the cutoff row follows the
incumbent by design of the main campaign, and the implementation contortions
(presolve with an incumbent, delivery, invalidated `objlimit`, decaying α) smelled
of overfitting.

## The three arms

| arm | what it does |
|---|---|
| `naive` | the **static** constraint cᵀx ≤ U is added to the model *before* and *outside* the pump; then a clean distance-only pump runs on the restricted model as a closed box. No starting incumbent: the pilot solution violates the constraint. |
| `test` (w = WT) | the **original** model, plus an **inner** row cᵀx ≤ U′ with U′ = U − WT·(U − z_LP): the inner row digs the rounding moat below U and the pump aims lower. x̂ is tested against the **original** constraints. |
| `completion` (w = WC) | as `test`, but the recovery is the one of FGL 2005 §3.2: fix the integers to x̂ and minimise cᵀx on the **original** constraints (an LP clone with no cutoff). On pure binary instances it coincides with `test` up to the cost of the LPs. |

There is no "test with w = 0" arm: with U′ = U the inner row cuts exactly the
same polyhedron as the static row of `naive` and the exit rule is the same — it
*was* `naive`, letter for letter. **`naive` is the w = 0 point of the grid**, for
`test` as for `completion`.

## The three-phase protocol

Each phase is a separate `sbatch` of the same script, selected by `PHASE`; each
phase has its own `--array`, passed on the `sbatch` command line.

```bash
mkdir -p ~/fpg/logs        # SLURM opens --output before the job starts

# 1. RECON -- only the pilot, no arm: says which instances are eligible and why
sbatch --array=0-107%32 --export=ALL,PHASE=recon job23_gurobi.sh

# 2. TUNE  -- 20 instances OUTSIDE the Benchmark Set, seeds 10-14, grid of w
sbatch --array=0-19%20  --export=ALL,PHASE=tune,A=0.5,RUNTAG=50 job23_gurobi.sh
sbatch --array=0-19%20  --export=ALL,PHASE=tune,A=0.9,RUNTAG=90 job23_gurobi.sh

# 3. EVAL  -- the evaluation set, seeds 0-4, the two chosen w frozen
sbatch --array=0-409%32 --export=ALL,PHASE=eval,A=0.5,RUNTAG=50,WT=0.02,WC=0.15 job23_gurobi.sh
sbatch --array=0-409%32 --export=ALL,PHASE=eval,A=0.9,RUNTAG=90,WT=0.05,WC=0.05 job23_gurobi.sh
```

* **recon** runs `fp_target.py --mode pilot` inside the SLURM task and decides
  eligibility there, with six *distinct* reasons for discarding an instance
  (`unsupported`, `nopilot`, `slow`, `at_best`, `best_below_lp`, `zero_gap`);
  they are kept apart because they say different things. Its output is
  `results/recon.res`, and the resulting eligible sets are `eligible23.txt` and
  `eligible23_full.txt`. The pilot JSONs stay cached and are reused by the later
  phases, so the pilot is never re-run.
* **tune** uses instances **outside** the MIPLIB 2017 Benchmark Set — an exogenous
  tuning/test split, the practice of Nair et al. (2020, arXiv:2012.13349), since
  MIPLIB 2017 has no "primal" tag. The winner is the w with the most
  (instance, seed) pairs with `target_ok = 1` on the `set=tune` rows. Chosen:
  **a = 0.5 → WT = 0.02, WC = 0.15**; **a = 0.9 → WT = WC = 0.05**.
* **eval** runs the three arms with the frozen w on the 134 evaluation instances
  (43 of them in the Benchmark Set), seeds 0-4. `results/eval50.res` and
  `results/eval90.res` are **the source of Tables 3 and 7**.

All phases use `TL = clamp(20 · t_LP, 20, 300)` s and `Threads = 1` per run, with
several runs in parallel inside the task (the departmental efficiency policy
cancels jobs that hold a blade below 60 % CPU; one single-threaded run on four
exclusive cores is 25 %). The parallelism is identical for all arms, which is
what makes the times comparable.

## Regenerating Tables 3 and 7

```bash
python mk_tab_target.py                 # writes tab_target_outcome.tex and tab_target_paired.tex here
python mk_tab_target.py --outdir DIR    # elsewhere
python mk_tab_target.py --no-write      # check only
```

The two files are then **copied into `../paper/`** — unlike the SCIP tables they
carry their own `table` environment, caption and label. The command also prints
the text version and verifies **14 hard-wired values**; a correct run ends with

```
controlli: 0 su 14 falliti
```

The reading and the statistics are those of `agg_target23.py`, imported and not
duplicated: same parsing of the `RES|` rows, same `Row` class (`ok`, `tts`,
`t_cens`, `bench`), same median `med`, same exact sign test `binom_sign_p`, same
Holm. If the tables and the aggregator ever disagree, it is a bug in
`mk_tab_target.py`.

Definitions used throughout: the outcome of (instance, arm) is the median of
`target_ok` over the 5 seeds, so an instance is *solved* when at least 3 seeds
out of 5 succeed; pairs are (instance, seed) with `target_ok = 1` and
`validated ≠ 0`; the censored time is `time_to_success` if successful and the
time limit otherwise; families are benchmark (43), non-benchmark (91), all (134);
types are pure 0-1 (70) and mixed (64).

The aggregator can also be run directly:

```bash
python agg_target23.py recon results/recon.res
python agg_target23.py tune  results/tune50.res
python agg_target23.py eval  results/eval50.res
```

## The exploratory "pressure" campaign (`job24`, **not reported in the paper**)

An exploration the paper does not report (an earlier version mentioned it as a
lead; the submitted one does not): constraints that press towards *feasibility*
rather than cost, namely a cardinality bound, a sign-only cutoff, no-good
constraints on failed roundings, an adaptive U′ (`reflect`), and a
**local-branching ball** of radius one tenth of the binaries around the pilot
solution, doubled when the pump stalls (`lb:0.1:grow`). It is shipped because it
shares code, lists and reference values with E3; nothing in the paper depends on
it. The specs are documented one by one in the `--pressure` docstring of
`fp_target.py`. An arm here is `<mode>[:<pressure>]`, for example
`completion:reflect:0.02+lb:0.1`.

```bash
sbatch --export=ALL,... job24_ideas.sh                 # see the header of the script
python agg_ideas.py results/confirm2_a90.res           # a = 0.9, the ball arms
python agg_ideas.py results/confirm2_a50.res           # a = 0.5
python agg_ideas.py results/confirm1_a90.res results/confirm1_a50.res --a 0.9   # the other confirmation
```

⚠️ **Aggregate one confirmation file at a time.** `confirm1_*` and `confirm2_*`
are two separately declared confirmations that each carry the same two reference
arms (`naive` and `completion:cut:*`), so passing both to `agg_ideas.py` at once
correctly trips the duplicate-arm invariant and refuses to aggregate. This is the
guard working, not a failure.

The numbers quoted in the paper — **110 instances solved against 107 at a = 0.9**
and **92-93 against 85 at a = 0.5** — are the `ist_ok` column of the `tutte` block
of `confirm2_a90.res` and `confirm2_a50.res`. No comparison met the rule declared
before the runs after Holm's correction, which is why the paper reports it as a
lead and not as a result.

`agg_ideas.py` differs from `agg_target23.py` in exactly two ways: every arm is
compared against **two** references (`naive`, to say whether pressure helps at
all, and `completion:cut:*`, to say whether it helps more than today's band), and
the comparison is **on the outcome alone** — a tie broken by time would reward
the faster arm on the easy instances, where everybody succeeds. Time is looked at
separately, only among the instances that *both* arms solve.

The `ideas1_*`, `ideas2_*` and `ideas3_*` files are the three exploratory rounds
that preceded the confirmations; `campaigns.json` records, for each launch, the
job id, the date, the code commit, the instance list, the parameters, where the
logs are and what came out. It is the machine-readable provenance of this
directory.

## The objective sweep (the "For the record" sentence of the conclusions)

The paper's conclusions record one more experiment, in a single sentence: the
cutoff used as the pump's **perturbation** instead of the random flips and
restarts of the from-scratch FGL pump of Section 7. A constraint on cᵀx sweeps
the objective range and is moved at every repeated rounding; nothing is random.
The experiment was written as a full section, audited, and taken out because
its only outcome is a loss without significance; the sentence and the numbers
stay for the record, the full table is supplementary material.

* **Code**: `fp_react.py` (imports `fp_target.py` and `fp.py` of this
  directory; md5 of the file that produced the results: `a28bf7a6…`). The arm
  names are those of its `opts()`; `mk_tab_react.py` maps them to the rows of
  the table: `fgl` the random pump (five seeds, median), `oh` the sweep,
  `eoh` the sweep moved at every repeated rounding, `fl` flips and sweep
  together, `pf` the sweep run first and the random pump after it on the
  remaining budget, `ff` the control that restarts the random pump the same
  way.
* **Testbed**: `inst_react.txt`, 272 pure 0-1 or mixed instances with a first
  LP within 5 s, taken from the pilot cache of E3 (176 on which the pilot pump
  finds a solution, 96 on which it fails); built by `mk_react_list.py`. The time
  limit is the clamp of 20 × t_LP to [20, 300] s, as in Section 5.
* **Runner**: `job26_react.sh`, one instance per SLURM task, all runs of an
  instance on the same blade (Xeon E3-1220 v2, one thread each, batches of
  four); `ARMS` and `SEEDS` come from the environment.
* **Campaign**: job **4949586** ("paper2" in `campaigns.json`): 272 instances ×
  22 runs (four seeded arms × 5 seeds + two deterministic arms) = 5,984 runs,
  none in error. An earlier run of the same design (job 4948984) had 150 runs
  aborted by an uncapped auxiliary LP and is superseded; it is not shipped.
* **Raw logs**: `results/logs_r26_4949586.tgz` (272 files, one per instance).
* **Regenerating** the sentence's macros and the table:

  ```bash
  cd campaign_gurobi
  tar xzf results/logs_r26_4949586.tgz              # creates logs/r26_4949586_*.log
  python mk_tab_react.py "logs/r26_4949586_*.log"   # writes tab_react.tex and val_react.tex here
  ```

  `val_react.tex` holds the `\Rc...` macros (`\RcN` = 272, `\RcOhAll` = 147,
  `\RcFglAll` = 158, `\RcPfWin` = 14, `\RcPfLoss` = 7, …); `tab_react.tex` is
  the full table. The script checks its invariants and stops on a violation.
  The copies shipped here were regenerated from the shipped logs and are
  identical, up to the two `%%` provenance lines.

## Files

| file | role |
|---|---|
| `fp_target.py` | the from-scratch pump for the target scenario: the three modes and all the `--pressure` specs |
| `fp.py` | the Section 2 instrumented pump, copied here unchanged (identical to `../prototype/fp.py`) |
| `job23_gurobi.sh` | E3 proper, three phases selected by `PHASE` |
| `job24_ideas.sh` | the pressure campaign, adapted from `job23` |
| `mk_target23.py` | builds the instance list; eligibility is decided later, by the pilot inside the task |
| `agg_target23.py` | the aggregator of E3: parsing, statistics, invariants (all definitions live here) |
| `agg_ideas.py` | the aggregator of the pressure campaign (imports the parsing from `agg_target23`) |
| `mk_tab_target.py` | Tables 3 and 7, with 14 hard-wired checks |
| `inst_target23.txt` | the instance list of E3 (`set` field: tune / eval) |
| `inst_target23_extra.txt` | the instances added after the first eval launch |
| `inst_ideas.txt`, `inst_confirm.txt` | the lists of the pressure rounds and of the confirmations |
| `eligible23.txt`, `eligible23_full.txt` | the outcome of the recon phase: which instances are eligible |
| `inst_wide.txt`, `miplib2017.solu`, `benchmark-v2.test` | the census of Section 2, the reference values, the Benchmark Set |
| `campaigns.json` | one entry per `sbatch`: job id, date, commit, list, parameters, logs, outcome |
| `results/*.res` | **the raw results**; `eval50.res` and `eval90.res` are the ones the paper's tables are built on |
| `tab_target_outcome.tex`, `tab_target_paired.tex` | the generated tables (copies in `../paper/`) |
| `fp_react.py` | the pump with the objective sweep as perturbation (section above) |
| `job26_react.sh`, `mk_react_list.py`, `inst_react.txt` | the runner, the list builder and the list of the sweep campaign |
| `agg_react.py`, `mk_tab_react.py` | parsing and statistics of the sweep logs; the table and the macros |
| `results/logs_r26_4949586.tgz` | **the raw logs of the sweep campaign**, job 4949586 |
| `tab_react.tex`, `val_react.tex` | the generated table (supplementary material) and the macros of the conclusions' sentence |
