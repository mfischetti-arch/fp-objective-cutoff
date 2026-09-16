# Patch minima a `heur_feaspump.c` (SCIP 11.0.0, commit dba4b2a) — rapporto del 16/09/2026

File prodotti (in questa cartella): `heur_feaspump_min.c` (1832 righe), `heur_feaspump_min.diff`
(438 righe, 13 hunk, +341/−3, intestazioni `a/src/scip/heur_feaspump.c`), `build_min.py` (genera il
`.c` dal pristino con ancore univoche), `smoke/` (risultati, md5, log di compilazione, `smoke_logs.tgz`).

## Che cosa contiene la patch

| funzionalità | righe aggiunte (circa) | parametro nuovo | default |
|---|---|---|---|
| avviso di modifica Apache 2.0 §4(b) in testa al file | 21 | — | — |
| `cutlam`: riga `fp_cutoff` = `c'x ≤ U` in `SCIPaddRowDive` dopo `SCIPstartDive`, `U = zlow + λ·(zinc − zlow)` ricalcolata prima di ogni LP con `SCIPchgRowRhsDive`; senza incumbent rhs = +∞; rilascio a fine dive | 28 + 18 + 4 | `heuristics/feaspump/cutlam` (Real, [−1,1]) | −1 (spento) |
| `tryrounded`: subito dopo l'arrotondamento e prima dei flip, `SCIPcreateSol` + `SCIPsetSolVal` su tutte le variabili, `SCIPtrySolFree` con `checklprows = TRUE` | 30 | `heuristics/feaspump/tryrounded` (Bool) | FALSE |
| `lpfix`: clone LPI (`lpi/lpi.h`) costruito PRIMA di `SCIPstartDive` (solo righe vere, obiettivo vero); a ogni giro `SCIPlpiChgBounds` sugli interi ai valori arrotondati, `SCIPlpiSolveDual`, soluzione costruita da zero e `SCIPtrySolFree` (`checklprows = TRUE`); distruzione a fine dive | 125 + 43 + 7 | `heuristics/feaspump/lpfix` (Bool) | FALSE |
| `restartonsol`: NON è upstream (0 occorrenze nel pristino; viene da `scip_patch_arms.py`). `while( nfracs > 0 || restartonsol )`, consegna dell'iterato intero in testa al giro (`SCIPlinkLPSol` + `SCIPtrySol`), guardia su `maxnflipcands`, perturbazione forzata quando `nfracs == 0` | 1 + 16 + 3 + 2 | `heuristics/feaspump/restartonsol` (Bool) | FALSE |
| campi in `heurdata`, variabili locali, inizializzazioni, registrazione parametri | 8 + 7 + 7 + 12 | — | — |

Didascalia: righe contate sugli hunk del diff (`+341` in tutto, 39 vuote); i parametri sono registrati in
`SCIPincludeHeurFeaspump` con descrizioni in inglese; stile SCIP (3 spazi, `SCIP_CALL`, commenti inglesi).

- ✅ Nessuna chiamata a `SCIPrecomputeSolObj` (grep = 0): le soluzioni sono costruite da zero come in f5 dopo il 02/09.
- ✅ Con i quattro parametri ai default il codice eseguito è quello upstream (ogni blocco è dietro un `if`).
- ⚠️ Scelte fatte ripulendo, da sapere: (1) il clamp `λ ∈ [0.02, 1]` di f5 è mantenuto (con λ=0.5 è ininfluente;
  evita rhs = zlow); (2) in f5 il completamento `lpfix` era annidato dentro `if( tryrounded )`, qui è indipendente
  (`if( fixlpi != NULL )`): identico in tutte le celle del paper (ogni cella `_f` ha entrambi TRUE), diverso solo
  nella combinazione `tryrounded=FALSE, lpfix=TRUE` mai usata; (3) la riga si chiama `fp_cutoff` (in f5 `fp_moat`);
  (4) come in f5, il clone fissa solo le colonne di tipo BINARY/INTEGER (le implied-integer restano libere).

## Che cosa è stato lasciato fuori e perché
- ❌ `moat`/`moatwmin`, `cutfallback`, `cutosc`/`cutoscper`, `rcut`/`rcutk`/`rcuttheta`/`rcutflip`, `vzinc`: bracci
  sperimentali o abbandonati, non nel paper.
- ❌ Tutti i contatori (`nroundedfound`, `nintegralfound`, `nlpfix*`, `nrfeas`/`nrabove`/`nrv*`, `nrcut*`), il
  `SCIPcheckSol` diagnostico a ogni giro, la riga `fp_exit` e il `fp_stop` (`SCIPverbMessage`): servivano
  all'esperimento, non al comportamento. SCIP stampa già calls/found della pompa nelle statistiche.
- ❌ `stopafter` (`SCIPinterruptSolve` a fine pompa): è strumentazione del protocollo di misura, non della
  euristica. Vedi «problemi aperti».

## Compilazione (arrow-16, worktree `~/scipwork/scip_min` a dba4b2a, stessi flag di `scip_build_all.sh`)
- ✅ `git apply --check` del diff sul worktree pulito: OK; dopo `git apply` il sorgente è byte-identico a `heur_feaspump_min.c`.
- ⚠️ Prima compilazione: 1 warning `-Wshadow` (`int j` nel blocco del clone ombreggiava la `j` della funzione);
  corretto (dichiarazione tolta), ricompilato: **0 warning, 0 errori** (`smoke/build2.log`).
