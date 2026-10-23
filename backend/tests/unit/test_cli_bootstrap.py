"""CLI bootstrap: la password passa la stessa policy dell'API, prima di toccare il DB."""

import pytest
from click.testing import CliRunner

from app import cli as cli_module


@pytest.mark.unit
def test_bootstrap_rifiuta_password_sotto_i_12_caratteri(monkeypatch):
    chiamate: list[tuple] = []

    async def spia(*args) -> None:
        chiamate.append(args)

    monkeypatch.setattr(cli_module, "_bootstrap", spia)
    esito = CliRunner().invoke(
        cli_module.cli,
        [
            "bootstrap",
            "--tenant-name",
            "ACME",
            "--email",
            "owner@acme-notifyhub.com",
            "--password",
            "corta-1",
        ],
    )
    assert esito.exit_code != 0
    assert "12" in esito.output
    # Nessun tenant creato: la validazione avviene prima di _bootstrap.
    assert chiamate == []
