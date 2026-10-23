"""Test di notifyhub-logpipe: il file di log non si spegne per sempre dopo un errore.

Lo script non ha estensione .py: si carica come modulo dal suo percorso. Si
esegue con `pytest -c /dev/null` dalla radice del repository, cosi' non si
applicano le opzioni di pytest del backend.
"""

from __future__ import annotations

import errno
import importlib.machinery
import importlib.util
from pathlib import Path

LOGPIPE = Path(__file__).resolve().parents[1] / "rootfs" / "usr" / "local" / "bin" / "notifyhub-logpipe"


def _carica_logpipe():
    loader = importlib.machinery.SourceFileLoader("notifyhub_logpipe", str(LOGPIPE))
    spec = importlib.util.spec_from_loader("notifyhub_logpipe", loader)
    modulo = importlib.util.module_from_spec(spec)
    loader.exec_module(modulo)
    return modulo


class _HandleGuasto:
    """Avvolge un file reale e fallisce una sola volta in scrittura, come con ENOSPC."""

    def __init__(self, reale):
        self._reale = reale
        self._guasto = True

    def write(self, dati):
        if self._guasto:
            self._guasto = False
            raise OSError(errno.ENOSPC, "No space left on device")
        return self._reale.write(dati)

    def flush(self):
        return self._reale.flush()

    def tell(self):
        return self._reale.tell()

    def close(self):
        return self._reale.close()


def test_dopo_un_errore_di_scrittura_le_righe_successive_arrivano_nel_file(tmp_path):
    logpipe = _carica_logpipe()
    percorso = tmp_path / "api" / "api.log"
    sink = logpipe.RotatingLog(str(percorso), max_bytes=0, backups=1)
    sink.handle = _HandleGuasto(sink.handle)

    sink.write("riga persa per ENOSPC")
    sink.write("riga successiva")
    sink.write("ancora una riga")

    contenuto = percorso.read_text(encoding="utf-8")
    assert "riga successiva" in contenuto
    assert "ancora una riga" in contenuto
    assert "riga persa per ENOSPC" not in contenuto


def test_il_file_si_riapre_se_l_apertura_iniziale_fallisce(tmp_path):
    logpipe = _carica_logpipe()
    percorso = tmp_path / "beat" / "beat.log"
    sink = logpipe.RotatingLog(str(percorso), max_bytes=0, backups=1)
    # Simula /logs non scrivibile al primo tentativo: il file resta chiuso.
    sink.handle = None
    sink.write("persa")

    sink.write("dopo il ripristino del volume")

    assert "dopo il ripristino del volume" in percorso.read_text(encoding="utf-8")
