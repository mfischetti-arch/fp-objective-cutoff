#!/usr/bin/env python3
"""
Il cutoff VIRTUALE: calcolato a ogni giro, mai imposto.

    python3 scip_patch_vcut.py ~/scipwork/scip/src/scip/heur_feaspump.c

Da applicare dopo scip_patch{,_moat,_arms,_stop,_osc}.py. Idempotente.

PERCHE' (verifica avversariale del 01/09/2026, sera). I contatori della patch
_osc rispondono a meta' della domanda. Il contatore nrabove sta dentro

    if( moatrow != NULL && ... )  heurdata->nrabove++;

e senza cutoff la riga moatrow non viene proprio creata: sui bracci bare e
recbare rabove esce zero in 152 run su 152, ma per COSTRUZIONE, non per
evidenza. Scrivere in un paper «rabove/rfeas ~ 0 senza cutoff, ~ 1 col cutoff»
sarebbe presentare come misura una tautologia dello strumento: senza cutoff non
esiste nessuna soglia sopra cui un punto possa stare.

La domanda vera e' controfattuale: *degli arrotondati ammissibili che il pump
standard incontra, quanti sarebbero stati esclusi da un cutoff a lambda?* Si
risponde calcolando la soglia con gli stessi ingredienti del cutoff reale --
i bound globali -- senza aggiungerla al poliedro. Il pump non se ne accorge,
la traiettoria non cambia, e i bracci diventano finalmente confrontabili.

CONTROLLO INTERNO. Sul braccio col cutoff imposto a lambda=0.5 il contatore
virtuale rv50 deve riprodurre nrabove. Se non lo fa, la patch e' sbagliata:
e' il test di validita' da guardare per primo nei risultati.

TRE LAMBDA IN UN COLPO SOLO. rv25/rv50/rv75 costano tre confronti per giro e
danno l'insensibilita' a lambda DENTRO lo stesso run, invece che confrontando
run diversi come nella misura del 01/09 mattina (65.6/65.9/66.8% per
lambda=0.75/0.5/0.25). E' lo stesso numero, misurato meglio.

IL RIFERIMENTO DEVE VENIRE DA FUORI (parametro vzinc). E' la lezione pagata
due volte scrivendo questa patch, e vale la pena scriverla per esteso perche'
e' la stessa trappola dell'altra misura, in un altro travestimento.

Primo tentativo: soglia = zlow + lambda*(ub - zlow) con ub = SCIPgetUpperbound
letto nel punto in cui si contano gli arrotondati. Sbagliato: qualche riga piu'
su, il recupero ha appena passato QUESTO punto a SCIPtrySolFree, quindi o
l'incumbent e' questo punto o gli sta gia' sotto -- e ogni confronto risulta
vero a ogni lambda. In piu', sul braccio senza recupero l'unica SCIPtrySol
dentro il ciclo e' proprio quella del recupero, quindi li' l'upper bound resta
infinito per tutto il run e non si conterebbe nulla.

Secondo tentativo: soglia fissata a fine giro sul costo dell'ultimo arrotondato
ammissibile, e confrontata al giro dopo. Lo sfasamento toglie la circolarita'
formale ma non quella sostanziale, e si vede misurandolo (mcsched, scip_v3:
rfeas=633, rvfeas=632, rv25=rv50=rv75=632). Il motivo e' semplice: gli
arrotondati di giri vicini si somigliano, quindi un punto della nuvola sta
quasi sempre sopra una frazione lambda<1 del gap costruito su un ALTRO punto
della stessa nuvola. Qualunque riferimento interno al pump da' 100%.

Il riferimento buono e' esterno e fisso: il valore di una soluzione nota
(=opt= o =best= di miplib2017-v31.solu), passato in vzinc nello spazio
ORIGINALE dell'obiettivo e riportato nello spazio trasformato con
SCIPtransformObj. Fisso vuol dire due cose che contano: la soglia e' la stessa
per tutti i bracci -- quindi i bracci sono confrontabili -- e i tre lambda
misurano davvero una distribuzione invece di un artefatto.

Le due ragioni per cui la prima versione era sbagliata restano vere e vanno
tenute a mente leggendo il codice:

  - il blocco tryrounded passa QUESTO STESSO punto a SCIPtrySolFree qualche
    riga piu' su. Quando si arriva al confronto, o il punto e' stato accettato
    (e allora ub == c'xhat, cioe' il punto definisce la propria soglia) o e'
    stato rifiutato perche' non migliorava (e allora ub <= c'xhat). In tutti e
    due i casi c'xhat sta sopra zlow + lambda*(ub-zlow) per ogni lambda < 1, e
    i contatori direbbero «100% nascosto» a qualunque lambda, sempre;
  - sul braccio senza recupero (tryrounded=FALSE) e' peggio: dentro il ciclo
    del pump l'unica SCIPtrySol e' proprio quella del recupero, e la soluzione
    finale viene passata a SCIP dopo l'uscita. L'upper bound resta infinito per
    tutto il ciclo, la guardia non si apre mai, e il braccio che dovrebbe dare
    il numero del paper non produrrebbe NESSUNA osservazione.

IL DENOMINATORE. nrvfeas conta gli arrotondati ammissibili visti nei soli giri
in cui la soglia e' definita (rvbest finito, cioe' dal secondo in poi), che
sono esattamente i giri in cui i tre contatori possono incrementare. Non si
riusa nrfeas: mescolerebbe giri in cui la soglia esiste con giri in cui non
esiste, e il rapporto non vorrebbe dire niente.
"""
import io
import sys

