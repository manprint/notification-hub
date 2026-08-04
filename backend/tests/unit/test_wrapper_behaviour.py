"""Comportamento dello script wrapper, eseguito davvero.

Finora del wrapper era coperta la forma (il rendering del template), non la
logica: e' un file bash che gira su macchine altrui dentro cron, e gli errori li
scopre l'operatore quando il job non parla piu'. `--dry-run` permette di
verificarlo senza rete e senza NotifyHub.
"""

import subprocess
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[3] / "scripts" / "notifyhub-run.sh"
SLUG = "maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    ambiente = {**os.environ, "NOTIFYHUB_URL": "https://notifyhub.com", "NOTIFYHUB_SLUG": SLUG}
    ambiente.update(env or {})
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(WRAPPER), "--dry-run", *args],
        capture_output=True,
        text=True,
        env=ambiente,
    )


@pytest.mark.unit
def test_il_wrapper_esiste_ed_e_bash_valido():
    assert WRAPPER.is_file(), f"wrapper non trovato in {WRAPPER}"
    esito = subprocess.run(  # noqa: S603
        ["/bin/bash", "-n", str(WRAPPER)], capture_output=True, text=True
    )
    assert esito.returncode == 0, esito.stderr


@pytest.mark.unit
def test_invio_normale_dichiara_esito_durata_e_fase():
    esito = _run("--", "echo", "prova")
    assert esito.returncode == 0
    assert f"--- POST https://notifyhub.com/ingest/{SLUG}" in esito.stdout
    assert "--- X-Phase: end" in esito.stdout
    assert "--- X-Exit-Code: 0" in esito.stdout
    assert "--- X-Duration-Ms: " in esito.stdout
    # Nessun ping di avvio se non lo si chiede.
    assert "X-Phase: start" not in esito.stdout


@pytest.mark.unit
def test_exit_code_del_comando_arriva_al_chiamante():
    """La proprieta' che rende il wrapper trasparente in cron: l'esito e' quello
    del comando avvolto, non quello dell'invio."""
    esito = _run("--", "bash", "-c", "exit 3")
    assert esito.returncode == 3
    assert "--- X-Exit-Code: 3" in esito.stdout


@pytest.mark.unit
def test_ping_di_avvio_precede_la_conclusione():
    esito = _run("--ping-start", "--", "echo", "prova")
    assert esito.returncode == 0
    assert esito.stdout.index("X-Phase: start") < esito.stdout.index("X-Phase: end")
    # L'avvio non e' un esito: severity debug esplicita, nessun exit code.
    avvio = esito.stdout.split("X-Phase: end")[0]
    assert "X-Severity: debug" in avvio
    assert "X-Exit-Code" not in avvio
    assert "avvio host=" in avvio


@pytest.mark.unit
@pytest.mark.parametrize("valore", ["1", "true", "TRUE", "yes", "on"])
def test_ping_di_avvio_dallambiente(valore):
    """`NOTIFYHUB_PING_START=true` veniva ignorato in silenzio: l'unico valore
    riconosciuto era "1", e chi esporta una variabile booleana non lo immagina."""
    esito = _run("--", "echo", "prova", env={"NOTIFYHUB_PING_START": valore})
    assert "X-Phase: start" in esito.stdout


@pytest.mark.unit
@pytest.mark.parametrize("valore", ["0", "false", "no", "", "boh"])
def test_ambiente_non_riconosciuto_non_manda_ping(valore):
    esito = _run("--", "echo", "prova", env={"NOTIFYHUB_PING_START": valore})
    assert "X-Phase: start" not in esito.stdout


@pytest.mark.unit
def test_avviso_su_ping_start_con_only_on_failure():
    """La combinazione produce il quadro di un job che muore a meta' ogni volta
    che va bene: avvii sempre, conclusioni solo sui fallimenti."""
    esito = _run("--ping-start", "--only-on-failure", "--", "echo", "prova")
    assert "--only-on-failure" in esito.stderr
    assert "--severity-ok debug" in esito.stderr
    # Resta un avviso, non un errore: non si spegne il cron di nessuno.
    assert esito.returncode == 0


@pytest.mark.unit
def test_only_on_failure_da_solo_non_avvisa():
    esito = _run("--only-on-failure", "--", "echo", "prova")
    assert "notifyhub-run:" not in esito.stderr


@pytest.mark.unit
def test_severity_non_valida_rifiutata_prima_di_eseguire():
    esito = _run("--severity", "catastrofica", "--", "echo", "non-deve-girare")
    assert esito.returncode == 2
    assert "severity non valida" in esito.stderr
    assert "non-deve-girare" not in esito.stdout


@pytest.mark.unit
def test_slug_mancante_rifiutato():
    esito = _run("--", "echo", "prova", env={"NOTIFYHUB_SLUG": ""})
    assert esito.returncode == 2
    assert "slug del receiver mancante" in esito.stderr


@pytest.mark.unit
def test_durata_leggibile_nel_corpo():
    esito = _run("--", "echo", "prova")
    # `durata=0.00Xs (Yms)`: la forma leggibile e il dato grezzo insieme.
    assert "durata=" in esito.stdout
    assert "ms)" in esito.stdout


@pytest.mark.unit
def test_output_del_comando_finisce_nel_corpo():
    esito = _run("--", "bash", "-c", "echo su-stdout; echo su-stderr >&2")
    assert "su-stdout" in esito.stdout
    # stdout e stderr uniti: chi legge la notifica vuole il log completo.
    assert "su-stderr" in esito.stdout


@pytest.mark.unit
def test_url_con_slash_finale_non_raddoppia():
    esito = _run("--", "echo", "prova", env={"NOTIFYHUB_URL": "https://notifyhub.com/"})
    assert f"--- POST https://notifyhub.com/ingest/{SLUG}" in esito.stdout
    assert "//ingest" not in esito.stdout
