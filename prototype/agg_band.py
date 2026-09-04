#!/usr/bin/env python3
r"""
Le tre tabelle sulla FASCIA fra il cutoff e l'incumbent (rounding-moat).

    python agg_band.py                       # markdown
    python agg_band.py --latex               # booktabs
    python agg_band.py --hist --dump band_positions.csv

Legge i run from-scratch di `fp.py` in `grid/` (campagna del 31/08/2026).

A. Quanto e' alta la strage: frazione n_killed/n_feas degli arrotondamenti
   ammissibili che il cutoff scarta, modalita' `cutoff`, per lambda (v2).
B. Dove cadono, dentro la fascia [U, z_inc], gli arrotondamenti ammissibili e
   migliorativi: 0 = appoggiati al cutoff, 1 = appoggiati all'incumbent.
C. Il numero della v1 del paper: mediana per istanza di n_killed_improving.

Regola dell'handoff (come in agg_grid.py): si aggrega PRIMA sui seed dentro
l'istanza, poi fra istanze. Un miglioramento su un seed non e' un miglioramento.

--------------------------------------------------------------------------
CONVENZIONE DI LAMBDA
--------------------------------------------------------------------------
I file di grid/ sono in convenzione v1 (lambda pesava z_lp). Qui, come in
agg_grid.py, si converte con lam_v2 = 1 - lam_v1 per i json privi del campo
"lam_conv": "v2". Vedi grid/CONVENZIONE.md. In v2:

    U = z_lp + lam * (z_ref - z_lp)      lam=1 -> U all'incumbent (il piu' lasco)
                                         lam=0 -> U a z_LP        (il piu' duro)

--------------------------------------------------------------------------
SEMANTICA ESATTA DEI CAMPI (letta in fp.py, funzione fp())
--------------------------------------------------------------------------
Tutte le quantita' obiettivo che finiscono nel .csv (cz_lp, cz_round, ub,
ub_eff, z_best) sono nel segno INTERNO di minimizzazione (c = sign*obj); nel
.json invece z_lp/ub/z_best sono rimoltiplicati per `sign`, cioe' sono nel segno
del problema originale. Le due cose non vanno mai mescolate: qui la parte B
lavora solo sul .csv, quindi e' tutta interna e coerente.

`feas`      (riga del csv)  fp.py:190,218 -- l'arrotondamento x_hat e'
            ammissibile per il problema ORIGINALE, cutoff ESCLUSO:
            viol_max <= feas_tol (default 1e-6). Il cutoff non entra mai nel
            test di ammissibilita': e' esattamente il punto della misura.
`n_feas`    fp.py:200 -- quante iterazioni hanno feas=1. Contatore del run.
`improving` fp.py:198-204,218 -- feas=1 E cz_round < z_best - TOL, cioe'
            l'arrotondamento migliora il MIGLIOR VALORE TROVATO DAL PUMP
            (z_best, che il cutoff lo ignora), non l'incumbent esterno z_ref.
            Alla prima soluzione ammissibile z_best e' None e improving=1.
`n_killed`  fp.py:205-206 -- feas=1 E cz_round > UB + TOL: ammissibile ma
            sopra il cutoff, quindi il cutoff la SCARTA. Attenzione: e'
            contato anche in cut_mode=none, dove UB e' calcolato lo stesso ma
            non imposto -- li' misura le soluzioni che un cutoff AVREBBE perso.
`n_killed_improving`
            fp.py:207-208 -- come sopra E cz_round < z_ref - TOL: la soluzione
            scartata era un MIGLIORAMENTO dell'incumbent di partenza. E' il
            numero della v1 del paper.
`ub`        (colonna del csv) fp.py:219 -- il livello NOMINALE UB = z_lp+lam*g,
            costante per tutto il run, uguale in tutte le modalita'.
`ub_eff`    fp.py:154,219,243-276 -- il cutoff DAVVERO imposto all'LP (cut.RHS).
            La riga viene scritta PRIMA che ub_eff sia aggiornato per l'LP
            successivo (rows.append e' a fp.py:210, il blocco che ricalcola
            ub_eff a fp.py:243): quindi ub_eff sulla riga `it` e' il RHS che era
            in vigore nell'LP che ha prodotto x_t di quella iterazione. Alla
            prima iterazione non c'era ancora nessun vincolo: ub_eff=+inf, che
            viene SCRITTO COME 0.0 con ub_free=1. Va letto con ub_free, mai a
            occhio. In cut_mode=cutoff ub_eff == ub da it=1 in poi; in `moat` e
            `progressive` ub_eff scende sotto ub; in `none` ub_free=1 sempre.
`z_best`    fp.py:201-204,221 -- scritto DOPO l'aggiornamento: su una riga con
            improving=1 vale esattamente cz_round. L'incumbent che c'era PRIMA
            dell'arrotondamento e' quindi lo z_best della riga precedente
            (None -- scritto 0.0 -- finche' non c'e' nessuna soluzione).

--------------------------------------------------------------------------
LA POSIZIONE NELLA FASCIA (parte B)
--------------------------------------------------------------------------
    pos = (cz_round - U) / (z_inc - U)

pos=0 e' appoggiato al cutoff, pos=1 all'incumbent.

Definizione CANONICA (e' quella che riproduce il numero del 01/09: mediana
0.057 su 31 istanze, covering 0.017 / MIPLIB2003 0.107 / MIPLIB2017 0.019,
29 istanze su 31 con mediana < 0.5):

    U     = ub_eff della riga (il cutoff in vigore in quell'iterazione);
            le righe con ub_free=1 (nessun cutoff) sono scartate;
    z_inc = z_ref, l'incumbent ESTERNO da cui il cutoff e' stato ricavato
            (U = z_lp + lam*(z_ref - z_lp)): e' il tetto della fascia che il
            cutoff ritaglia, ed e' fisso per tutto il run;
    righe = sel `killed_impr`, cioe' ESATTAMENTE la popolazione contata da
            n_killed_improving in fp.py:205-208 -- feas=1, cz_round > ub+TOL
            (sopra il cutoff, quindi scartata) e cz_round < z_ref-TOL (ma era
            un miglioramento dell'incumbent). Queste righe stanno DENTRO la
            fascia per costruzione, quindi pos in (0,1) senza bisogno di clamp;
    nessun clamp.

La lettura del paper e' questa: delle soluzioni che il cutoff butta via pur
essendo migliorative, dove cadono nella fascia [U, z_inc]? Mediana 5.7% =
appoggiate al fondo, cioe' appena sopra il cutoff. E' il rounding-moat.

ATTENZIONE alla definizione LETTERALE alternativa (z_inc = z_best del pump
prima dell'aggiornamento, righe feas=1 & improving=1): NON e' la stessa cosa e
da' mediana -0.061 su 24 istanze. Ragione: `improving` in fp.py e' relativo a
z_best, il miglior valore trovato dal PUMP, che ignora il cutoff e scende
presto sotto U; quando z_best < U la fascia [U, z_best] e' vuota (denominatore
negativo) e le righe vengono scartate, e quelle che restano hanno spesso
cz_round < U, cioe' pos < 0. E' una quantita' diversa, non un errore di segno.

La definizione non e' univoca (ub vs ub_eff, z_best prima o dopo, z_ref,
clamp, quali righe), e i numeri cambiano parecchio: --variants (di default
acceso) stampa la tabella di tutte le combinazioni, cosi' la scelta fatta nel
paper e' verificabile invece che dichiarata.
"""

