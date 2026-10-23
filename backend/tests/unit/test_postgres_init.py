"""Script di init Postgres: il loopback non deve restare trust nel pg_hba.conf."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "deploy/postgres/initdb/20-setup-auth.sh"

# Il pg_hba.conf che initdb genera nell'immagine ufficiale (postgres:16), prima dello script.
_PG_HBA_IMMAGINE = """\
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
host    all             all             all                     scram-sha-256
"""

_LOOPBACK = {"127.0.0.1/32", "::1/128"}


@pytest.mark.unit
def test_loopback_non_resta_trust_dopo_lo_script(tmp_path):
    (tmp_path / "pg_hba.conf").write_text(_PG_HBA_IMMAGINE, encoding="utf-8")

    subprocess.run(  # noqa: S603
        [shutil.which("bash") or "/bin/bash", str(SCRIPT)],
        env={"PATH": os.environ["PATH"], "PGDATA": str(tmp_path)},
        check=True,
        timeout=30,
    )

    righe = (tmp_path / "pg_hba.conf").read_text(encoding="utf-8").splitlines()
    campi = [r.split() for r in righe if r.strip() and not r.lstrip().startswith("#")]

    host_loopback = [c for c in campi if c[0] == "host" and c[3] in _LOOPBACK]
    assert len(host_loopback) == 4  # i due 'all' e i due 'replication'
    assert all(c[4] == "scram-sha-256" for c in host_loopback)
    # La socket Unix resta trust: la usano gli script di init.
    assert campi[0] == ["local", "all", "all", "trust"]
