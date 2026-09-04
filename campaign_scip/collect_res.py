#!/usr/bin/env python3
"""Raccoglie le righe RES| dai log di una campagna, tenendo UNA sola passata per istanza.

Perche' serve. Una campagna che e' stata cancellata e rilanciata sta su due job
id (`logs/wide_4930041_*.log` e `logs/wide_4932707_*.log`), e il glob che li
prende tutti mette insieme righe di due passate. Per le righe chiavate su
(istanza, braccio, seme) l'aggregatore tiene l'ultima e non se ne accorge
nessuno; ma le righe `probe|FAIL` e `SKIP` non hanno quella chiave, e la vecchia
sopravvive accanto alla nuova. E' cosi' che `tbfp-network` risultava esclusa dal
probe mentre nella passata buona il suo primo LP si risolve in 21 secondi.

La regola qui e' per ISTANZA, non per riga: di ogni istanza si tengono le righe
del job id piu' alto che la contiene, e si buttano tutte le altre. Un job id piu'
alto e' una sottomissione successiva, quindi la passata piu' recente.

    python3 collect_res.py logs/wide_*.log > results_wide.txt
    python3 collect_res.py --stats logs/arrow_*.log > results_arrow.txt
"""
import re
import sys


def main():
    args = [a for a in sys.argv[1:] if a != "--stats"]
    stats = "--stats" in sys.argv[1:]

    # job id dal nome del file: <qualcosa>_<jobid>_<taskid>.log
    per_inst = {}
    for path in args:
        m = re.search(r"_(\d+)_(\d+)\.log$", path)
        job = int(m.group(1)) if m else 0
        try:
            f = open(path, errors="replace")
        except OSError:
            continue
        with f:
            for ln in f:
                if not ln.startswith("RES|"):
                    continue
                inst = ln.split("|", 2)[1]
                cur = per_inst.get(inst)
                if cur is None or job > cur[0]:
                    per_inst[inst] = (job, [ln])
                elif job == cur[0]:
                    cur[1].append(ln)

    n = 0
    for inst in sorted(per_inst):
        for ln in per_inst[inst][1]:
            sys.stdout.write(ln)
            n += 1
    if stats:
        jobs = sorted({v[0] for v in per_inst.values()})
        sys.stderr.write("istanze %d, righe %d, job usati %s\n"
                         % (len(per_inst), n, jobs))


if __name__ == "__main__":
    main()