import argparse
import csv
import glob
import json
import os
import statistics as st
import sys
from collections import defaultdict

try:                                   # su Windows lo stdout e' cp1252
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TOL = 1e-9                             # guardia geometrica (fascia non degenere)
TOL_FP = 1e-6                          # la TOL di fp.py: i test feas/killed/improving
LAMS = (0.25, 0.5, 0.75)
SELS = ("impr", "killed_impr", "impr_killed", "feas", "killed")
ZINCS = ("zref", "prev", "prevfb", "best", "after")
# il numero stabilito il 01/09, che la definizione canonica deve riprodurre
RIF_B = {"TUTTE": 0.057, "ORLib_setcover": 0.017,
         "miplib2003": 0.107, "miplib2017": 0.019}
RIF_B_N, RIF_B_LOW = 31, 29
FAM_LABEL = {"ORLib_setcover": "covering",
             "miplib2003": "MIPLIB2003",
             "miplib2017": "MIPLIB2017"}
FAM_ORDER = ("ORLib_setcover", "miplib2003", "miplib2017")


# --------------------------------------------------------------------------
# lettura (stessa logica di agg_grid.py)
# --------------------------------------------------------------------------

def fam_of(inst_list):
    """basename del path -> famiglia, da inst_list.txt (campo 0 = famiglia)."""
    m = {}
    for ln in open(inst_list):
        if ln.startswith("#") or not ln.strip():
            continue
        f = ln.rstrip("\n").split("\t")
        m[os.path.basename(f[2])] = f[0]
    return m