- ✅ Binario NUOVO `~/scipwork/bin/scip_min`, md5 `a0b94ed9b68c62c443a66e4ca451db05` (f5: `921dbc83…`). Nessun altro
  binario toccato; `~/scipwork/scip/src/` intatto; nessun job SLURM lanciato.

## Smoke test di equivalenza f5 vs min (arrow-16, un processo alla volta, seme 0)
Istanze: `p0201`, `glass-sc` (pure 0-1), `b-ball`, `glass4` (con continue). Parametri comuni = quelli di
`job21_factorial.sh` (`limits/nodes 1`, `set heuristics emphasis off`, freq 1, maxsols −1, maxstallloops 1e6,
maxlpiterquot 1000, maxlpiterofs 1e7, restartonsol TRUE, verblevel 5, seedshift 0); a f5 in più `moat FALSE`,
`cutosc 0`, `cutfallback FALSE`, `rcut FALSE`. Celle: **a** = cutlam −1 / tryrounded F / lpfix F; **b** = 0.5 / T / T.
Tre regimi: **det** = maxloops 500, TL 600 s, f5 con `stopafter TRUE` (come la campagna); **det-ns** = idem con
`stopafter FALSE`; **tl** = maxloops −1, TL 60 s, `stopafter TRUE`.

| istanza | cella | binario | primal bound | found (pompa) | dive-LP calls / iter | giri (f5) |
|---|---|---|---|---|---|---|
| p0201 | a | f5 / min | 1e20 / 1e20 | 0 / 0 | 255/2067 / 255/2067 | 500 |
| p0201 | b | f5 / min | 1e20 / 1e20 | 0 / 0 | 400/1662 / 400/1662 | 500 |
| glass-sc | a | f5 / min | 39 / 39 | 1 / 1 | 2/1594 / 2/1594 | 500 |
| glass-sc | b | f5 / min | 23 / 23 | 3 / 3 | 387/93888 / 387/93888 | 500 |
| b-ball | a | f5 / min | −1.5 / −1.5 | 1 / 1 | 2/25 / 2/25 | 500 |
| b-ball | b | f5 / min | −1.5 / −1.5 | 1 / 1 | 210/551 / 210/551 | 500 |
| glass4 | a | f5 / min | 4.2167084e9 / 4.2167084e9 | 1 / 1 | 6/129 / 6/129 | 500 |
| glass4 | b | f5 / min | 2.6333627e9 / 2.6333627e9 | 60 / 60 | 346/6947 / 346/6947 | 500 |

Didascalia: regime **det-ns** (`results3.txt`, binario finale). «primal bound» = riga `Primal Bound` delle
statistiche; «found» = colonna Found della riga `feaspump`; «dive-LP» = riga `diving/probing LP` (calls/iterazioni,
comprende tutti i dive del run); «giri» = `nloops` della riga `fp_exit`, che solo f5 stampa (min non ha contatori: il
numero di giri si legge indirettamente dalle iterazioni di dive, identiche). Anche il conteggio totale di soluzioni
(`nsols`) e i file `.sol` scritti sono identici in tutte le 8 coppie (`cmp` byte a byte).

- ✅ **det-ns: identico in ogni numero** su 4 istanze × 2 celle (pb, found, nsols, dive calls, dive iter, .sol).
- ✅ **det (stopafter TRUE in f5)**: pb, found e numeri della pompa identici (`results2.txt`). Differiscono solo
  `nsols` (glass-sc: 51 vs 1 in a, 53 vs 3 in b) e su glass4 un dive-LP in più (6/129 vs 5/103): è lavoro del nodo
  radice DOPO la pompa (strong branching: 25 chiamate, 50 soluzioni non miglioranti), che f5 interrompe con
  `stopafter` e min no. Confermato dal regime det-ns, dove tutto coincide.
- ✅ **tl (60 s)**: pb e found identici in tutte le 8 coppie; i giri no, come atteso, perché min è più veloce per
  giro (f5 fa un `SCIPcheckSol` diagnostico a ogni giro): p0201 a 339k vs 285k dive-LP, glass4 b 63 soluzioni
  in entrambi con pb 2.5750251e9. Su b-ball a la pompa esaurisce da sola i 10^6 stall loops (24.8 s f5, 11.6 s min).
- Log e `.set` in `~/scipwork/scip_min/smoke/` (206 file) e in `smoke/smoke_logs.tgz` qui.

## Problemi aperti
- ⚠️ `stopafter` non c'è in min: con `limits/nodes 1` i numeri della POMPA coincidono, ma il tempo totale e il
  conteggio globale di soluzioni includono il resto del nodo radice. Per riprodurre alla lettera i log della campagna
  (dove SCIP si ferma a fine pompa) serve o il binario f5, o un modo upstream di fermarsi dopo la pompa (non ne
  conosco uno pulito senza toccare altre euristiche/rami: da decidere se accettare la differenza o documentarla).
- 🔵 La patch non è stata provata con `tryrounded=FALSE, lpfix=TRUE` (combinazione resa possibile dal punto (2)).
- 🔵 Non provata in build Debug (assert): solo Release, come la campagna.
