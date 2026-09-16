# M14 del referee: quanto costa il completamento? — campagna `lpft`, 16/09/2026

**Domanda.** Quota di tempo di parete spesa negli LP di completamento (`lpfix`: clone dell'LP con le intere
fissate, c'x minimizzato) nei tre bracci FGL. Risposta corta: sulle **56 istanze miste** di E1 la quota mediana
per run è **22 %** senza cutoff, **7 %** con λ = 0.5, **13.5 %** con λ = 0.95; sulle **120 pure** è **esattamente 0**
(il clone non viene costruito). Un LP di completamento costa 0.3–0.5 ms in aggregato (mediana per run ~2 ms).

## Il cronometro e la sua verifica

- ✅ `scip_f6` = sorgente **patchato** di `scip_f5` (copiato da `~/scipwork/scip/src/scip/heur_feaspump.c`, md5
  `beb741f6…`, identico alla copia locale) + `fpc/scip_patch_lpfixtime.py` (idempotente; `fpc/lpfixtime.diff`, 22 righe).
  Due `SCIP_CLOCK` (wall clock, il `timing/clocktype` del *Solving Time*), stampati in `fp_exit:`: `lpfixtime` avvolge
  **tutto** il completamento per giro (bound del clone, `SCIPlpiSolveDual`, lettura, `SCIP_SOL`, `SCIPtrySol`); `lpfixbuild` la costruzione del clone.
- ✅ Worktree nuovo `~/scipwork/scip_f6` al commit `dba4b2a`, build `build_f6` con i flag di `scip_build_all.sh`
  (`fpc/scip_build_f6.sh`, compilato su arrow-16); binario `~/scipwork/bin/scip_f6` md5
  `a318db87ca3574ca9497a0c5f0d618d2`. `scip_f5` (`921dbc83…`) e `~/scipwork/scip` non toccati.
- ✅ **Verifica di identità** (`fpc/smoke_f6.sh`, arrow-16): `assign1-5-8` e `mad` (miste, E1), bracci `recbare_f` e
  `rec50_f`, stesso `.set` con `maxloops = 200` al posto del time limit (deterministico). In **4 / 4** casi la riga
  `fp_exit` (nloops, nfracs, nstall, nlpiter, ifound, contatori r*, `lpfix/lpfixfeas/lpfixinf`), il *Primal Bound*,
  il numero di soluzioni e la riga `feaspump calls/found` sono **identici byte per byte** fra f5 e f6; differisce solo
  il primal integral alla seconda cifra (dipende dall'orologio, non dalla pompa).

## Che cosa è girato

- ✅ `fpc/job31_lpft.sh`, job SLURM **4969322** (array 0-175 %32, `razor`, `--exclusive`, 4 run in parallelo per lama
  come job21), `scip_f6` (hash nel log di tutti i 176 task). **2640 / 2640 run completati**, 0 falliti, 0 `err`,
  task più lungo 20 min 17 s. Bracci `recbare_f`, `rec50_f`, `rec95_f` (`tryrounded TRUE, lpfix TRUE, cutfallback
  FALSE`), 176 istanze di E1 (`inst_e1.txt`), 5 semi, TL e z_LP della campagna (`tl_e1.txt`), `.set` di job21 riga
  per riga, ordine casuale dentro il seme. Separatori: 0 chiamate in 2640 / 2640 log (in 4 log, tutti con
  `feaspump calls = 0` — LP di radice non finito nel TL — la sezione non è stampata).
- ⚠️ Il paper girò su `arrow,razor`, questa solo su `razor`: 5 % di clock come rumore sui tempi assoluti, non sulle quote.
- Dati: `fpc/results_lpft.txt` (riga `RES|` di job21 + `lpfixtime=`, `lpfixbuild=`; `time=` = *Solving Time*); analisi
  `python3 fpc/agg_lpft.py`; log su cluster `~/fpc/logs/lpft_4969322_*.log`, `~/fpc/out/lpft/`.

## Conteggi

**Tabella 1.** Quota di tempo di parete del completamento, `lpfixtime / Solving Time` in %, per braccio e strato
(split da `fact_ncont.txt`: ncont > 0 dopo presolve = mista). Per run: mediana [q1, q3] e massimo su tutti i run
dello strato; per istanza: mediana sui 5 semi, poi mediana [q1, q3] e massimo sulle istanze. «LP > 0» = run con
almeno un LP di completamento. «ms/LP» = mediana per run di `lpfixtime / lpfix`.

| strato | braccio | per run | per istanza | LP > 0 | ms/LP |
|---|---|---|---|---|---|
| miste (56) | `recbare_f` | **22.0** [16.8, 30.9] max 53.6 | 21.9 [16.9, 29.8] max 53.4 | 276/280 | 2.2 |
| miste (56) | `rec50_f` | **7.0** [1.9, 18.0] max 36.6 | 6.9 [1.8, 17.3] max 35.2 | 274/280 | 1.7 |
| miste (56) | `rec95_f` | **13.5** [4.2, 26.7] max 52.5 | 13.0 [4.4, 27.1] max 47.4 | 277/280 | 2.2 |
| pure (120) | tutti e tre | 0.0 [0.0, 0.0] max 0.0 | 0.0 | 0/600 | — |
| E1 (176) | i tre bracci | mediana 0.0, q3 = 14.6 / 1.1 / 2.2 | — | 276–277/880 | — |

**Tabella 2.** Miste, somme su tutti i 280 run per braccio: tempo del completamento, della costruzione del clone e
*Solving Time* totale; quota aggregata; numero di LP di completamento e costo medio aggregato per LP.

| braccio | Σ lpfixtime (s) | Σ lpfixbuild (s) | Σ Solving Time (s) | quota aggregata | LP di compl. | ms/LP |
|---|---|---|---|---|---|---|
| `recbare_f` | 4102.7 | 7.1 | 22415.9 | **18.3 %** | 7 613 009 | 0.54 |
| `rec50_f` | 1461.5 | 6.9 | 21755.3 | **6.7 %** | 4 829 344 | 0.30 |
| `rec95_f` | 2241.5 | 6.9 | 21540.3 | **10.4 %** | 5 052 690 | 0.44 |

- ✅ Sulle pure la quota è **esattamente 0** in 600 / 600 run per braccio: il clone non viene costruito
  (`lpfix = 0`, `lpfixbuild = 0`). La costruzione del clone è trascurabile: 7 s per braccio, al più 0.4 % di un run.
- 🔵 Le istanze più care hanno centinaia di migliaia di giri in 20 s e un LP di completamento per giro: probportfolio
  53 %, supportcase26 48 %, glass4 47 %, b-ball 46 %, liu 46 %, mas74/76 42 % (`recbare_f`); assign1-5-8 47 % (`rec95_f`).
  Caso opposto: polygonpack4-10 (`rec50_f`, `rec95_f`), un solo giro e **un solo** LP, a freddo, che vale il 35 % dei 20 s.
- 🔵 Senza cutoff la quota è più alta perché il dive è più economico (poche iterazioni per giro, molti giri: 6454
  giri mediani contro 758 di `rec50_f`) e il completamento gira a ogni giro. Nei 4–6 run misti per braccio senza LP
  di completamento la pompa non ha fatto un giro nel TL (es. drayage-100-12 seme 1, LP di radice non finito in 20 s).
- ⚠️ L'LP di completamento non guarda il time limit di SCIP: 12 run su 2640 sforano il TL di più di 1 s (polygonpack4-10,
  `rec50_f`: 22.6–23.0 s con TL = 20 s, un LP da 8 s); 0 su 1760 nella campagna `alpha0`. Da dichiarare se il TL è detto rigido.

**Tabella 3.** Coerenza con la campagna del paper (`results_fact.txt`, `scip_f5`), stessi bracci, E1: istanze e run con
soluzione, gap mediano, giri/run, LP di completamento totali, accettati, infeasible; f6 vs f5 = gap mediano per istanza meglio / pari / peggio.

| braccio | binario | inst. con sol. | run con sol. | gap mediano | giri/run | LP compl. | accettati | infeas. | f6 vs f5 |
|---|---|---|---|---|---|---|---|---|---|
| `recbare_f` | f5 | 176/176 | 856/880 | 55.81 | 6720 | 8 413 518 | 242 | 50 873 | — |
| `recbare_f` | f6 | 176/176 | 850/880 | 55.81 | 6454 | 7 613 009 | 239 | 47 008 | 0 / 173 / 3 |
| `rec50_f` | f5 | 173/176 | 840/880 | 30.41 | 780 | 5 316 978 | 19 865 | 3 072 971 | — |
| `rec50_f` | f6 | 173/176 | 829/880 | 30.41 | 758 | 4 829 344 | 19 406 | 2 740 363 | 2 / 165 / 9 |
| `rec95_f` | f5 | 173/176 | 840/880 | 29.39 | 820 | 5 559 625 | 6 599 | 432 887 | — |
| `rec95_f` | f6 | 173/176 | 832/880 | 29.22 | 788 | 5 052 690 | 6 584 | 398 125 | 4 / 164 / 8 |

- ✅ In linea, non identici: stessi gap mediani, stesse istanze con soluzione, 3–4 % di giri in meno per run (clock + lama razor), 6–11 run con soluzione in meno su 880, 164–173 istanze su 176 pari.

## Interpretazione (tre righe)

- ✅ Il completamento **costa**, ed è misurato: sulle miste un quinto del tempo senza cutoff, un quattordicesimo con
  λ = 0.5, un ottavo con λ = 0.95 (mediane per run; 18 / 7 / 10 % in aggregato). Non è gratis, non è dominante.
- ✅ Il singolo LP è economico (0.3–0.5 ms aggregato, ~2 ms mediana per run): è il **numero** di giri, non il prezzo
  di un LP, a fare la quota. Sulle pure la quota è zero per costruzione.
- ⚠️ Le code (max 54 %) sono istanze piccole con centinaia di migliaia di giri in 20 s, oppure un unico LP grande
  risolto a freddo: un completamento ogni k giri, o a partire dal secondo, le taglierebbe (non provato).

## Frasi possibili per il paper (non inserite nel `.tex`)

> We timed the whole completion step (bound update, dual simplex, solution retrieval and check) with a clock that
> leaves the pump statistics byte-for-byte unchanged. On the 56 mixed instances of E1 the completion takes a median
> 22 % of the running time per run without cutoff (interquartile range 17–31 %, maximum 54 %), 7 % with λ = 0.5
> (2–18 %, max 37 %) and 13.5 % with λ = 0.95 (4–27 %, max 53 %); summed over all runs, 18 %, 7 % and 10 %. A single
> completion LP costs 0.3–0.5 ms on average (warm-started dual simplex): the share is driven by the number of rounds.
> On pure integer instances no clone is built and the cost is zero; building the clone never exceeds 0.4 % of a run.