def stem_map(fam):
    """'air03' -> famiglia: i .csv sono nominati con lo stem, i .json col
    basename completo ('air03.mps.gz')."""
    out = {}
    for k, v in fam.items():
        out[k.split(".")[0]] = v
    return out


def load_runs(d, fam):
    """Tutti i .json della griglia, con lam SEMPRE in convenzione v2."""
    runs = []
    for p in sorted(glob.glob(os.path.join(d, "*.json"))):
        s = json.load(open(p))
        if s.get("status") in ("no_firstsol",) or "cut_mode" not in s:
            continue
        s["fam"] = fam.get(s["inst"], "?")
        if s.get("lam_conv") != "v2" and s.get("lam") is not None:
            s["lam"] = round(1.0 - s["lam"], 6)
        # fp.py NON scrive moat_wmin nel summary: le due larghezze della fascia
        # progressiva (w0.05 / w0.15) si distinguono solo dal nome del file, e
        # senza questo tag finirebbero mescolate come se fossero altri semi.
        base = os.path.basename(p)[:-5]
        s["wtag"] = base.split("_")[-1] if "_w0." in base else ""
        s["mode_lab"] = s["cut_mode"] + (f" {s['wtag']}" if s["wtag"] else "")
        runs.append(s)
    return runs


def read_csv_rows(p):
    with open(p, newline="") as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


def med(v):
    return st.median(v) if v else None


def mean(v):
    return st.fmean(v) if v else None


# --------------------------------------------------------------------------
# stampa: markdown o booktabs
# --------------------------------------------------------------------------

class Out:
    def __init__(self, latex):
        self.latex = latex

    def h(self, txt, lvl=2):
        if self.latex:
            print("\n%% " + txt)
        else:
            print("\n" + "#" * lvl + " " + txt)

    def p(self, txt):
        print(("%% " if self.latex else "") + txt if self.latex else txt)

    def table(self, head, rows, caption=None, align=None):
        if not self.latex:
            print("| " + " | ".join(head) + " |")
            print("|" + "|".join("---" for _ in head) + "|")
            for r in rows:
                print("| " + " | ".join(str(x) for x in r) + " |")
            return
        al = align or ("l" + "r" * (len(head) - 1))
        print(r"\begin{table}[t]\centering")
        if caption:
            print(r"\caption{%s}" % caption)
        print(r"\begin{tabular}{%s}" % al)
        print(r"\toprule")
        print(" & ".join(_tex(x) for x in head) + r" \\")
        print(r"\midrule")
        for r in rows:
            print(" & ".join(_tex(str(x)) for x in r) + r" \\")
        print(r"\bottomrule")
        print(r"\end{tabular}")
        print(r"\end{table}")


