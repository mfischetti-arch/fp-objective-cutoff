# Feasibility Pump with Objective Cutoff: A Computational Study — reproducibility package

Code, data and scripts behind the paper

> M. Fischetti. *Feasibility Pump with Objective Cutoff: A Computational Study.*
> Submitted to **Mathematical Programming Computation** (2026).
> The manuscript is in [`paper/manuscript.pdf`](paper/manuscript.pdf).

Everything the paper reports is produced by a script in this repository from the
raw result files shipped here. No number in the paper is typed by hand: the
table below maps every table and figure to the command that regenerates it and
to the file it lands in.

> **Note on language.** The comments and the on-screen output of the scripts are
> in **Italian** (the author's working language). File names, command-line
> options, the LaTeX output and this documentation are in English. Nothing in
> the behaviour of the scripts depends on the language of the comments.

---

## 1. What is here

```
README.md              this file
LICENSE                MIT
CITATION.cff           how to cite the software
.gitignore

scip/                  the patched SCIP: patch chain, build script with pinned commits, NOTICE;
                       scip/minimal/ is the self-contained minimal patch (cutlam, tryrounded, lpfix, restartonsol)
campaign_scip/         the factorial campaign of Sections 5-6 (SCIP): job, aggregators, raw results, the settings file of one cell
prototype/             the from-scratch pump of Section 2: fp.py, its grid of runs, the band aggregator
campaign_gurobi/       experiment E3 of Section 7 (Gurobi): the three-phase target experiment;
                       the objective sweep recorded in the conclusions (fp_react.py, its logs, its table)
paper/                 the .tex table bodies, the figure script, and the manuscript PDF
```

Each directory has its own `README.md` with the details.

---

## 2. Requirements

| component | version used for the results | note |
|---|---|---|
| SCIP | git snapshot **`dba4b2a`** (2026-08-24) | not redistributed; `scip/scip_build.sh` clones and checks it out |
| SoPlex | git snapshot **`f0dbc81`** (2026-08-08) | idem |
| Gurobi | **13.0.3** via `gurobipy` | the from-scratch pump of Section 2 (`prototype/`), experiment E3 and the sweep (`campaign_gurobi/`); a licence able to handle MIPLIB-sized models is required to *run* them, not to re-aggregate them |
| Python | **3.12** on the cluster | the aggregators also run on 3.14; only the standard library, `numpy` and `scipy` are used |
| numpy, scipy | any recent version | `agg_*.py`, `mk_*.py` |
| matplotlib | any recent version | only for `paper/figs_v2.py` |
| gcc | **gcc-toolset-13** (via `scl`) | the system gcc 8.5 of the cluster does not compile SCIP |
| LaTeX | any TeX Live with `booktabs` | only to recompile the manuscript, whose sources are *not* in this package |

⚠️ **The two commit hashes are pinned on purpose.** The patches in
`scip/scip_patch*.py` replace *textual anchors* inside `heur_feaspump.c`: on a
more recent master those lines change, the anchors no longer match and the
artefact does not rebuild. Those two commits are the tree that produced **all**
the results of the paper.

Re-aggregating the results (i.e. reproducing every table and figure of the
paper) needs **only Python + numpy**; SCIP, SoPlex and Gurobi are needed only to
re-run the campaigns from scratch.

---

## 3. How to regenerate every table and figure

All commands are run from the directory shown. Table and figure numbers are
those of `paper/manuscript.pdf`.

| paper object | command | produces |
|---|---|---|
| **Figure 1** (the two sequences of the pump on `scpnrh3`, the "ping-pong" in and out of the cutoff) | `cd paper && python fig_pingpong.py` (`[instance] [rounds]`, default `scpnrh3 150`) | `paper/fig7_pingpong.pdf`, from the per-round `.csv` of `prototype/grid/` |
| **Table 1, left** (fraction of feasible rounded points above the cutoff, three seeds) | `cd prototype && python agg_band.py --latex` (λ = 0.5), `--band-lam 0.75` (λ = 0.25) and `--band-lam 0.25` (λ = 0.75; the option takes the v1 value, see `prototype/README.md`) | printed to stdout; the body is pasted into the manuscript (the `.tex` carries a `%%` provenance line) |
| **Table 1, right** (position in the band, median over three seeds) | `cd prototype && python agg_band_seeds.py --latex --dump ../paper/band_positions_3seeds.csv` | the rows on stdout, pasted into the manuscript; `paper/band_positions_3seeds.csv` |
| **Figure 2** (where the lost improving points sit inside the band) | `cd paper && python figs_v2.py` | `paper/fig5_band.pdf`, from `paper/band_positions_3seeds.csv` |
| **numbers of the two paragraphs of Section 2 after Figure 1** (round of the first lost rounding vs. round of the first point under U; plain vs. perturbed roundings) | `cd prototype && python chk_moat_time.py` and `python chk_spikes.py --table` | printed to stdout; quoted by hand in the text |
| **pure 0-1 vs. mixed numbers of Section 6** (56/120, FGL vs. direct test on the two groups, general integers, split by size) | `cd campaign_scip && python chk_mixed.py` | printed to stdout; quoted by hand in the text |
| **Table 2** (the three experiments at a glance) | none: written by hand in the manuscript | — |
| **Table 3** (E1, the twelve pre-declared paired comparisons, Holm; the last two rows are the two post hoc comparisons of the headline, outside the Holm family) | `cd campaign_scip && python mk_tabs_fact.py` | `paper/tab_fact_paired.tex` |
| **Table 4** (E3, target experiment, outcome) | `cd campaign_gurobi && python mk_tab_target.py` | `campaign_gurobi/tab_target_outcome.tex`, copied to `paper/` |
| **Table 5** (E1 per arm) | `cd campaign_scip && python mk_tabs_fact.py` | `paper/tab_fact_e1.tex` |
| **Table 6** (E2 per arm) | `cd campaign_scip && python mk_tabs_fact.py` | `paper/tab_fact_e2.tex` |
| **Table 7** (E2, the twelve declared comparisons paired per instance on the final gap) | `cd campaign_scip && python mk_tabs_fact.py` | `paper/tab_fact_paired_e2.tex` |
| **Table 8** (found / not found, paired per run) | `cd campaign_scip && python mk_tabs_fact.py` | `paper/tab_fact_found.tex` |
| **Table 9** (E3, paired comparisons on the outcome; W/T/L = wins/ties/losses, as in the rest of the paper) | `cd campaign_gurobi && python mk_tab_target.py` | `campaign_gurobi/tab_target_paired.tex`, copied to `paper/` |
| **numbers quoted in the running text** of Sections 6-8 (medians, counts, cost of the completion, pure vs mixed, split by size) | `cd campaign_scip && python agg_fact.py results_fact.txt --valid validated.txt` | a Markdown report on stdout; the manuscript carries a `%%` comment next to each quoted number saying which line of this report it comes from |
| **independent validation** of every `.sol` (Section 5) | `cd campaign_scip && python agg_fact.py results_fact.txt --valid validated.txt` | the section "Validazione indipendente" of the same report, read from `validated.txt` |
| **declared exclusions** (37 + 2 instances, Section 5) | same command | the section "Esclusioni dichiarate" of the same report; the list is also shipped as `campaign_scip/excluded_instances.txt` |
| **the "For the record" sentence of the conclusions** (the cutoff as the pump's perturbation: 147 vs 158 solved on 272 instances, +14/−7 in the portfolio) | `cd campaign_gurobi && tar xzf results/logs_r26_4949586.tgz && python mk_tab_react.py "logs/r26_4949586_*.log"` | `campaign_gurobi/val_react.tex` (the `\Rc...` macros the sentence uses) and `campaign_gurobi/tab_react.tex` (the full table, supplementary material) |
| **the settings of one cell** of the SCIP campaign (Section 5) | none: `campaign_scip/settings/10teams_rec50_s0.set` and `.cmd` are two files written by `job21_factorial.sh`, reproduced verbatim | — |

`mk_tabs_fact.py` writes into `../paper` by default, i.e. into `paper/` of this
repository; `python mk_tabs_fact.py --out DIR` writes elsewhere.
`mk_tab_target.py` writes into its own directory by default (`--outdir DIR` to
change it) and additionally verifies **14 hard-wired values** against the
tables, printing `controlli: 0 su 14 falliti` when they all agree.

Each generated `.tex` starts with two `%%` provenance lines recording the exact
command and the absolute path of the input file. **The second line necessarily
differs from machine to machine**: when comparing a regenerated table against
the copy shipped here, skip the first two lines.

### The whole cycle, when the raw results change

```
cd campaign_scip
python collect_res.py logs/fact_<jobid>_*.log > results_fact.txt   # all job ids of the campaign
python agg_fact.py results_fact.txt --valid validated.txt          # fatal invariants + report
python mk_tabs_fact.py                                             # the four .tex bodies
cd ../campaign_gurobi && python mk_tab_target.py                   # the two E3 tables
cd ../paper && python figs_v2.py                                   # fig5_band.pdf
```

---

## 4. What is **not** in this repository, and where it is

This package deliberately ships the *results* of the campaigns, not their raw
by-products. Three things are missing, all of them regenerable from what is
here (given the cluster time), and all available from the author on request.

1. **The instances.** MIPLIB 2017 and the OR-Library set-covering instances are
   public and are **not** redistributed: they are cited. `campaign_scip/inst_wide.txt`,
   `prototype/inst_list.txt` and `campaign_gurobi/inst_target23.txt` list exactly
   which ones are used, and `miplib2017.solu` gives the reference values.

2. **The 32,627 `.sol` files written by the SCIP campaign** are included,
   compressed: `campaign_scip/validated_sols.tgz` (31 MB; 455 MB unpacked,
   paths `fpc/sols/<campaign>/<instance>__<variant>_s<seed>.sol`, plus a copy
   of `validated.txt`). The *outcome* of their independent validation is
   `campaign_scip/validated.txt` (28,198 `VALID|` rows, one per validated
   solution), which is what `agg_fact.py --valid` reads and what the paper
   reports. Re-running the validation from the `.sol` files needs
   `campaign_scip/validate_sols.sh` and a SCIP build.

3. **The raw SCIP logs, ~4.2 GB** (`~/fpc/out/` and `~/fpc/sets_*/` on the
   cluster), archived as `~/archive/fpc_scip_out_sets_2026-09-03.tgz`, **436 MB
   compressed** (435,658,633 bytes, md5 `12dcd9af04713f1fe7a8172ce7a247b9`).
   They are the input of `collect_res.py`, whose output —
   `campaign_scip/results_fact.txt`, 28,243 `RES|` rows — *is* in this package
   and is the source of every table. The raw logs are also the input of
   `replay_tl.py`, which cannot therefore be re-run from this package alone.
   The raw logs of the Gurobi sweep campaign quoted in the conclusions are
   small and **are** included: `campaign_gurobi/results/logs_r26_4949586.tgz`
   (272 files, 229 KB compressed).

   **Proposal for the published version of the artefact:** attach the 436 MB
   archive as a **GitHub release asset** (the 2 GB per-file limit is ample), or
   deposit it on **Zenodo** together with a snapshot of this repository, which
   also yields a DOI to cite in the paper. Neither has been done yet; the
   decision is the author's.

4. **The exploratory campaigns that the paper does not report.** Jobs `job00`–
   `job22` (except the census grids of Section 2, `job03`, `job04`, `job20`,
   shipped in `prototype/`) and their `results_*.txt`, the earlier aggregators
   (`agg_e1.py`, `agg_e2.py`, `agg_cnt.py`, `agg_arms*.py`, `agg_grid.py`), the
   auxiliary instance lists (`inst_e2.txt`, `inst_cnt.txt`, `inst_target*.txt`
   of campaign 22, `lamall.txt`, `skipped_e2.txt`) and the tables built on them
   (`tab_e1.tex`, `tab_e2.tex`, `tab_cnt.tex`, `tab_vcnt.tex`, …) are **not**
   included: they predate the factorial campaign that the paper is built on, and
   some of them are contaminated by the `SCIPrecomputeSolObj` defect described
   in `scip/scip_build_all.sh`. They are kept in the author's research
   repository and are **available on request**. One exploratory campaign *is*
   shipped, the "pressure" campaign of `campaign_gurobi/` (`job24_ideas.sh`,
   `agg_ideas.py`, `results/ideas*.res` and `confirm*.res`), because it shares
   code, lists and reference values with E3; the paper does not report it.

5. **`chk_mixed.py`.** An earlier version of the paper documentation refers to a
   control script by this name for the pure/mixed split quoted in the text. **It
   does not exist as a separate file**: that split is produced by `agg_fact.py`
   itself (section "pure 0-1 / mixed" of its report). It is therefore *not
   included*, and nothing is missing.

6. **The LaTeX sources of the manuscript.** Only `paper/manuscript.pdf` is
   shipped; the `.tex` files stay in the author's repository. The table *bodies*
   the manuscript `\input`s are here, in `paper/`.

---

## 5. Reproducing from scratch

The campaigns were run on the blade cluster of the Department of Information
Engineering, University of Padova (SLURM; 4 exclusive cores and 14 GB per task).
The `job*.sh` files carry their `#SBATCH` headers and their exact `sbatch`
command lines in the header comment. They contain absolute paths under
`/home/fisch` and `/nfsd/rop`, and must be adapted to a different site.

Order of operations:

1. `scip/scip_build.sh` — clone SCIP and SoPlex at the pinned commits and build a
   pristine SCIP.
2. `scip/scip_build_all.sh` — apply the patch chain and build the three
   experimental binaries `scip_f1`, `scip_f2`, `scip_f5`.
3. `scip/setup_venv.sh` — the Python environment (3.12, `gurobipy`, numpy, scipy).
4. `campaign_scip/job21_factorial.sh` — the factorial campaign (463 instances ×
   12 arms × 5 seeds).
5. `campaign_scip/validate_sols.sh` — independent revalidation of every `.sol`.
6. `campaign_gurobi/job23_gurobi.sh` — experiment E3, in three phases.
7. The aggregation cycle of Section 3 above.

---

## 6. Versions and provenance in one place

- SCIP `dba4b2a5653707291e16ddb3cc843c7b872291ba` (2026-08-24)
- SoPlex `f0dbc81b47aa13f5746edd42b80df013257e8b2f` (2026-08-08)
- Gurobi 13.0.3 through `gurobipy` 13.0.x
- Python 3.12, numpy, scipy (aggregators verified also under Python 3.14)
- Testbed: MIPLIB 2017 instances with ≥ 80 % binary variables — 463 probed, **424
  analysed** after the declared exclusions, **25,440 runs**; strata **E1 = 176**
  and **E2 = 248** instances.
- Section 2 prototype: 37 instances (OR-Library set covering, MIPLIB 2003,
  MIPLIB 2017), 999 runs in `prototype/grid/`.
- Experiment E3: 134 instances (43 in the MIPLIB 2017 Benchmark Set), 3 arms,
  5 seeds, two target levels a = 0.5 and a = 0.9.

SCIP is licensed under the **Apache License 2.0**; `scip/NOTICE.md` explains what
this package redistributes of it (textual anchors only, never the sources) and
the modification notice that Section 4(b) requires. Read it before publishing
the artefact.

---

## 7. Licence

MIT — see [`LICENSE`](LICENSE). It covers the code and data *of this package*,
not SCIP, not Gurobi, and not the instances.
