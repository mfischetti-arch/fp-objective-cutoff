#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregato della campagna Q3: la rounding moat ADATTIVA (test-adapt /
completion-adapt di fp_target.py) contro i bracci di E3.

DA DOVE VENGONO I NUMERI
    results/eval50.res, results/eval90.res      E3: naive, test(w), completion(w)
    results/eval50_adapt.res, eval90_adapt.res  regola freeze (primaria):
                                                naive RIFATTO + test-adapt:freeze
                                                + completion-adapt:freeze
    results/eval50_adaptr.res, eval90_adaptr.res regola running (secondaria):
                                                naive RIFATTO + i due -adapt:running
    results/eval50_adapta.res, eval90_adapta.res regola abs (esplorativa, fascia =
                                                mediana di |delta|): naive RIFATTO +
                                                i due -adapt:abs
    Ogni file adapt viene da UNA campagna (job27_adapt.sh): i tre bracci di un
    seme girano insieme sulla stessa lama, e il naive rifatto e' il controllo
    nella stessa contesa.

DEFINIZIONI: quelle di mk_tab_target.py / agg_target23.py, IMPORTATE e non
ridefinite: esito per (istanza, braccio) = mediana di target_ok (e validated)
sui 5 semi, "solved" se >= 3/5; coppie = (istanza, seme) riuscite; W/T/L
appaiato sull'esito; p = test del segno esatto bilaterale sulle non-parita';
"faster" = fra le istanze risolte da entrambi, tempo mediano censurato piu'
basso di almeno il 5%; famiglie benchmark (43) / non-benchmark (91) / all
(134); pure (n_cont=0) / mixed (n_cont>0). Holm sulla famiglia dichiarata: 2 a
x 2 famiglie (benchmark, non-benchmark) x 4 confronti della regola freeze
(test-adapt e completion-adapt, ciascuno vs naive di E3 e vs il proprio
braccio a w fisso) = 16 test; la regola running e' esplorativa, senza Holm.

USO
    python agg_adapt.py            stampa le tabelle in markdown (per il rapporto)
    python agg_adapt.py --md FILE  le scrive anche su FILE