def _tex(s):
    s = str(s)
    s = s.replace("%", r"\%").replace("_", r"\_")
    s = s.replace("`", "").replace("**", "")
    return s


def fmt(x, d=2, suf=""):
    return "--" if x is None else f"{x:.{d}f}{suf}"


# --------------------------------------------------------------------------
# A -- frazione di ammissibili che il cutoff scarta
# --------------------------------------------------------------------------

def part_A(o, runs):
    o.h("A — frazione di arrotondamenti ammissibili che stanno SOPRA il cutoff "
        "(`n_killed / n_feas`, modalita' `cutoff`)")
    o.p("Mediana sui semi dentro l'istanza, poi mediana e media fra istanze. "
        "Un'istanza entra se ha almeno un seme con `n_feas > 0`; le altre sono "
        "contate a parte nella colonna *escluse*.")

    # (inst, fam, lam) -> lista di frazioni, una per seme
    per = defaultdict(list)
    seen = defaultdict(set)
    for s in runs:
        if s["cut_mode"] != "cutoff" or s["lam"] not in LAMS:
            continue
        k = (s["inst"], s["fam"], s["lam"])
        seen[k].add(s["seed"])
        if s["n_feas"] > 0:
            per[k].append(s["n_killed"] / s["n_feas"])

    head = ["famiglia", "lam (v2)", "istanze", "escluse (n_feas=0)",
            "mediana", "media"]
    rows = []
    for lam in LAMS:
        for f in FAM_ORDER + ("TUTTE",):
            vals, excl = [], 0
            for (inst, fm, lm), v in seen.items():
                if lm != lam or (f != "TUTTE" and fm != f):
                    continue
                if per[(inst, fm, lm)]:
                    vals.append(st.median(per[(inst, fm, lm)]))
                else:
                    excl += 1
            if not vals and not excl:
                continue
            lab = FAM_LABEL.get(f, f) if f != "TUTTE" else "**tutte**"
            rows.append([lab, lam, len(vals), excl,
                         fmt(100 * med(vals), 1, "%"),
                         fmt(100 * mean(vals), 1, "%")])
    o.table(head, rows,
            caption="Frazione degli arrotondamenti ammissibili scartata dal cutoff.")


# --------------------------------------------------------------------------
# B -- posizione nella fascia
# --------------------------------------------------------------------------

def positions(rows, ucol="ub_eff", zinc="prev", sel="impr", clamp=False,
              zref=None):
    """Posizioni pos=(cz_round-U)/(z_inc-U) di un singolo run (lista di righe
    del csv). Ritorna [(it, pos)]. Vedi la docstring del modulo per le opzioni."""
    out = []
    zb_prev = None                      # z_best PRIMA dell'aggiornamento
    for r in rows:
        if ucol == "ub":
            U = r["ub"]
        else:                           # ub_eff: 0.0 quando ub_free=1 = +inf
            U = None if r["ub_free"] else r["ub_eff"]
        ok = r["feas"] == 1
        if sel in ("impr", "impr_killed"):
            ok = ok and r["improving"] == 1
        if sel in ("killed", "impr_killed", "killed_impr"):
            # fp.py:205 conta n_killed contro l'UB NOMINALE, non contro ub_eff:
            # in cut_mode=cutoff coincidono, in moat/progressive no.
            ok = ok and r["cz_round"] > r["ub"] + TOL_FP
        if sel == "killed_impr":
            # fp.py:207 -- ...ed era un miglioramento dell'incumbent esterno.
            # La coppia dei due test e' esattamente n_killed_improving.
            ok = ok and zref is not None and r["cz_round"] < zref - TOL_FP
        if ok and U is not None:
            if zinc == "prev":
                zi = zb_prev
            elif zinc == "prevfb":       # ripiego su z_ref finche' non c'e' z_best
                zi = zb_prev if zb_prev is not None else zref
            elif zinc == "best":         # incumbent vero: il meglio fra i due
                zi = (zref if zb_prev is None else
                      (zb_prev if zref is None else min(zb_prev, zref)))
            elif zinc == "after":        # z_best DOPO l'aggiornamento (=cz_round)
                zi = r["z_best"] if r["z_best"] else None
            else:                        # "zref": l'incumbent esterno
                zi = zref
            if zi is not None and zi - U > TOL:
                q = (r["cz_round"] - U) / (zi - U)
                if clamp:
                    q = min(1.0, max(0.0, q))
                out.append((int(r["it"]), q))
        if r["improving"] == 1:
            zb_prev = r["z_best"]
    return out