A_STRUCT = """   int                   nrimprove;          /**< ...of those, how many improved the incumbent */"""
N_STRUCT = """   int                   nrimprove;          /**< ...of those, how many improved the incumbent */
   int                   nrvfeas;            /**< feasible rounded points seen while an incumbent existed */
   int                   nrv25;              /**< ...of those, how many sit above a virtual cutoff at lambda=0.25 */
   int                   nrv50;              /**< ...same, at lambda=0.50 */
   int                   nrv75;              /**< ...same, at lambda=0.75 */
   SCIP_Real             vzinc;              /**< external upper reference for the virtual cutoff (original space) */
   SCIP_Real             vrhs25;             /**< virtual cutoff level at lambda=0.25, set at the end of the previous round */
   SCIP_Real             vrhs50;             /**< ...at lambda=0.50 */
   SCIP_Real             vrhs75;             /**< ...at lambda=0.75 */
   SCIP_Bool             vvalid;             /**< are those three levels usable? */"""

A_CNT = """            if( SCIPisLT(scip, cr, SCIPgetUpperbound(scip)) )
               heurdata->nrimprove++;"""
N_CNT = """            if( SCIPisLT(scip, cr, SCIPgetUpperbound(scip)) )
               heurdata->nrimprove++;

            /* The same question, asked against a cutoff that is COMPUTED but
             * never IMPOSED. The counter above is guarded by moatrow != NULL,
             * so on an arm without a cutoff it is zero by construction rather
             * than by evidence; these levels exist on every arm, and the pump
             * never sees them, so no trajectory changes.
             *
             * The levels compared against here were fixed at the END OF THE
             * PREVIOUS ROUND, which is both what the real cutoff does and what
             * keeps the measurement honest. Reading a level here and now would
             * be circular: this same rounded point has just been handed to
             * SCIPtrySolFree a few lines above, so the incumbent either IS
             * this point or already sits below it, and every comparison would
             * come out true at every lambda -- a new tautology in place of the
             * old one.
             */
            if( heurdata->vvalid )
            {
               heurdata->nrvfeas++;
               if( SCIPisGT(scip, cr, heurdata->vrhs25) )
                  heurdata->nrv25++;
               if( SCIPisGT(scip, cr, heurdata->vrhs50) )
                  heurdata->nrv50++;
               if( SCIPisGT(scip, cr, heurdata->vrhs75) )
                  heurdata->nrv75++;
            }
         }

         /* The levels for the NEXT round -- fixed here and compared one round
          * later, which is when the real cutoff is compared against too.
          *
          * The upper reference is the EXTERNAL one when it is given, and that
          * is how the arms are meant to be run: a level built on whatever the
          * pump itself has in hand is a level built on a point of the very
          * cloud being measured, and the answer comes out "all of them" at
          * every lambda, whichever round one reads it in. Measured on mcsched:
          * rv25 = rv50 = rv75 = rvfeas exactly. The incumbent is kept only as a
          * fallback, for runs where no reference value is supplied.
          */
         {
            SCIP_Real zi = SCIPisInfinity(scip, heurdata->vzinc) ?
               SCIPgetUpperbound(scip) : SCIPtransformObj(scip, heurdata->vzinc);
            SCIP_Real zl = SCIPgetLowerbound(scip);

            heurdata->vvalid = !SCIPisInfinity(scip, zi) && !SCIPisInfinity(scip, -zl)
               && SCIPisGT(scip, zi, zl);
            if( heurdata->vvalid )
            {
               SCIP_Real g = MAX(zi - zl, 0.0);

               heurdata->vrhs25 = zl + 0.25 * g;
               heurdata->vrhs50 = zl + 0.50 * g;
               heurdata->vrhs75 = zl + 0.75 * g;
            }"""

