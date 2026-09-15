"""Confronto di versione dell'entrypoint all-in-one.

Decide se l'avvio e' una prima installazione, un aggiornamento o un downgrade
da bloccare: sbagliarlo non degrada nulla, impedisce al container di partire su
un'installazione sana. Il test chiama le funzioni bash vere, non una loro
riscrittura in Python.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

LIB = (
    Path(__file__).resolve().parents[3]
    / "deploy"
    / "all-in-one"
    / "rootfs"
    / "usr"
    / "local"
    / "lib"
    / "notifyhub"
    / "lib.sh"
)

BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="serve bash")


def _chiama(funzione: str, a: str, b: str) -> bool:
    # Nome della funzione e argomenti sono letterali scritti qui sotto, non
    # input: nulla di esterno raggiunge la riga di comando.
    assert BASH is not None
    script = f'set -u; source "{LIB}"; {funzione} "{a}" "{b}"'
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", script], capture_output=True, text=True
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("precedente", "immagine"),
    [
        ("0.0.2", "0.0.3"),
        ("v0.0.2", "v0.0.3"),
        # Il caso che fermava l'avvio: /data scritto da un'immagine pubblicata
        # (tag git, con la v) e immagine nuova costruita in locale (senza).
        ("v0.0.2", "0.0.3"),
        ("0.0.2", "v0.0.3"),
        ("v0.9.9", "1.0.0"),
    ],
)
def test_aggiornamento_non_viene_scambiato_per_downgrade(precedente: str, immagine: str):
    assert not _chiama("version_lt", immagine, precedente)
    assert not _chiama("version_eq", immagine, precedente)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("precedente", "immagine"),
    [
        ("0.0.3", "0.0.2"),
        ("v0.0.3", "v0.0.2"),
        ("v1.0.0", "0.9.9"),
    ],
)
def test_downgrade_resta_riconosciuto(precedente: str, immagine: str):
    assert _chiama("version_lt", immagine, precedente)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("precedente", "immagine"),
    [
        ("0.0.3", "0.0.3"),
        # Stessa versione scritta nei due modi: e' un riavvio, non un
        # aggiornamento, e non deve rifare backup e hook di versione.
        ("v0.0.3", "0.0.3"),
        ("0.0.3", "v0.0.3"),
    ],
)
def test_stessa_versione_e_un_riavvio(precedente: str, immagine: str):
    assert _chiama("version_eq", immagine, precedente)
    assert not _chiama("version_lt", immagine, precedente)