def band_files(d, mode, lam=0.5, seed=0, wtag="w0.05"):
    pat = f"*__{mode}_lam{lam}_s{seed}.csv"
    if mode == "progressive":
        pat = f"*__{mode}_lam{lam}_s{seed}_{wtag}.csv"
    return sorted(glob.glob(os.path.join(d, pat)))


def band_data(d, sfam, mode, lam, seed, wtag, **kw):
    """{istanza: (famiglia, [(it,pos)])} per una definizione data."""
    out = {}
    for p in band_files(d, mode, lam, seed, wtag):
        base = os.path.basename(p).split("__")[0]
        rows = read_csv_rows(p)
        jp = p[:-4] + ".json"
        js = json.load(open(jp)) if os.path.exists(jp) else {}
        # z_ref nel segno INTERNO. Si prende dal json (che lo ha in piena
        # precisione, nel segno ORIGINALE) e si rigira col segno del modello:
        # ub_json = sign*UB e ub_csv = UB, quindi il segno si legge dai due.
        # NON si ricostruisce da ub_csv + (1-lam)*gap_int: la colonna `ub` del
        # csv e' scritta con %.10g e l'errore (~3e-6 su f2gap40400) basta a
        # far cambiare esito al test cz_round < z_ref - 1e-6.
        zref = None
        if rows and js.get("z_ref") is not None:
            sign = (1.0 if abs(js.get("ub", 0.0) - rows[0]["ub"])
                    <= abs(js.get("ub", 0.0) + rows[0]["ub"]) else -1.0)
            zref = sign * js["z_ref"]
        pos = positions(rows, zref=zref, **kw)
        if pos:
            out[base] = (sfam.get(base, "?"), pos)
    return out


