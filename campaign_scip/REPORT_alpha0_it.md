# Q2 del referee: il vantaggio del test senza cutoff è un effetto di α > 0? — campagna `alpha0`, 16/09/2026

**Domanda.** Su E1 `recbare` (test del punto arrotondato, nessun cutoff) batte `bare` 22 / 154 / 0 sul gap
finale mediano, mediana della differenza appaiata +17.1 punti. Il referee chiede se il vantaggio sparisce
con la proiezione pura, α = 0. Risposta corta: **no, resta** (17 / 158 / 1, +17.9 punti).

## Che cosa è girato

- ✅ `fpc/job30_alpha0.sh`, job SLURM **4969293** (array 0-175 %32, `razor`, `--exclusive`, 4 run in parallelo
  per lama come in job21), binario `scip_f5` md5 `921dbc833eed2431f5c434de8cde5616` (quello del paper).
- ✅ **1760 / 1760 run completati** (176 istanze di E1 × 2 bracci × 5 semi), 0 falliti, 0 `err`, task più lungo 15 min 14 s.
- ✅ Istanze: `fpc/inst_e1.txt` (le 176 di E1 = griglia completa in `results_fact.txt` e pilot con soluzione, da
  `mk_inst_e1.py` con le definizioni di `agg_fact.py`). TL e z_LP per istanza **presi da `results_fact.txt`**
  (`fpc/tl_e1.txt`), il probe del primo LP non è stato rifatto: `agg_alpha0.py` verifica che tl e z_LP
  coincidano con la campagna su tutte le 176 istanze (True).
- ✅ `.set` di job21 riga per riga + `heuristics/feaspump/alpha = 0`; ordine dei bracci casuale dentro il seme
  (stessa permutazione di job21). `set diffsave` in ogni run: `alpha = 0` risulta caricato in **1760 / 1760**
  file `.diff`. Separatori: **0 chiamate in 1760 / 1760 log** (`set heuristics emphasis off`, `limits/nodes = 1`).
- ⚠️ La campagna del paper girò su `arrow,razor`; questa solo su `razor` (arrow è di un collega). I confronti
  `recbare` vs `bare` sono dentro lo stesso task (stessa lama); i confronti α = 0 vs default attraversano
  campagne diverse a parità di TL in secondi, con il 5 % di clock fra le due partizioni come rumore possibile.
- Dati: `fpc/results_alpha0.txt`; analisi: `python3 fpc/agg_alpha0.py` (definizioni importate da `agg_fact.py`,
  confronto appaiato come `mk_tabs_fact.paired`). Log su cluster: `~/fpc/logs/alpha0_4969293_*.log`, `~/fpc/out/alpha0/`.

## Conteggi

**Tabella 1.** Per braccio su E1 (176 istanze, 880 run): istanze e run con una soluzione, gap finale mediano
(mediana per istanza sui 5 semi, 100 se nessuna soluzione, poi mediana sulle istanze), giri e iterazioni LP
mediani per run. «default» = `results_fact.txt` (α = 1, objfactor default), «0» = campagna `alpha0`.

| braccio | α | inst. con sol. | run con sol. | gap mediano | giri/run | LP iter/run |
|---|---|---|---|---|---|---|
| `bare` | default | 176/176 | 856/880 | 59.12 | 8032 | 2030 |
| `bare` | 0 | 174/176 | 851/880 | 71.62 | 6305 | 1700 |
| `recbare` | default | 176/176 | 856/880 | 58.87 | 7695 | 2124 |
| `recbare` | 0 | 174/176 | 849/880 | 65.94 | 5812 | 1804 |

**Tabella 2.** Confronti appaiati per istanza sul gap finale (mediana dei 5 semi; tolleranza 1e-6): X meglio /
pari / X peggio, p del test dei segni esatto a due code, mediana di (gap Y − gap X) sulle sole istanze non pari
(positiva = X migliore), e lo stesso conteggio per run (appaiato per seme). Split misto/puro da `fact_ncont.txt`
(ncont > 0 dopo presolve = mista; 3 istanze senza ncont: neos-3437289-erdre, neos-3696678-lyvia, neos-633273,
contate in E1 ma in nessuno dei due split).

