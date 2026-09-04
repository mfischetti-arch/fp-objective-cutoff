# `scip/` — rebuilding the patched SCIP

SCIP is **not redistributed** here. What is here are scripts that *transform* a
SCIP source tree already on the machine, by replacing textual anchors inside
`src/scip/heur_feaspump.c`. This is the cleanest form for a paper artefact:
whoever reproduces the results downloads SCIP themselves, at the declared
commit, and applies our modifications.

Read **[`NOTICE.md`](NOTICE.md)** first (it is in Italian): it explains the
Apache 2.0 obligations, in particular §4(b), the modification notice that
`scip_patch_notice.py` writes at the top of the patched `heur_feaspump.c`.

## The pinned commits

```
SCIP    dba4b2a5653707291e16ddb3cc843c7b872291ba    2026-08-24
SoPlex  f0dbc81b47aa13f5746edd42b80df013257e8b2f    2026-08-08
```

⚠️ They are pinned on purpose, and it is not pedantry: the patches replace
**textual anchors**. On a more recent master those lines change, the anchors no
longer match, and the artefact does not rebuild. This is the tree that produced
**all** the results of the paper.

## Two scripts, in this order

```bash
bash scip_build.sh        # clone at the pinned commits, build SoPlex, build a pristine SCIP
bash scip_build_all.sh    # restore heur_feaspump.c from git HEAD, apply the chain, build the 3 binaries
```

Both are written for the cluster (`ROOT=/home/fisch/scipwork`, patch directory
`P=/home/fisch/fpc`, `gcc-toolset-13` through `scl`, `make -j4`): adapt those
paths to your site. The build is deliberately minimal — no IPOPT, ZIMPL,
PAPILO, GMP, READLINE, BOOST, AMPL: none of them is needed by a primal
heuristic, and each is one more dependency that can break the build.

`scip_build_all.sh` is the only build script the paper needs; it does **not**
call any other `scip_build*.sh`. `scip_build.sh` is separate because it is what
fetches the sources and builds the unmodified baseline.

`setup_venv.sh` creates the Python 3.12 virtual environment used by all the
Python scripts of this package (`gurobipy` 13.0.x, numpy, scipy) and checks that
the Gurobi licence works. Only `campaign_gurobi/` needs `gurobipy`; the SCIP
aggregators need numpy alone.

## The three binaries and the patch chain

`scip_build_all.sh` starts from a pristine `heur_feaspump.c` taken from
`git HEAD`, and applies the patches **in cascade** (each one is idempotent):

| binary | patches applied | used by |
|---|---|---|
| `scip_f1` | `scip_patch.py` → `_moat` → `_arms` → `_stop` → `_diag` | the E1 arms |
| `scip_f2` | `scip_f1` + `_osc` | E2 and the counters |
| `scip_f5` | `scip_f2` + `_vcut` + `_rcut` + `_lpfix` | the completion; **this is the binary of the factorial campaign** |

After each stage the script asserts that the call to `SCIPrecomputeSolObj` is
gone: see the long comment at the top of `scip_build_all.sh` for the defect this
guards against (a *transformed* solution passed to a routine meant for
*original* solutions — a feasible vector with a wrong value, which then became
the incumbent). It was found by an external audit and fixed by building the
solution with `SCIPcreateSol` + `SCIPsetSolVal`. The binaries carry the suffix
`f` ("fixed") precisely so that no result file can accidentally mix a pre-fix
pass with a post-fix one.

At the end the script checks that the new parameters are actually registered:

```
set heuristics feaspump tryrounded TRUE     # scip_f1
set heuristics feaspump cutosc 0.8          # scip_f2
set heuristics feaspump lpfix TRUE          # scip_f5
```

## The parameters added to `heuristics/feaspump`

All of them default to the value that reproduces the **original** SCIP
behaviour, so the patched binary is a strict superset of the unpatched one:
`tryrounded`, `moat`/`moatwmin`, `cutlam`, `restartonsol`, `stopafter`,
`cutosc`/`cutoscper`, `lpfix`, plus three counters on the rounded point.

`scip_patch_rcut.py` is applied in the `scip_f5` chain but the arm it enables is
**exploratory and produces no number of the paper**; it is kept here only
because removing it would change the binary that produced the results.

## Files

| file | role |
|---|---|
| `scip_build.sh` | clone at the pinned commits, build SoPlex and the pristine SCIP |
| `scip_build_all.sh` | apply the chain, build `scip_f1`, `scip_f2`, `scip_f5` |
| `setup_venv.sh` | Python 3.12 venv with gurobipy, numpy, scipy |
| `scip_patch.py` | the core patch: `tryrounded`, the recovery of the rounded point, `cutlam` |
| `scip_patch_moat.py` | the `moat` band below the cutoff (never active in the paper: `moatwidth` stays 0) |
| `scip_patch_arms.py` | the arm parameters and the per-arm bookkeeping |
| `scip_patch_stop.py` | `stopafter`: stop SCIP as soon as the pump exits |
| `scip_patch_diag.py` | the diagnostic lines the aggregators parse |
| `scip_patch_osc.py` | `cutosc`/`cutoscper` and the counters on the rounded point |
| `scip_patch_vcut.py` | the virtual cutoff used by the E2 counters |
| `scip_patch_rcut.py` | exploratory arm, no number of the paper depends on it |
| `scip_patch_lpfix.py` | the FGL completion: fix the integers to x̂ and minimise cᵀx on the original constraints |
| `scip_patch_notice.py` | writes the Apache 2.0 §4(b) modification notice at the top of the file |
| `NOTICE.md` | attribution and licence of the SCIP material (Italian) |