"""

import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg_target23 as agg   # noqa: E402
import mk_tab_target as mk   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
ALPHAS = (("0.5", "eval50.res", "eval50_adapt.res", "eval50_adaptr.res", "eval50_adapta.res"),
          ("0.9", "eval90.res", "eval90_adapt.res", "eval90_adaptr.res", "eval90_adapta.res"))
RULES = ("freeze", "running", "abs")
NEW = {"freeze": ("test-adapt:freeze", "completion-adapt:freeze"),
       "running": ("test-adapt:running", "completion-adapt:running"),
       "abs": ("test-adapt:abs", "completion-adapt:abs")}
FIXED_OF = {"test-adapt": "test", "completion-adapt": "completion"}
SUBSETS = mk.SUBSETS
FAMILIES = (("benchmark", "primario"), ("non-benchmark", "secondario"), ("all", "tutte"))
KINDS = (("pure 0-1", "puro"), ("mixed", "misto"))


# ------------------------------------------------------------------ lettura

def load_adapt(path, rule, base_rows):
    """Righe RES di una campagna adapt, rietichettate: naive -> 'naive:re-<rule>',
    test-adapt/completion-adapt -> '<mode>:<rule>'. Invarianti propri (i tre
    bracci per (istanza, seme), U e tl uguali a E3, nessun errore)."""
    mism = {}          # istanza -> (tl di E3, tl di questa campagna): NON fatale
    if not os.path.exists(path):
        return [], ["file assente: %s" % path], mism
    L = agg.read_logs([path])
    rows = [r for r in L.rows if r.dataset == "eval"]
    bad = ["FAIL %s: %s" % f for f in L.fails]
    bad += ["SKIP %s: %s" % s for s in L.skips]
    base_U = {}
    base_tl = {}
    for r in base_rows:
        base_U[r.inst] = agg.fnum(r.kv, "U")
        base_tl[r.inst] = r.tl
    by_seed = defaultdict(Counter)
    for r in rows:
        if r.mode == "naive":
            r.mode = "naive:re-" + rule
        elif r.mode in FIXED_OF:
            if r.w_str != rule:
                bad.append("%s/%s: regola %s in un file %s [%s]" % (r.inst, r.mode, r.w_str, rule, r.src))
            r.mode = "%s:%s" % (r.mode, r.w_str)
        else:
            bad.append("%s: braccio inatteso %s [%s]" % (r.inst, r.mode, r.src))
        U = agg.fnum(r.kv, "U")
        if r.inst not in base_U:
            bad.append("%s: istanza non in E3 [%s]" % (r.inst, r.src))
        else:
            if U is None or not agg.close(U, base_U[r.inst]):
                bad.append("%s/%s: U=%s diverso da E3 (%s) [%s]" % (r.inst, r.mode, U, base_U[r.inst], r.src))
            if r.tl is None or abs(r.tl - base_tl[r.inst]) > 1e-9:
                # il pilota in cache e' stato rifatto dopo E3 (stesso z_inc, t_LP
                # diverso): TL diverso, confronto con E3 confondato su questa
                # istanza. Si registra e si ESCLUDE dai confronti con i bracci di
                # E3 (non da quelli col naive rifatto, che ha lo stesso TL).
                mism[r.inst] = (base_tl[r.inst], r.tl)
        if r.kv.get("status") == "error":
            bad.append("%s/%s/seed=%s: status=error (%s) [%s]"
                       % (r.inst, r.mode, r.seed, r.kv.get("error", "?")[:60], r.src))
        by_seed[(r.inst, r.seed)][r.mode] += 1
    want = ("naive:re-" + rule,) + NEW[rule]
    for (inst, sd), c in sorted(by_seed.items(), key=lambda t: (t[0][0], t[0][1] or 0)):
        miss = [a for a in want if c[a] == 0]
        dup = [a for a in want if c[a] > 1]
        if miss:
            bad.append("%s/seed=%s: bracci mancanti %s" % (inst, sd, ",".join(miss)))
        if dup:
            bad.append("%s/seed=%s: bracci duplicati %s" % (inst, sd, ",".join(dup)))
    insts = {r.inst for r in rows}
    missing_inst = sorted(set(base_U) - insts)
    if missing_inst:
        bad.append("istanze di E3 senza righe adapt: %d (%s...)" % (len(missing_inst), ", ".join(missing_inst[:5])))
    return rows, bad, mism


# ------------------------------------------------------------------ statistiche

def paired(summ, insts, A, B):
    w, l, t = mk.outcome_wlt(summ, insts, A, B)
    return {"A": A, "B": B, "n": len(insts), "w": w, "l": l, "t": t,
            "p": agg.binom_sign_p(w, w + l),
            "faster": mk.faster_wlt(summ, insts, A, B)}


def moat_stats(rows, arm):
    """Diagnostica della fascia sui run di un braccio adattivo: w_eff = moat/G."""
    rr = [r for r in rows if r.mode == arm]
    weff = [agg.fnum(r.kv, "w_eff") for r in rr]
    weff = [x for x in weff if x is not None]
    nd = [agg.inum(r.kv, "n_delta") for r in rr]
    k = [agg.inum(r.kv, "adapt_k") for r in rr]
    short = sum(1 for a, b in zip(nd, k) if a is not None and b is not None and a < b)
    zero = sum(1 for x in weff if x <= 1e-12)
    # fascia nulla fra i run che hanno RAGGIUNTO i K giri di misura (mediana dei delta <= 0)
    zero_long = sum(1 for r in rr
                    if (agg.fnum(r.kv, "w_eff") or 0.0) <= 1e-12
                    and (agg.inum(r.kv, "n_delta") or 0) >= (agg.inum(r.kv, "adapt_k") or 1))
    ws = sorted(weff)

    def q(p):
        if not ws:
            return float("nan")
        return ws[min(len(ws) - 1, int(round(p * (len(ws) - 1))))]
    return {"n": len(rr), "short": short, "zero": zero, "zero_long": zero_long,
            "q25": q(0.25), "med": q(0.5),
            "q75": q(0.75), "q90": q(0.9), "max": ws[-1] if ws else float("nan")}


def rerun_agreement(rows_new, rows_base, rule):
    """Il naive rifatto contro il naive di E3, coppia per coppia."""
    base = {(r.inst, r.seed): r for r in rows_base if r.mode == "naive"}
    new = {(r.inst, r.seed): r for r in rows_new if r.mode == "naive:re-" + rule}
    same = diff = 0
    ratio = []
    for k, r in new.items():
        b = base.get(k)
        if b is None:
            continue
        if r.ok == b.ok:
            same += 1
        else:
            diff += 1
        if r.ok and b.ok and r.tts and b.tts and b.tts > 0.5:
            ratio.append(r.tts / b.tts)
    ratio.sort()
    med = ratio[len(ratio) // 2] if ratio else float("nan")
    return same, diff, med, len(ratio)


# ------------------------------------------------------------------ tabelle

def fmt_p(p):
    return "<0.001" if p < 5e-4 else "%.3f" % p


def collect():
    out = {}
    for a, base_f, f_f, f_r, f_a in ALPHAS:
        base = mk.load(os.path.join(RES, base_f))
        wfix = mk.arm_widths(base)
        allrows = list(base)
        bad_all = []
        rules_ok = []
        adapt_rows = {}
        mism_all = {}
        for rule, fn in (("freeze", f_f), ("running", f_r), ("abs", f_a)):
            rows, bad, mism = load_adapt(os.path.join(RES, fn), rule, base)
            adapt_rows[rule] = rows
            mism_all.update(mism)
            if rows:
                rules_ok.append(rule)
                allrows += rows
            bad_all += ["[%s] %s" % (rule, b) for b in bad]
        summ, info = agg.build_summary(allrows)
        d = {"wfix": wfix, "summ": summ, "info": info, "rules": rules_ok, "bad": bad_all,
             "tl_mismatch": mism_all,
             "subsets": {lab: agg.select(info, fam, kind) for lab, fam, kind in SUBSETS},
             "outcome": {}, "paired": defaultdict(list), "moat": {}, "rerun": {}}
        arms = ["naive", "test", "completion"]
        for rule in rules_ok:
            arms += ["naive:re-" + rule] + list(NEW[rule])
        d["arms"] = arms
        for lab, _, _ in SUBSETS:
            for arm in arms:
                d["outcome"][(lab, arm)] = mk.outcome_cell(summ, d["subsets"][lab], arm)
        for rule in rules_ok:
            for fam_lab, fam in FAMILIES + KINDS:
                insts = (agg.select(info, fam, "tutte") if fam in ("primario", "secondario", "tutte")
                         else agg.select(info, "tutte", fam))
                insts_e3 = [i for i in insts if i not in mism_all]   # stesso TL di E3
                for arm in NEW[rule]:
                    mode = arm.split(":")[0]
                    d["paired"][(rule, fam_lab)].append(paired(summ, insts, arm, "naive:re-" + rule))
                    d["paired"][(rule, fam_lab)].append(paired(summ, insts_e3, arm, "naive"))
                    d["paired"][(rule, fam_lab)].append(paired(summ, insts_e3, arm, FIXED_OF[mode]))
            for arm in NEW[rule]:
                d["moat"][arm] = moat_stats(adapt_rows[rule], arm)
            d["rerun"][rule] = rerun_agreement(adapt_rows[rule], base, rule)
        out[a] = d
    # Holm sui 16 test dichiarati (freeze, benchmark/non-benchmark, vs naive e vs w fisso)
    fam = []
    for a in out:
        for fam_lab in ("benchmark", "non-benchmark"):
            for e in out[a]["paired"].get(("freeze", fam_lab), []):
                if not e["B"].startswith("naive:re-"):
                    fam.append(e)
    if fam:
        for e, ph in zip(fam, agg.holm([e["p"] for e in fam])):
            e["p_holm"] = ph
    return out


def render(data):
    L = []
    for a in (t[0] for t in ALPHAS):
        d = data[a]
        L.append("### a = %s" % a)
        L.append("")
        if d["bad"]:
            L.append("Invarianti violate (%d):" % len(d["bad"]))
            for b in d["bad"][:15]:
                L.append("- ❌ " + b)
            L.append("")
        mm = d["tl_mismatch"]
        if mm:
            L.append("- ⚠️ %d istanze con TL diverso da E3 (pilota in cache rifatto dopo E3: stesso z_inc e U, "
                     "t_LP diverso): escluse dai confronti con i bracci di E3, tenute in quelli col naive "
                     "rifatto (stesso TL). E3→ora: %s"
                     % (len(mm), ", ".join("%s %g→%g" % (i, mm[i][0], mm[i][1]) for i in sorted(mm))))
        for rule in d["rules"]:
            same, diff, med, nr = d["rerun"][rule]
            L.append("- naive rifatto (campagna %s) vs naive di E3: stesso esito su %d coppie, diverso su %d; "
                     "rapporto mediano dei tempi (coppie riuscite da entrambi con t_E3 > 0.5 s, n=%d): %.2f"
                     % (rule, same, diff, nr, med))
        L.append("")
        wf = d["wfix"]
        L.append("**Tabella A%s. Esiti per braccio, a = %s** (solved = istanze con mediana dei 5 semi = 1, "
                 "cioe' >= 3/5 semi riusciti; pairs = coppie (istanza, seme) riuscite su 5N; "
                 "E3: naive, test w=%s, completion w=%s; re-freeze/re-running = naive rifatto nella campagna "
                 "adattiva corrispondente, sulla stessa lama dei bracci adattivi; K = 5 giri di misura)."
                 % (a.replace(".", ""), a, wf["test"], wf["completion"]))
        L.append("")
        arms = d["arms"]
        L.append("| subset | N | " + " | ".join(arms) + " |")
        L.append("|---|---:|" + "|".join(["---:"] * len(arms)) + "|")
        for lab, _, _ in SUBSETS:
            n = len(d["subsets"][lab])
            cells = []
            for arm in arms:
                s, ok, tot = d["outcome"][(lab, arm)]
                cells.append("%d (%d/%d)" % (s, ok, tot))
            L.append("| %s | %d | %s |" % (lab, n, " | ".join(cells)))
        L.append("")
        for rule in d["rules"]:
            L.append("**Tabella B%s-%s. Confronti appaiati, a = %s, regola %s** (W/T/L = istanze su cui il primo "
                     "braccio vince/pareggia/perde sull'esito mediano; p = test del segno esatto bilaterale sulle "
                     "non-parita'; p_Holm sui 16 test dichiarati (solo freeze, benchmark e non-benchmark, vs naive "
                     "di E3 e vs w fisso); faster W/T/L = fra le istanze risolte da entrambi, tempo mediano piu' basso "
                     "di almeno il 5%%; naive:re-* = naive rifatto sulla stessa lama, N = tutte le istanze; "
                     "vs naive/test/completion di E3: N = sole istanze con lo stesso TL di E3)."
                     % (a.replace(".", ""), rule[0], a, rule))
            L.append("")
            L.append("| family | comparison | N | W/T/L | p | p_Holm | faster W/T/L |")
            L.append("|---|---|---:|---:|---:|---:|---:|")
            for fam_lab, _ in FAMILIES + KINDS:
                for e in d["paired"][(rule, fam_lab)]:
                    ph = fmt_p(e["p_holm"]) if "p_holm" in e else "-"
                    fw, fl, ft = e["faster"]
                    L.append("| %s | %s vs %s | %d | %d/%d/%d | %s | %s | %d/%d/%d |"
                             % (fam_lab, e["A"], e["B"], e["n"], e["w"], e["t"], e["l"],
                                fmt_p(e["p"]), ph, fw, ft, fl))
            L.append("")
        L.append("**Tabella C%s. La fascia effettiva, a = %s** (per run: w_eff = moat/(U - z_LP), la fascia "
                 "applicata alla fine della corsa in unita' di gap; short = run finiti prima dei K = 5 giri di "
                 "misura, quindi mai con fascia; zero moat (all) = run con w_eff = 0, short compresi; zero moat (>=K) = run arrivati a K giri con mediana dei delta <= 0, cioe' fascia nulla, su quelli arrivati a K; quantili "
                 "di w_eff su tutti i run del braccio)." % (a.replace(".", ""), a))
        L.append("")
        L.append("| arm | runs | short (<K) | zero moat (all) | zero moat (>=K) | q25 | median | q75 | q90 | max |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for arm, m in d["moat"].items():
            L.append("| %s | %d | %d | %d | %d/%d | %.3f | %.3f | %.3f | %.3f | %.3f |"
                     % (arm, m["n"], m["short"], m["zero"], m["zero_long"], m["n"] - m["short"],
                        m["q25"], m["med"], m["q75"], m["q90"], m["max"]))
        L.append("")
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description="aggregato della campagna Q3 (moat adattiva)")
    p.add_argument("--md", default=None, help="scrive le tabelle markdown su questo file")
    args = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass
    data = collect()
    text = render(data)
    print(text)
    nbad = sum(len(data[a]["bad"]) for a in data)
    print("invarianti: %s" % ("tutte verificate" if nbad == 0 else "%d violazioni" % nbad))
    if args.md:
        with open(args.md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    return 0 if nbad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
