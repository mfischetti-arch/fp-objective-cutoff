# Attribuzione e licenza del materiale in `fpc/`

## Che cosa distribuiamo, e che cosa no

Le cinque `scip_patch*.py` **non ridistribuiscono SCIP**: sono script che *trasformano* un sorgente
SCIP già presente sulla macchina, sostituendo ancore testuali. È la forma più pulita per un artefatto
di paper — chi riproduce scarica SCIP da sé, alla versione dichiarata, e applica le nostre modifiche.

⚠️ Le ancore di sostituzione, però, **sono frammenti letterali di `heur_feaspump.c`**: righe di
codice SCIP copiate dentro i nostri file per poterle riconoscere. Sono brevi e funzionali
all'identificazione, ma è comunque codice altrui incluso nel nostro materiale, e va attribuito.

## La licenza di SCIP

**SCIP Optimization Suite — Apache License 2.0** (dalla 8.0.3 in avanti, quindi anche SCIP 11, quello
che usiamo). Prima della 8.0.3 era la ZIB Academic License, restrittiva: chi cita la vecchia
situazione sbaglia.

Che cosa ci chiede la Apache 2.0, in concreto:

- **§4(a)** — conservare copyright, brevetti, marchi e note di attribuzione nel codice ridistribuito;
- **§4(b)** ⚠️ — *«You must cause any modified files to carry prominent notices stating that You
  changed the files.»* Il nostro `heur_feaspump.c` compilato **è** un file modificato: deve portare
  la nota in testa. Ci pensa `scip_patch_notice.py`.
- uso commerciale, modifica e ridistribuzione sono liberi, e c'è una concessione esplicita di brevetto
  dai contributori: nessun ostacolo a pubblicare l'artefatto.

## Che cosa mettere nel pacchetto per MPC

MPC chiede il codice **insieme al manoscritto**, e la revisione mira a *verificare i risultati
computazionali riportati*: quindi il pacchetto deve essere eseguibile da un terzo, non solo leggibile.

1. `scip_build.sh` con il **commit hash fissato** di SCIP e SoPlex — ⚠️ senza, fra sei mesi le ancore
   testuali delle patch non applicano più e l'artefatto non si ricostruisce;
2. le sei patch, in ordine: `scip_patch.py` → `_moat` → `_arms` → `_stop` → `_osc` → `_vcut`
   (più `_diag` e `_notice`; `_rcut` è sperimentale e non produce numeri del paper);
3. i job (`job11` E1, `job12` E2, `job13` contatori, `job14` controllo `recbare` in E2, `job15`
   contatori virtuali con `scip_v3`), gli aggregatori (`agg_e1.py`, `agg_e2.py`, `agg_cnt.py`,
   `agg_band.py` — ognuno riproduce i numeri del paper dai `results_*.txt`, e il `--latex` genera le
   tabelle; `paper/mk_tabs.py` e `paper/figs_v2.py` chiudono il ciclo), le liste di istanze e
   `miplib2017-v31.solu` (riferimenti per `job15`);
4. i log grezzi dei risultati, già versionati nel repo: sono la fonte dei numeri delle tabelle;
5. un README che dica **quale tabella nasce da quale file**;
6. questo NOTICE.

Le istanze sono pubbliche (MIPLIB 2017, OR-Library) e **non** vanno ridistribuite: si citano.

## Testo della nota di modifica

Quello inserito da `scip_patch_notice.py` in testa a `heur_feaspump.c`:

```
/* NOTICE (Apache License 2.0, section 4(b)): this file has been MODIFIED with
 * respect to the original SCIP Optimization Suite distribution.
 *
 * Changes, all guarded by parameters whose default reproduces the original
 * behaviour: tryrounded, moat/moatwmin, cutlam, restartonsol, stopafter,
 * cutosc/cutoscper, and three counters on the rounded point.
 *
 * The original file is part of the SCIP Optimization Suite, Copyright (C)
 * Zuse Institute Berlin (ZIB) and contributors, licensed under the Apache
 * License, Version 2.0. The original copyright and license notices below are
 * retained unchanged.
 */
```

⚠️ Una cosa che **non** ho verificato: se l'*Author Tutorial* di MPC imponga un formato particolare
per l'artefatto (licenza obbligatoria, archiviazione con DOI, struttura delle cartelle). Le pagine
pubbliche del sistema editoriale non lo dicono. Da leggere prima di impacchettare.
