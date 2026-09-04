#!/usr/bin/env python3
"""Lista delle istanze per l'esperimento "target" su GUROBI (campagna 23).

Differenza con mk_target_list.py (campagna 22, su SCIP): qui la lista NON dipende
dal pilota. Il pilota (fp_target.py --mode pilot) gira DENTRO il task SLURM
(PHASE=recon di job23_gurobi.sh), che decide li' l'eleggibilita' dell'istanza --
sei motivi di scarto, tenuti DISTINTI perche' dicono cose diverse:

    - l'istanza e' nel perimetro della pompa binaria (niente intere generali,
      niente vincoli quadratici/SOS/generali)      -> altrimenti SKIP|unsupported
    - il pilota trova una soluzione entro 150 s    -> altrimenti SKIP|nopilot
    - il primo LP costa t_LP <= TLP_MAX (5 s)      -> altrimenti SKIP|slow
    - il pilota e' strettamente peggiore di z_best -> altrimenti SKIP|at_best
    - z_best NON sta sotto il bound LP di radice   -> altrimenti SKIP|best_below_lp
      (dato sporco: i due numeri non si riferiscono allo stesso modello, come in
      app2-1 e drayage-100-23; U cadrebbe sotto il bound e nessuna soluzione con
      c'x <= U esisterebbe)
    - |z_inc - z_LP| non e' nullo                  -> altrimenti SKIP|zero_gap
      (senza gap non c'e' nessuna fascia da scavare: U' ~ U ~ z_LP)

Gli ultimi due hanno bisogno di z_LP, che solo il pilota conosce: per questo
stanno nel task e non qui, dove mk_target_list.py li faceva a monte.

Quindi la lista porta solo cio' che si sa PRIMA di far girare qualcosa: il nome,
il path del modello, il miglior valore noto di MIPLIB 2017 e la divisione
taratura/valutazione.

z_best e' quello di miplib2017.solu (righe =opt= e =best=) ed e' nel senso
ORIGINALE del modello: il task lo NEGA se il modello e' di massimo (il JSON del
pilota riporta "maximize"), perche' fp_target.py converte tutto a minimo.

Divisione ESOGENA (prassi di Nair et al. 2020, arXiv:2012.13349): il MIPLIB 2017
Benchmark Set (benchmark-v2.test) e' SOLO valutazione; le NTUNE=20 istanze di
TARATURA di w sono estratte a caso (seme 4242) fra quelle FUORI dal benchmark;
tutte le altre vanno in valutazione, con le istanze del benchmark come test
primario e le restanti come test secondario.

    python mk_target23.py > inst_target23.txt

Il file NON e' nel repo: va rigenerato prima di ogni campagna e copiato sul
cluster insieme a fp_target.py, fp.py, benchmark-v2.test e miplib2017.solu.
L'--array di job23_gurobi.sh e' dimensionato sulle sue righe di dati (430 al
03/09/2026): se la lista cambia, riallineare 0-429.

Colonne (tab):  set  name  mps  zbest  bench
  set    "tune" | "eval"
  zbest  miglior valore noto MIPLIB 2017, senso ORIGINALE del modello
  bench  1 se l'istanza sta nel MIPLIB 2017 Benchmark Set, 0 altrimenti
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NTUNE = int(os.environ.get("NTUNE", "20"))
SEED = int(os.environ.get("SEED", "4242"))
WIDE = os.environ.get("WIDE", "inst_wide.txt")
# ELIGIBLE: file con i nomi (uno per riga) delle istanze giudicate eleggibili
# dalla fase di ricognizione (PHASE=recon: pilota, t_LP, at_best, ...). Se
# dato, la lista contiene SOLO quelle, e le NTUNE di taratura sono estratte a
# caso fra le eleggibili fuori benchmark: senza, un terzo delle righe di
# taratura sarebbe sprecato in SKIP (03/09/2026: 147 eleggibili su 410).
# L'eleggibilita' non dipende da tune/eval ne' da a, quindi il filtro non
# guarda i risultati e non contamina la divisione.
ELIGIBLE = os.environ.get("ELIGIBLE", "")


def stem(path):
    n = os.path.basename(path.strip())
    for suf in (".mps.gz", ".mps"):
        if n.endswith(suf):
            return n[:-len(suf)]
    return n


def main():
    solu = {}
    for ln in open(os.path.join(HERE, "miplib2017.solu")):
        p = ln.split()
        if len(p) >= 3 and p[0] in ("=opt=", "=best="):
            solu[p[1]] = float(p[2])

    bench = set()
    for ln in open(os.path.join(HERE, "benchmark-v2.test")):
        n = stem(ln)
        if n:
            bench.add(n)

    elig = None
    if ELIGIBLE:
        elig = set(stem(ln) for ln in open(os.path.join(HERE, ELIGIBLE)) if ln.strip())

    rows, seen = [], set()
    skipped = {"no_best": 0, "dup": 0, "not_eligible": 0}
    for ln in open(os.path.join(HERE, WIDE)):
        if ln.startswith("#"):
            continue
        f = ln.rstrip("\n").split("\t")
        if len(f) < 3 or not f[2].strip():
            continue
        path = f[2].strip()
        n = stem(path)
        if n in seen:
            skipped["dup"] += 1
            continue
        seen.add(n)
        if n not in solu:
            # z_best assente, o riga =inf= / =unbd= / =unkn=: senza z_best non si
            # puo' costruire U, l'istanza non entra nell'esperimento
            skipped["no_best"] += 1
            continue
        if elig is not None and n not in elig:
            skipped["not_eligible"] += 1
            continue
        rows.append((n, path, solu[n]))
    rows.sort()

    nonbench = [x for x in rows if x[0] not in bench]
    rnd = random.Random(SEED)
    tune = set(x[0] for x in rnd.sample(nonbench, min(NTUNE, len(nonbench))))

    nb = sum(1 for x in rows if x[0] in bench)
    print("# set\tname\tmps\tzbest\tbench")
    print("# NTUNE=%d SEED=%d WIDE=%s ELIGIBLE=%s  candidate=%d (benchmark=%d, fuori benchmark=%d)"
          "  scartate=%s  --  eleggibilita' (pilota, t_LP, at_best) decisa NEL TASK%s"
          % (NTUNE, SEED, WIDE, ELIGIBLE or "-", len(rows), nb, len(nonbench), skipped,
             " e qui gia' filtrata con ELIGIBLE" if elig is not None else ""))
    for n, path, zb in rows:
        print("\t".join([("tune" if n in tune else "eval"), n, path,
                         "%.15g" % zb, "1" if n in bench else "0"]))
    print("candidate: %d (tune %d fuori benchmark, eval %d di cui %d benchmark = test "
          "primario); scartate: %s" % (len(rows), len(tune), len(rows) - len(tune),
                                       nb, skipped), file=sys.stderr)


if __name__ == "__main__":
    main()