A_INIT = """   heurdata->nrimprove = 0;"""
N_INIT = """   heurdata->nrimprove = 0;
   heurdata->nrvfeas = 0;
   heurdata->nrv25 = 0;
   heurdata->nrv50 = 0;
   heurdata->nrv75 = 0;
   heurdata->vvalid = FALSE;"""

A_PARAM = """   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/cutosc","""
N_PARAM = """   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/vzinc",
         "upper reference for the virtual cutoff counters, in the ORIGINAL objective space "
         "(infinity: fall back on the incumbent, which makes the counters much less informative)",
         &heurdata->vzinc, FALSE, SCIP_REAL_MAX, -SCIP_REAL_MAX, SCIP_REAL_MAX, NULL, NULL) );

   SCIP_CALL( SCIPaddRealParam(scip, "heuristics/" HEUR_NAME "/cutosc","""

A_DIAG = """      " rfeas=%d rabove=%d rimprove=%d\\n","""
N_DIAG = """      " rfeas=%d rabove=%d rimprove=%d"
      " rvfeas=%d rv25=%d rv50=%d rv75=%d\\n","""

A_DIAG2 = """      heurdata->nrfeas, heurdata->nrabove, heurdata->nrimprove);"""
N_DIAG2 = """      heurdata->nrfeas, heurdata->nrabove, heurdata->nrimprove,
      heurdata->nrvfeas, heurdata->nrv25, heurdata->nrv50, heurdata->nrv75);"""

STEPS = [(A_STRUCT, N_STRUCT, "struct heurdata: i quattro contatori virtuali"),
         (A_CNT, N_CNT, "il cutoff virtuale a tre lambda"),
         (A_INIT, N_INIT, "azzeramento"),
         (A_DIAG, N_DIAG, "diagnostica: formato"),
         (A_DIAG2, N_DIAG2, "diagnostica: argomenti"),
         (A_PARAM, N_PARAM, "parametro vzinc")]


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "nrvfeas" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "cutosc" not in s:
        print("ERRORE: applica prima scip_patch_osc.py")
        return 1
    for anchor, new, what in STEPS:
        if s.count(anchor) != 1:
            print(f"ERRORE: ancora '{what}' trovata {s.count(anchor)} volte, ne serve 1")
            return 1
        s = s.replace(anchor, new, 1)
        print(f"  applicato: {what}")
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    print(f"cutoff virtuale applicato a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
