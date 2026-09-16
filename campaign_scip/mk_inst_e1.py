#!/usr/bin/env python3
"""Le 176 istanze di E1 della campagna fattoriale, con il loro tl e z_LP.

    python3 mk_inst_e1.py            # scrive inst_e1.txt e tl_e1.txt accanto

E1 = istanze con la griglia bracci x semi COMPLETA in results_fact.txt (le
stesse di agg_fact.main / mk_tabs_fact.py) in cui il pilota trova una
soluzione. Le definizioni sono importate da agg_fact.py, non ripetute.

  inst_e1.txt   le righe di inst_wide.txt delle sole istanze di E1, stesso formato
  tl_e1.txt     nome, TL (s) e z_LP (stringa verbatim di results_fact.txt), tab-separati:
                le campagne di verifica (job30, job31) li leggono da qui invece
                di rifare il probe del primo LP.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agg_fact as A  # noqa: E402


def main():
    runs, pilot, notes, below, dropped = A.load(os.path.join(HERE, "results_fact.txt"))
    if below:
        sys.exit("FATALE: primale sotto z_LP in results_fact.txt")
    insts, arms = A.complete_instances(runs, 5)
    e1 = [i for i in insts if pilot.get(i)]
    print("istanze complete %d, E1 %d, bracci %d" % (len(insts), len(e1), len(arms)))

    # tl e zlp: identici su tutti i bracci/semi di un'istanza (controllato)
    tlz = {}
    for ln in open(os.path.join(HERE, "results_fact.txt"), errors="replace"):
        p = ln.rstrip("\n").split("|")
        if len(p) < 4 or p[0] != "RES" or p[2] not in arms:
            continue
        d = dict(f.split("=", 1) for f in p[3:] if "=" in f)
        cur = tlz.setdefault(p[1], (d["tl"], d["zlp"]))
        if cur != (d["tl"], d["zlp"]):
            sys.exit("tl/zlp non costanti su %s: %s vs %s" % (p[1], cur, (d["tl"], d["zlp"])))

    wide = {}
    for ln in open(os.path.join(HERE, "inst_wide.txt"), errors="replace"):
        if ln.startswith("#"):
            continue
        name = os.path.basename(ln.split("\t")[2]).replace(".mps.gz", "")
        wide[name] = ln
    missing = [i for i in e1 if i not in wide]
    if missing:
        sys.exit("istanze di E1 assenti da inst_wide.txt: %s" % missing)

    with open(os.path.join(HERE, "inst_e1.txt"), "w", newline="\n") as f:
        f.write("# famiglia\tbanda\tpath\tn\tncons\tnnz\tquota_bin   (E1: 176 istanze, da mk_inst_e1.py)\n")
        for i in e1:
            f.write(wide[i])
    with open(os.path.join(HERE, "tl_e1.txt"), "w", newline="\n") as f:
        f.write("# nome\ttl\tzlp   (da results_fact.txt, mk_inst_e1.py)\n")
        for i in e1:
            f.write("%s\t%s\t%s\n" % (i, tlz[i][0], tlz[i][1]))
    print("scritti inst_e1.txt (%d righe) e tl_e1.txt" % len(e1))


if __name__ == "__main__":
    main()
