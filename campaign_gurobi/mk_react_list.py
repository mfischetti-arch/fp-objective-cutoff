#!/usr/bin/env python3
"""Lista istanze della campagna reactive (job26) dai JSON del pilota di E3
(cache del cluster ~/fpg/out/tgt23pilot/, copiata in locale).

    python mk_react_list.py <dir-json-pilota> > inst_react.txt
    python mk_react_list.py <dir-json-pilota> --slow > inst_react_slow.txt

Colonne (tab): name  mps  tlp  TL  pilot  n_bin  n_cont  zlp  zinc
  pilot = found (il pilota FGL ha trovato una soluzione) | failed (150 s a vuoto)
  TL    = clamp(20 t_LP, 20, 300), lo stesso per tutti i bracci dell'istanza.
Perimetro: 0-1 misti supportati da fp_target.load (niente intere generali,
niente SOS/quadratici); t_LP <= 5 s (--slow: 5 < t_LP <= 150, TL = 300).
Le 6 istanze col primo LP interrotto a 150 s (ds-big, rmine13/15/21,
physiciansched3-3, nsr8k) restano fuori da entrambe le liste."""
import glob
import json
import os
import sys

MPSDIR = "/nfsd/rop/instances/miplib2017"


def main():
    d = sys.argv[1]
    slow = "--slow" in sys.argv
    rows = []
    seen = set()
    for f in sorted(glob.glob(os.path.join(d, "*__pilot_*.json"))):
        j = json.load(open(f))
        # fiber e 2club200v15p5scn hanno due JSON (due righe nelle liste di E3):
        # l'indice dell'array e' la riga della lista, quindi UNA riga per nome
        if j.get("inst") in seen:
            continue
        seen.add(j.get("inst"))
        st = j.get("status")
        tlp = j.get("tlp")
        if st == "error" or tlp is None:
            continue                      # unsupported (skip) o morta prima del primo LP
        if st == "timelimit" and tlp >= 100:
            continue                      # primo LP interrotto dal budget del pilota
        if st not in ("target", "timelimit", "slow"):
            continue
        is_slow = tlp > 5
        if is_slow != slow:
            continue
        TL = 300 if slow else int(round(min(300.0, max(20.0, 20.0 * tlp))))
        pilot = "found" if st == "target" else "failed" if st == "timelimit" else "slow"
        rows.append((j["inst"], f"{MPSDIR}/{j['file']}", f"{tlp:.4f}", TL, pilot,
                     j.get("n_bin"), j.get("n_cont"), j.get("zlp"), j.get("zinc")))
    print("# name\tmps\ttlp\tTL\tpilot\tn_bin\tn_cont\tzlp\tzinc")
    print(f"# {len(rows)} istanze, {'lente (5 < t_LP <= 150 s, TL 300)' if slow else 't_LP <= 5 s'}; "
          f"pilota found={sum(r[4]=='found' for r in rows)} failed={sum(r[4]=='failed' for r in rows)} "
          f"slow={sum(r[4]=='slow' for r in rows)}; somma TL={sum(r[3] for r in rows)} s")
    for r in rows:
        print("\t".join("" if v is None else str(v) for v in r))


if __name__ == "__main__":
    main()
