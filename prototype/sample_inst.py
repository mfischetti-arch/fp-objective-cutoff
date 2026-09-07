#!/usr/bin/env python3
"""
Campionamento stratificato delle istanze binarie pure dal censimento.

    python sample_inst.py --per-family 20 --out inst_list.txt

Stratifica per famiglia e, dentro la famiglia, per taglia (<1k, 1k-10k, >10k
variabili), cosi' il campione non finisce tutto sulle istanze piccole. Seed
fisso: la lista e' riproducibile e va versionata insieme ai risultati.
"""
import argparse
import csv
import os
import random

FAM = {"miplib2017": "/nfsd/rop/instances/miplib2017",
       "miplib2003": "/nfsd/rop/instances/miplib2003",
       "ORLib_setcover": "/nfsd/rop/instances/ORLib/setcover"}
HERE = os.path.dirname(os.path.abspath(__file__))


def band(n):
    return "<1k" if n < 1000 else "1k-10k" if n < 10000 else ">10k"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-dir", default=os.path.join(HERE, "scan"))
    ap.add_argument("--per-family", type=int, default=20)
    ap.add_argument("--max-n", type=int, default=50000)
    ap.add_argument("--max-nnz", type=int, default=2_000_000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=os.path.join(HERE, "inst_list.txt"))
    a = ap.parse_args()

    rng = random.Random(a.seed)
    picked = []
    for fam, root in FAM.items():
        rows = [r for r in csv.DictReader(open(f"{a.scan_dir}/scan_{fam}.csv"))
                if r["status"] == "ok" and int(r["nint"]) == 0 and int(r["ncont"]) == 0
                and 50 <= int(r["n"]) <= a.max_n and 10 <= int(r["ncons"]) <= 50000
                and int(r["nnz"]) <= a.max_nnz]
        strata = {}
        for r in rows:
            strata.setdefault(band(int(r["n"])), []).append(r)
        # quota proporzionale allo strato, ma almeno 1 per strato non vuoto
        tot = len(rows)
        quota = {b: max(1, round(a.per_family * len(v) / tot)) for b, v in strata.items()}
        for b, v in sorted(strata.items()):
            k = min(quota[b], len(v))
            for r in sorted(rng.sample(v, k), key=lambda r: r["inst"]):
                # "/" esplicito: la lista si genera su Windows e si usa sul
                # cluster, os.path.join scriverebbe backslash inservibili
                picked.append((fam, b, f"{root}/{r['inst']}",
                               r["n"], r["ncons"], r["nnz"]))

    with open(a.out, "w") as f:
        f.write("# famiglia\tbanda\tpath\tn\tncons\tnnz\n")
        for p in picked:
            f.write("\t".join(str(x) for x in p) + "\n")

    from collections import Counter
    c = Counter((p[0], p[1]) for p in picked)
    print(f"{len(picked)} istanze in {a.out}")
    for k in sorted(c):
        print(f"  {k[0]:16s} {k[1]:7s} {c[k]}")


if __name__ == "__main__":
    main()
