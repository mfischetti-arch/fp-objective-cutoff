# Q3 — la rounding moat adattiva, scalata sul rounding gap osservato (16/09/2026)

**Domanda del referee.** «w = 0 per test al target profondo: una moat per istanza, scalata sul gap o sul
rounding gap δ osservato, è il passo naturale: l'avete provata?» (w è già frazione del gap; mancava δ.)

## Regola implementata (`fp_gurobi/fp_target.py`, modi `test-adapt` / `completion-adapt`, solo aggiunte)
Come test / completion, ma la riga interna parte a U (w = 0) e, dal giro K+1 (K = 5), vale U' = U − m con
m = mediana dei rounding gap δ_k = c'x̂_k − c'x̃_k misurati a ogni giro sull'arrotondamento puro (prima di flip
e restart), troncata in [0, G(1 − 10⁻³)], G = U − z_LP. Tre sotto-regole (`--adapt-rule`):
- **freeze** (primaria, dichiarata prima della campagna): m = mediana dei primi K δ, congelata;
- **running** (secondaria): m = mediana di tutti i δ finora, ricalcolata a ogni giro;
- **abs** (esplorativa, aggiunta dopo lo smoke test): m = mediana di |δ| sui primi K, congelata.
Il resto è identico a E3. Runner `job27_adapt.sh`: per ogni seme i tre run **naive (rifatto) + test-adapt +
completion-adapt** partono insieme sulla stessa lama razor, come i tre bracci di E3; il naive rifatto è il
controllo nella stessa contesa. Aggregato `agg_adapt.py` (definizioni importate da `mk_tab_target.py`).

## Verifica delle politiche esistenti
- ✅ Job 4969310 (naive, test w=0.02, completion w=0.15; 10teams e 30_70_45_095_98; seme 0; a = 0.5): stessi
  esiti e n_iter di `results/eval50.res` (125/515≈519/318 e 10/7/6), tempi entro il 2 % (es. 4.75 vs 4.70 s).
- ✅ Naive rifatto in campagna vs naive di E3, coppia per coppia (670 per campagna): stesso esito su 666/668/667
  (a = 0.5) e 664/663/664 (a = 0.9); rapporto mediano dei tempi 1.01.
- ⚠️ 22 istanze su 134 hanno un TL diverso da E3 (pilota in cache rifatto dopo E3: stesso z_inc e U, t_LP diverso;
  es. ramos3 99→88, cod105 26→21): escluse dai confronti con i bracci di E3 (N = 112 pooled, 41 benchmark, 71
  altre), tenute in quelli col naive rifatto.

## Campagna
Job razor 4969487 (a = 0.5 freeze), 4969488 (0.9 freeze), 4969489 (0.5 running), 4969490 (0.9 running),
4969491 (0.5 abs), 4969492 (0.9 abs): 134 istanze × 5 semi × 3 run. ✅ 804/804 task COMPLETED, **12 060 run,
0 errori, 0 SKIP/FAIL**, invarianti ok. File `fp_gurobi/results/eval{50,90}_adapt{,r,a}.res` (freeze/running/abs).

**Tabella 1. Istanze risolte (coppie riuscite su 670), pooled sulle 134.** Risolta = mediana di target_ok
sui 5 semi = 1 (≥ 3/5), coppie = (istanza, seme) con target_ok = validated = 1. E3 = i bracci del paper
(test w = 0.02/0.05, completion w = 0.15/0.05 ad a = 0.5/0.9); «naive rif.» = naive rifatto nella campagna
freeze; *-adapt = fascia adattiva con la regola indicata.

| a | naive E3 | test E3 | compl. E3 | naive rif. | test-adapt f | compl-adapt f | test-adapt r | compl-adapt r | test-adapt abs | compl-adapt abs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.5 | 87 (438) | 84 (424) | 85 (430) | 88 (436) | 83 (423) | 90 (446) | 79 (405) | 87 (429) | 73 (379) | 81 (404) |
| 0.9 | 104 (519) | 103 (518) | 112 (561) | 103 (513) | 100 (503) | 108 (541) | 99 (503) | 106 (541) | 90 (461) | 100 (503) |

**Tabella 2. Confronti appaiati sull'esito, W/T/L = istanze su cui il braccio adattivo vince / pareggia /
perde**; p = test del segno esatto bilaterale sulle non-parità. «vs naive rif.» sulle 134 (stessa lama,
stesso TL); «vs naive E3» e «vs w fissa» (il test o completion di E3 corrispondente) sulle 112 con TL uguale;
in coda lo split puri (70) / misti (64) del confronto col naive rifatto. Holm sui 16 test dichiarati (freeze,
benchmark e non-benchmark, vs naive E3 e vs w fissa): tutti p_Holm = 1.

