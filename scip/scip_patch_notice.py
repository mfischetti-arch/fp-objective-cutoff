#!/usr/bin/env python3
"""
La nota di modifica richiesta dalla Apache License 2.0, sezione 4(b).

    python3 scip_patch_notice.py ~/scipwork/scip/src/scip/heur_feaspump.c

SCIP e' sotto Apache 2.0 dalla 8.0.3 (quindi anche la 11, quella che usiamo), e
la 4(b) dice: «You must cause any modified files to carry prominent notices
stating that You changed the files». Il nostro heur_feaspump.c e' un file
modificato, quindi la nota ci vuole -- e va messa PRIMA di impacchettare
l'artefatto per MPC, non dopo.

Non tocca il codice: solo un commento in testa. Idempotente.

⚠️ Da applicare quando NESSUNA campagna sta girando: modificare il sorgente non
cambia il binario gia' compilato, ma un `make` successivo si', e i job in coda
userebbero un binario diverso da quello dei job gia' finiti.
"""
import io
import sys

NOTICE = """/* NOTICE (Apache License 2.0, section 4(b)): this file has been MODIFIED with
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
"""


def main():
    path = sys.argv[1]
    s = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if "section 4(b)" in s:
        print("gia' applicata, non faccio nulla")
        return 0
    if "tryrounded" not in s:
        print("ERRORE: questo non e' il nostro heur_feaspump.c modificato")
        return 1
    io.open(path, "w", encoding="utf-8", errors="surrogateescape").write(NOTICE + s)
    print(f"nota di modifica aggiunta in testa a {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
