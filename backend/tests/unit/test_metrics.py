"""Metriche fra processi: API e worker scrivono, il server 9100 deve vedere i loro valori."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

# Un processo a parte, come l'API o il worker: importa il modulo con la directory multiprocess
# gia' impostata (la scelta del backend dei valori avviene all'import) e incrementa il contatore.
_SCRITTORE = (
    "from app.core.metrics import ingestion_requests_total as c; c.labels(outcome='success').inc()"
)
_SCRITTORE_GAUGE = (
    "from app.core.metrics import tenant_storage_bytes as g; "
    "g.labels(tenant_id='tenant-test').set({valore})"
)


@pytest.mark.unit
def test_contatori_di_processi_separati_arrivano_al_registro_del_9100(tmp_path, monkeypatch):
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    for _ in range(2):
        subprocess.run(  # noqa: S603
            [sys.executable, "-c", _SCRITTORE],
            cwd=BACKEND,
            env=env,
            check=True,
            timeout=60,
        )

    from app.core.metrics import _registro_metriche

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    registro = _registro_metriche()

    valore = registro.get_sample_value("notifyhub_ingestion_requests_total", {"outcome": "success"})
    assert valore == 2.0


@pytest.mark.unit
def test_gauge_multiprocess_vale_l_ultima_scrittura_non_il_massimo(tmp_path, monkeypatch):
    # Il job di ricalcolo puo' dare uno spazio minore di prima: il 9100 deve mostrare il nuovo
    # valore, anche se il processo che aveva scritto il massimo e' gia' finito.
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    for valore in (10, 1):
        subprocess.run(  # noqa: S603
            [sys.executable, "-c", _SCRITTORE_GAUGE.format(valore=valore)],
            cwd=BACKEND,
            env=env,
            check=True,
            timeout=60,
        )

    from app.core.metrics import _registro_metriche

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    registro = _registro_metriche()

    valore = registro.get_sample_value(
        "notifyhub_tenant_storage_bytes", {"tenant_id": "tenant-test"}
    )
    assert valore == 1.0


@pytest.mark.unit
def test_senza_multiprocess_il_9100_usa_il_registro_del_processo(monkeypatch):
    from prometheus_client.registry import REGISTRY

    from app.core.metrics import _registro_metriche

    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    assert _registro_metriche() is REGISTRY