| a | regola | braccio | vs naive rif. (p) | vs naive E3 (p) | vs w fissa (p) | puri vs naive rif. | misti vs naive rif. |
|---|---|---|---|---|---|---|---|
| 0.5 | freeze | test-adapt | 1/127/6 (0.125) | 2/105/5 (0.453) | 5/104/3 (0.727) | 1/65/4 | 0/62/2 |
| 0.5 | freeze | completion-adapt | 7/122/5 (0.774) | 7/101/4 (0.549) | 9/99/4 (0.267) | 1/65/4 | 6/57/1 |
| 0.5 | running | test-adapt | 1/124/9 (0.021) | 1/105/6 (0.125) | 5/102/5 (1.000) | 1/62/7 | 0/62/2 |
| 0.5 | running | completion-adapt | 8/118/8 (1.000) | 7/100/5 (0.774) | 9/98/5 (0.424) | 1/62/7 | 7/56/1 |
| 0.5 | abs | test-adapt | 0/119/15 (<0.001) | 0/99/13 (<0.001) | 4/96/12 (0.077) | 0/60/10 | 0/59/5 |
| 0.5 | abs | completion-adapt | 6/115/13 (0.167) | 6/94/12 (0.238) | 9/90/13 (0.523) | 0/60/10 | 6/55/3 |
| 0.9 | freeze | test-adapt | 3/125/6 (0.508) | 2/105/5 (0.453) | 3/106/3 (1.000) | 1/67/2 | 2/58/4 |
| 0.9 | freeze | completion-adapt | 8/123/3 (0.227) | 6/104/2 (0.289) | 1/108/3 (0.625) | 2/66/2 | 6/57/1 |
| 0.9 | running | test-adapt | 2/126/6 (0.289) | 1/106/5 (0.219) | 3/105/4 (1.000) | 2/66/2 | 0/60/4 |
| 0.9 | running | completion-adapt | 6/125/3 (0.508) | 5/105/2 (0.453) | 0/109/3 (0.250) | 1/67/2 | 5/58/1 |
| 0.9 | abs | test-adapt | 2/117/15 (0.002) | 2/98/12 (0.013) | 3/99/10 (0.092) | 1/61/8 | 1/56/7 |
| 0.9 | abs | completion-adapt | 7/117/10 (0.629) | 6/97/9 (0.607) | 1/101/10 (0.012) | 2/60/8 | 5/57/2 |

Per famiglia (freeze, vs naive rif., test e completion): benchmark 0/41/2 e 3/39/1 (a = 0.5), 2/40/1 e 4/39/0
(0.9); non-benchmark 1/86/4 e 4/83/4, 1/85/5 e 4/84/3. «Faster» pooled (istanze risolte da entrambi, tempo
mediano −5 %): test-adapt 25/23/34 e 30/26/41; completion-adapt 24/11/48 e 29/14/57 (l'LP in più si paga).

**Tabella 3. La fascia effettiva.** Per run w_eff = m/G; short = run finiti prima dei K = 5 giri di misura (mai
con fascia); zero (≥K) = run arrivati a K giri con mediana dei δ ≤ 0 (fascia nulla) su quelli arrivati a K;
quantili di w_eff sui 670 run del braccio. Frazione di δ > 0 (campagna freeze): pooled sui giri 10.0 % (a = 0.5,
647 193 giri) e 11.6 % (0.9, 296 984); mediana per run 4.9 % e 7.5 %; run con mediana δ ≤ 0: 72 % e 75 %.

| a | braccio | short | zero moat (≥K) | q75 | q90 | max |
|---|---|---:|---:|---:|---:|---:|
| 0.5 | test-adapt freeze | 113 | 453/557 (81 %) | 0.000 | 0.216 | 0.999 |
| 0.5 | completion-adapt freeze | 131 | 435/539 (81 %) | 0.000 | 0.216 | 0.999 |
| 0.5 | test-adapt abs | 113 | 184/557 (33 %) | 0.340 | 0.817 | 0.999 |
| 0.9 | test-adapt freeze | 152 | 454/518 (88 %) | 0.000 | 0.000 | 0.999 |
| 0.9 | completion-adapt freeze | 192 | 419/478 (88 %) | 0.000 | 0.000 | 0.999 |
| 0.9 | test-adapt abs | 150 | 192/520 (37 %) | 0.111 | 0.558 | 0.999 |

## Interpretazione
- ❌ La moat scalata sul δ osservato **non batte il naive** a nessuno dei due target: freeze 1/127/6 e 3/125/6
  (test), 7/122/5 e 8/123/3 (completion), nel rumore; running non fa meglio (test-adapt perde 1/124/9, p = 0.021,
  ad a = 0.5); abs (fasce grandi, q90 = 0.6–0.8 del gap) **fa male**: test-adapt perde 15 istanze a entrambi i
  target (p < 0.001 e 0.002).
- ❌ **Non batte la w fissa** del paper: contro test/completion di E3 tutto nel rumore; ad a = 0.9
  completion-adapt abs perde 1/101/10 (p = 0.012) contro completion w = 0.05.
- ⚠️ Il motivo è nei dati: con la pompa a distanza pura l'iterato LP sta sulla riga c'x ≤ U' e l'arrotondamento
  **abbassa** il costo nel ~90 % dei giri (δ ≤ 0 in mediana nel 72–75 % dei run): la fascia della regola
  letterale è **nulla in 4 run su 5** e il braccio collassa sul naive. L'unico segnale, completion-adapt sulle
  miste (6/57/1 a entrambi i target, p = 0.125), è quello del completamento LP di E3, non della moat.

## Frasi possibili per il paper (§7, dopo la taratura di w)
«We also tried a per-instance moat scaled on the observed rounding gap: after K = 5 rounds the inner
constraint moves to U' = U − m, with m the median of δ_k = c'x̂_k − c'x̃_k over the rounds seen, truncated to
[0, U − z_LP). On this pump the LP iterate sits on the inner constraint and rounding lowers the cost in about
nine rounds out of ten, so the median gap is nonpositive in three runs out of four and the adaptive moat is
zero; where it is not, it changes nothing: over the 134 instances the adaptive \textsc{test} and
\textsc{completion} win/tie/lose 1/127/6 and 7/122/5 instances against \textsc{naive} at a = 0.5, 3/125/6 and
8/123/3 at a = 0.9 (sign test p ≥ 0.125), and are indistinguishable from the fixed-w policies. A moat scaled
on |δ| instead is harmful (15 instances lost by \textsc{test} at both targets, p ≤ 0.002).»
