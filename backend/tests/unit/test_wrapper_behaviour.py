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


# --- Robustezza (review 2026-09) -------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("opzione", ["-s", "--url", "--timeout", "--max-bytes", "--retries"])
def test_opzione_senza_valore_in_coda_esce_subito(opzione):
    """`shift 2` falliva in silenzio con un solo argomento rimasto: il ciclo
    delle opzioni girava per sempre al 100% di CPU."""
    esito = subprocess.run(  # noqa: S603
        ["/bin/bash", str(WRAPPER), opzione],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert esito.returncode == 2
    assert "richiede un valore" in esito.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    ("opzione", "valore"),
    [
        ("--max-bytes", "abc"),
        ("--connect-timeout", "abc"),
        ("--connect-timeout", "0"),
        ("--retries", "-1"),
        ("--timeout", "5x"),
    ],
)
def test_valori_numerici_non_validi_rifiutati_prima_di_eseguire(opzione, valore):
    esito = _run(opzione, valore, "--", "echo", "NON-DEVE-GIRARE")
    assert esito.returncode == 2
    assert "NON-DEVE-GIRARE" not in esito.stdout


@pytest.mark.unit
def test_byte_nul_non_rompono_il_corpo():
    esito = _run("-q", "--", "printf", "a\\0b\\n")
    assert esito.returncode == 0
    assert "ab" in esito.stdout
    assert "null byte" not in esito.stderr


@pytest.mark.unit
def test_max_bytes_vale_per_il_corpo_intero():
    """Il taglio contava solo l'output: con --max-bytes uguale al max_body_bytes
    del receiver, intestazione e righe aggiunte facevano sforare (413)."""
    esito = _run("-q", "--max-bytes", "2000", "--", "seq", "1", "5000")
    assert esito.returncode == 0
    corpo = esito.stdout.split("\n---\n", 1)[1]
    assert len(corpo.encode()) <= 2000
    assert "byte omessi" in corpo
    # Testa e coda restano: sono le parti che spiegano cos'e' successo.
    assert "\n1\n" in corpo
    assert corpo.rstrip().endswith("5000")


@pytest.mark.unit
def test_timeout_uccide_anche_chi_ignora_sigterm():
    esito = subprocess.run(  # noqa: S603
        [
            "/bin/bash",
            str(WRAPPER),
            "--dry-run",
            "-q",
            "--timeout",
            "1",
            "--",
            "bash",
            "-c",
            'trap "" TERM; sleep 60',
        ],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "NOTIFYHUB_SLUG": SLUG},
        timeout=30,
    )
    assert esito.returncode == 137
    assert "esito=timeout" in esito.stdout


@pytest.mark.unit
def test_output_senza_a_capo_finale_non_si_attacca_alle_righe_successive():
    esito = _run("--", "printf", "abc")
    assert esito.stdout.startswith("abc\n")


class _Webhook:
    """Finto NotifyHub: risponde con la sequenza di codici data e registra le
    richieste ricevute."""

    def __init__(self, codici: list[int]):
        import http.server
        import threading

        self.codici = list(codici)
        self.richieste: list[dict[str, str]] = []
        esterno = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                lunghezza = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(lunghezza)
                esterno.richieste.append(dict(self.headers))
                codice = esterno.codici.pop(0) if esterno.codici else 200
                self.send_response(codice)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args: object) -> None:
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


def _invia(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    import os

    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(WRAPPER), "-u", url, "-s", SLUG, "-q", *args, "--", "true"],
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("NOTIFYHUB_")},
        timeout=60,
    )


@pytest.mark.unit
def test_errore_passeggero_ritentato_con_lo_stesso_request_id():
    webhook = _Webhook([503, 200])
    try:
        esito = _invia(webhook.url, "--retries", "2")
    finally:
        webhook.close()
    assert esito.returncode == 0, esito.stderr
    assert len(webhook.richieste) == 2
    ids = {r["X-Request-Id"] for r in webhook.richieste}
    assert len(ids) == 1, "i tentativi devono riusare lo stesso X-Request-Id"


@pytest.mark.unit
def test_errore_definitivo_non_ritentato():
    webhook = _Webhook([404, 200])
    try:
        esito = _invia(webhook.url, "--retries", "2", "--strict")
    finally:
        webhook.close()
    assert esito.returncode == 1
    assert len(webhook.richieste) == 1
    assert "http=404" in esito.stderr


@pytest.mark.unit
def test_tentativi_esauriti_restituiscono_comunque_lexit_code_del_comando():
    webhook = _Webhook([503, 503])
    try:
        esito = _invia(webhook.url, "--retries", "1")
    finally:
        webhook.close()
    assert esito.returncode == 0
    assert len(webhook.richieste) == 2
    assert "tentativi=2" in esito.stderr