def part_B(o, d, sfam, a):
    o.h("B — posizione degli arrotondamenti ammissibili e migliorativi nella "
        "fascia [U, z_inc]")
    ZDESC = {"zref": "z_ref, l'incumbent **esterno** da cui il cutoff e' "
                     "ricavato (tetto della fascia, fisso per tutto il run)",
             "prev": "z_best **prima** dell'aggiornamento",
             "prevfb": "z_best precedente, con ripiego su z_ref",
             "best": "min(z_best precedente, z_ref)",
             "after": "z_best **dopo** l'aggiornamento"}
    SDESC = {"killed_impr": "le righe contate da `n_killed_improving` "
                            "(feas=1, sopra il cutoff, e sotto z_ref): stanno "
                            "dentro la fascia per costruzione",
             "impr": "feas=1 e improving=1",
             "impr_killed": "feas=1, improving=1 e sopra il cutoff",
             "feas": "tutte le feas=1",
             "killed": "feas=1 e sopra il cutoff"}
    o.p(f"`pos = (cz_round - U)/(z_inc - U)`; 0 = appoggiato al cutoff, "
        f"1 = appoggiato all'incumbent. Definizione canonica: modalita' "
        f"`{a.band_mode}`, lam {a.band_lam} nel nome del file (convenzione v1: "
        f"lambda_v2 = {1 - a.band_lam:g}), seme 0, U = `{a.band_u}` (righe senza "
        f"cutoff scartate), z_inc = {ZDESC[a.band_zinc]}, righe = "
        f"{SDESC[a.band_sel]}, {'con' if a.clamp else 'nessun'} clamp.")

    data = band_data(d, sfam, a.band_mode, a.band_lam, 0, a.wtag,
                     ucol=a.band_u, zinc=a.band_zinc, sel=a.band_sel,
                     clamp=a.clamp)
    per_inst = {b: (f, st.median([q for _, q in ps]), len(ps))
                for b, (f, ps) in data.items()}

    head = ["famiglia", "istanze", "mediana della mediana per istanza",
            "istanze con mediana < 0.5", "arrotondamenti usati"]
    rows = []
    for f in FAM_ORDER + ("TUTTE",):
        v = [(m, n) for (fm, m, n) in per_inst.values()
             if f == "TUTTE" or fm == f]
        if not v:
            continue
        lab = FAM_LABEL.get(f, f) if f != "TUTTE" else "**tutte**"
        low = sum(1 for m, _ in v if m < 0.5)
        rows.append([lab, len(v), fmt(med([m for m, _ in v]), 3),
                     f"{low}/{len(v)}", sum(n for _, n in v)])
    o.table(head, rows, caption="Posizione nella fascia, definizione canonica.")

    # --- confronto col numero di riferimento del 01/09 ----------------------
    if a.band_lam == 0.5 and (a.band_mode, a.band_u, a.band_zinc, a.band_sel, a.clamp) == \
            ("cutoff", "ub_eff", "zref", "killed_impr", False):
        byf = defaultdict(list)
        for fm, m, _ in per_inst.values():
            byf[fm].append(m); byf["TUTTE"].append(m)
        chk = []
        for f in ("TUTTE",) + FAM_ORDER:
            got, exp = med(byf.get(f)), RIF_B[f]
            chk.append(f"{FAM_LABEL.get(f, 'tutte')} atteso {exp:.3f} / "
                       f"ottenuto {got:.3f} "
                       f"{'OK' if abs(got - exp) < 5e-4 else '**DIVERSO**'}")
        n, low = len(byf["TUTTE"]), sum(1 for m in byf["TUTTE"] if m < 0.5)
        chk.append(f"istanze atteso {RIF_B_N} / ottenuto {n} "
                   f"{'OK' if n == RIF_B_N else '**DIVERSO**'}")
        chk.append(f"mediana < 0.5 atteso {RIF_B_LOW} / ottenuto {low} "
                   f"{'OK' if low == RIF_B_LOW else '**DIVERSO**'}")
        o.p("Controllo contro il numero stabilito il 01/09: " + "; ".join(chk) + ".")

    if a.variants:
        o.h("B2 — le varianti della definizione", 3)
        o.p("La posizione non ha una definizione unica. Colonne: U = livello "
            "usato come fondo della fascia; z\\_inc = incumbent usato come "
            "tetto (`prev` = z_best prima dell'aggiornamento, `after` = dopo, "
            "`zref` = incumbent esterno del run, `prevfb` = prev con ripiego "
            "su zref, `best` = min(prev, zref), cioe' l'incumbent davvero "
            "noto in quel momento); righe = filtro sulle iterazioni "
            "(`killed_impr` = la popolazione di `n_killed_improving`, cioe' "
            "sopra il cutoff E sotto z_ref; `impr_killed` = migliorativi "
            "rispetto a z_best E sopra il cutoff -- non e' la stessa cosa). "
            "La riga in grassetto e' la canonica.")
        vh = ["modo", "U", "z_inc", "righe", "clamp", "istanze", "mediana",
              "media", "<0.5", "covering", "MIPLIB2003", "MIPLIB2017"]

        def vrow(mode, ucol, zinc, sel, clamp):
            dd = band_data(d, sfam, mode, a.band_lam, 0, a.wtag, ucol=ucol,
                           zinc=zinc, sel=sel, clamp=clamp)
            pi = {b: (f, st.median([q for _, q in ps]))
                  for b, (f, ps) in dd.items()}
            if not pi:
                return None
            allm = [m for _, m in pi.values()]
            byf = defaultdict(list)
            for f, m in pi.values():
                byf[f].append(m)
            canon = (mode == a.band_mode and ucol == a.band_u
                     and zinc == a.band_zinc and sel == a.band_sel
                     and clamp == a.clamp)
            b_ = "**" if canon and not o.latex else ""
            return [f"{b_}{mode}{b_}", ucol, zinc, sel, int(clamp), len(pi),
                    f"{b_}{fmt(med(allm), 3)}{b_}", fmt(mean(allm), 3),
                    f"{sum(1 for m in allm if m < 0.5)}/{len(pi)}",
                    fmt(med(byf.get('ORLib_setcover')), 3),
                    fmt(med(byf.get('miplib2003')), 3),
                    fmt(med(byf.get('miplib2017')), 3)]

        vr = []
        for ucol in ("ub_eff", "ub"):
            for zinc in ZINCS:
                for sel in SELS:
                    for clamp in (False, True):
                        r = vrow(a.band_mode, ucol, zinc, sel, clamp)
                        if r:
                            vr.append(r)
        o.table(vh, vr, caption="Varianti della definizione di posizione "
                                "(modalita' %s)." % a.band_mode)

        o.h("B2bis — la definizione canonica sulle altre modalita'", 3)
        vr = []
        for mode in ("cutoff", "moat", "none", "progressive"):
            r = vrow(mode, a.band_u, a.band_zinc, a.band_sel, a.clamp)
            if r:
                vr.append(r)
        o.table(vh, vr, caption="Definizione canonica, tutte le modalita'.")
        o.p("`none` non compare: li' il cutoff non e' mai imposto (ub_free=1 "
            "su ogni riga), quindi con U=`ub_eff` non c'e' nessuna fascia.")

    if a.hist:
        o.h("B3 — istogramma delle posizioni (definizione canonica)", 3)
        allp = [q for _, ps in data.values() for _, q in ps]
        lo = sum(1 for q in allp if q < 0.0)
        hi = sum(1 for q in allp if q > 1.0)
        bins = [0] * 10
        for q in allp:
            if 0.0 <= q <= 1.0:
                bins[min(9, int(q * 10))] += 1
        tot = len(allp) or 1
        wid = max([lo, hi] + bins) or 1
        print(f"\n```\nn = {len(allp)} arrotondamenti, "
              f"{len(data)} istanze   (modo {a.band_mode}, lam 0.5, seme 0)")
        print(f"  < 0.0       {lo:6d} {100*lo/tot:5.1f}% "
              f"{'#' * int(40 * lo / wid)}")
        for i, c in enumerate(bins):
            print(f"  [{i/10:.1f},{(i+1)/10:.1f}) {c:6d} {100*c/tot:5.1f}% "
                  f"{'#' * int(40 * c / wid)}")
        print(f"  > 1.0       {hi:6d} {100*hi/tot:5.1f}% "
              f"{'#' * int(40 * hi / wid)}")
        print("```")

    if a.dump:
        with open(a.dump, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["inst", "fam", "it", "pos"])
            for b in sorted(data):
                fm, ps = data[b]
                for it, q in ps:
                    w.writerow([b, FAM_LABEL.get(fm, fm), it, f"{q:.10g}"])
        o.p(f"\nscritto `{a.dump}`: "
            f"{sum(len(ps) for _, ps in data.values())} righe.")