| strato | confronto X vs Y | meglio / pari / peggio | p | mediana diff. | per run |
|---|---|---|---|---|---|
| E1 (176) | `recbare` vs `bare`, **α = 0** | **17 / 158 / 1** | 1.4e-4 | **+17.9** | 87 / 791 / 2 |
| E1 (176) | `recbare` vs `bare`, α default (paper) | 22 / 154 / 0 | 4.8e-7 | +17.1 | 101 / 779 / 0 |
| E1 (176) | `bare`: α = 0 vs default | 16 / 71 / 89 | < 1e-4 | −1.7 | 92 / 386 / 402 |
| E1 (176) | `recbare`: α = 0 vs default | 18 / 53 / 105 | < 1e-4 | −1.7 | 103 / 305 / 472 |
| miste (56) | `recbare` vs `bare`, α = 0 | 0 / 55 / 1 | 1.0 | −42.2 | 0 / 278 / 2 |
| miste (56) | `recbare` vs `bare`, α default | 0 / 56 / 0 | 1.0 | — | 0 / 280 / 0 |
| pure (120) | `recbare` vs `bare`, α = 0 | 17 / 103 / 0 | < 1e-4 | +18.0 | 87 / 513 / 0 |
| pure (120) | `recbare` vs `bare`, α default | 22 / 98 / 0 | < 1e-4 | +17.1 | 101 / 499 / 0 |

**Tabella 3.** Trovata / non trovata per run a α = 0, `recbare` contro `bare` (880 coppie): le quattro celle.

| solo `recbare` | solo `bare` | entrambi | nessuno |
|---|---|---|---|
| 0 | 2 | 849 | 29 |

- ✅ Le 17 istanze in cui `recbare` vince a α = 0 vincono **tutte anche a default**, con differenze dello stesso
  ordine (ab51/67/69/71/72, cvs08r139-94, cvs16r70/89/106/128, eil33-2, eilA101-2, eilC76-2, ds, opm2-z7-s8,
  opm2-z8-s0, queens-30: +0.7 … +35.3 punti). Nessuna istanza vince **solo** a α = 0.
- 🔵 Le 5 istanze che vincono solo a default sono quelle con l'effetto più piccolo (core4284-1064 +0.1,
  opm2-z6-s1 +0.3, fast0507 +0.5, nu25-pr12 +0.6, opm2-z10-s4 +2.0): a α = 0 diventano pari.
- ⚠️ L'unica sconfitta (drayage-100-12, mista, TL = 20 s) è rumore del time limit: a α = 0 i run di `recbare`
  sui semi 0 e 3 fanno 5 e 0 giri prima del limite (gap 100), `bare` 63 e 53; sul seme 1 entrambi 0 giri.
  Tutte le miste sono pari altrimenti, come a default.
- 🔵 Effetto collaterale, non richiesto: α = 0 peggiora entrambi i bracci (gap mediano +12.5 e +7.1 punti;
  `bare` perde 89 istanze contro 16), con meno giri nel budget.

## Interpretazione (tre righe)

- ✅ **Il vantaggio non è un effetto di α**: alla proiezione pura resta 17 / 158 / 1 con mediana +17.9 punti,
  contro 22 / 154 / 0 e +17.1 a default; se ne vanno solo le 5 istanze con differenze ≤ 2 punti.
- ✅ È interamente sulle istanze **pure** (17 / 103 / 0), dove il test del punto arrotondato non aggiunge nulla
  alla proiezione: ciò che cambia è **quando** la pompa consegna e ciò che fa dopo — la continuazione e il tempo,
  come dice il paper — non il peso dell'obiettivo.
- ⚠️ Sulle miste il test diretto è pari a `bare` a ogni α: lì il vantaggio, se c'è, va cercato nel completamento (M14).

## Frasi possibili per il paper (non inserite nel `.tex`)

> To rule out that the advantage of the direct check without cutoff is an artefact of the objective weight, we
> repeated the two arms on E1 with the pure projection (`heuristics/feaspump/alpha = 0`, same binary, time limits,
> seeds and common parameters). The paired comparison on the final gap gives 17 better / 158 ties / 1 worse
> (exact sign test p = 1.4e-4), with a median paired difference of 17.9 points on the non-tied instances, against
> 22 / 154 / 0 and 17.1 points with the default weight; the 17 instances are a subset of the 22, and the five that
> drop out are those with differences below 2 points. The effect is confined to pure integer instances at both
> settings (mixed: 0 / 56 / 0 and 0 / 55 / 1). The objective weight is therefore not what the direct check exploits.
