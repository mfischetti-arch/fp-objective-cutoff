# `campaign_gurobi/` — experiment E3, the target experiment (Section 7)

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

## The exploratory "pressure" campaign (`job24`, reported as a lead)

Section 7 closes with a paragraph on constraints that press towards *feasibility*
rather than cost: a cardinality bound, a sign-only cutoff, no-good constraints on
failed roundings, an adaptive U′ (`reflect`), and a **local-branching ball** of
radius one tenth of the binaries around the pilot solution, doubled when the pump
stalls (`lb:0.1:grow`). The specs are documented one by one in the `--pressure`
docstring of `fp_target.py`. An arm here is `<mode>[:<pressure>]`, for example
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