# --------------------------------------------------------------------------
# C -- il numero della v1: n_killed_improving
# --------------------------------------------------------------------------

def part_C(o, runs):
    o.h("C — soluzioni MIGLIORATIVE scartate dal cutoff "
        "(`n_killed_improving`, mediana per istanza)")
    o.p("Mediana sui semi dentro l'istanza, poi mediana fra istanze. In "
        "`none` il cutoff non e' imposto: il contatore misura le soluzioni che "
        "un cutoff AVREBBE perso. `progressive` compare sia unita (le due "
        "larghezze di fascia trattate come run dello stesso metodo, che e' "
        "come la leggeva la nota del 01/09) sia spezzata per `w`.")

    per = defaultdict(list)
    for s in runs:
        if s.get("lam") is None:
            continue
        per[(s["inst"], s["fam"], s["mode_lab"], s["lam"])].append(
            s["n_killed_improving"])
        if s["wtag"]:                  # la versione unita, per confronto
            per[(s["inst"], s["fam"], s["cut_mode"], s["lam"])].append(
                s["n_killed_improving"])

    agg = defaultdict(list)
    for (inst, f, m, lam), v in per.items():
        agg[(f, m, lam)].append(st.median(v))

    head = ["famiglia", "modo", "lam (v2)", "istanze",
            "mediana n_killed_improving", "% istanze con >= 1"]
    rows = []
    for m in sorted({k[1] for k in agg},
                    key=lambda x: (["none", "cutoff", "moat"].index(x)
                                   if x in ("none", "cutoff", "moat") else 3, x)):
        for lam in sorted({k[2] for k in agg if k[1] == m}):
            for f in FAM_ORDER + ("TUTTE",):
                v = [x for (fm, mm, ll), vv in agg.items()
                     if mm == m and ll == lam and (f == "TUTTE" or fm == f)
                     for x in vv]
                if not v:
                    continue
                lab = FAM_LABEL.get(f, f) if f != "TUTTE" else "**tutte**"
                rows.append([lab, f"`{m}`", lam, len(v), fmt(med(v), 0),
                             fmt(100 * sum(1 for x in v if x > 0) / len(v),
                                 0, "%")])
    o.table(head, rows,
            caption="Soluzioni migliorative scartate dal cutoff.")


# --------------------------------------------------------------------------

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--dir", default=os.path.join(here, "grid"))
    p.add_argument("--inst-list", default=os.path.join(here, "inst_list.txt"))
    p.add_argument("--latex", action="store_true", help="tabelle booktabs")
    p.add_argument("--hist", action="store_true",
                   help="istogramma testuale delle posizioni (10 bin)")
    p.add_argument("--dump", nargs="?", const="band_positions.csv", default=None,
                   help="scrive istanza,famiglia,iterazione,pos per la figura")
    p.add_argument("--band-mode", default="cutoff",
                   choices=["cutoff", "moat", "none", "progressive"])
    p.add_argument("--band-lam", type=float, default=0.5,
                   help="lambda dei csv di fascia, COME NEL NOME DEL FILE (convenzione v1: "
                        "0.25 = lambda_v2 0.75, cutoff lasco; 0.75 = lambda_v2 0.25). "
                        "I csv a 0.25 e 0.75 vengono da job17_grid3.sh")
    p.add_argument("--band-u", default="ub_eff", choices=["ub_eff", "ub"])
    p.add_argument("--band-zinc", default="zref", choices=list(ZINCS),
                   help="tetto della fascia; `zref` (default) e' l'incumbent "
                        "esterno da cui il cutoff e' ricavato")
    p.add_argument("--band-sel", default="killed_impr", choices=list(SELS),
                   help="quali iterazioni; `killed_impr` (default) sono "
                        "esattamente le n_killed_improving di fp.py")
    p.add_argument("--clamp", action="store_true", help="pos clampata in [0,1]")
    p.add_argument("--wtag", default="w0.05",
                   help="quale progressive usare nei .csv (w0.05 / w0.15)")
    p.add_argument("--no-variants", dest="variants", action="store_false",
                   help="salta la tabella B2 delle definizioni alternative")
    a = p.parse_args()

    fam = fam_of(a.inst_list)
    sfam = stem_map(fam)
    runs = load_runs(a.dir, fam)
    o = Out(a.latex)

    o.p(f"run letti: {len(runs)} — istanze: "
        f"{len(set(s['inst'] for s in runs))} — "
        f"csv di fascia: {len(band_files(a.dir, a.band_mode, a.band_lam, 0, a.wtag))}")
    part_A(o, runs)
    part_B(o, a.dir, sfam, a)
    part_C(o, runs)


if __name__ == "__main__":
    main()
