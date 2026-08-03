"""Il catalogo dei preset predefiniti e dati scritti a mano: questi test sono il
controllo che un preset aggiunto in futuro rispetti le regole della casa."""

import pytest

from app.db.types import Severity
from app.services.severity import compile_pattern
from app.services.severity_presets import BUILTIN_BY_KEY, BUILTIN_PRESETS

PATTERN_MAX_LENGTH = 200  # come la colonna pattern di severity_preset_rules

# Il committente li ha chiesti per nome: se qualcuno li rinomina, questo test
# glielo dice prima che lo scoprano gli utenti con i preset spariti.
CHIAVI_ATTESE = {"bash-generic", "postgres", "mongodb", "tar", "rclone"}


@pytest.mark.unit
def test_chiavi_previste_presenti():
    assert CHIAVI_ATTESE <= set(BUILTIN_BY_KEY)


@pytest.mark.unit
def test_chiavi_e_nomi_unici():
    chiavi = [spec.key for spec in BUILTIN_PRESETS]
    nomi = [spec.name for spec in BUILTIN_PRESETS]
    assert len(chiavi) == len(set(chiavi))
    # I nomi finiscono in un vincolo di unicita per tenant: due preset omonimi
    # nel catalogo renderebbero l'installazione impossibile a meta strada.
    assert len(nomi) == len(set(nomi))


@pytest.mark.unit
@pytest.mark.parametrize("spec", BUILTIN_PRESETS, ids=lambda spec: spec.key)
def test_preset_ben_formato(spec):
    assert spec.rules, f"{spec.key} non ha regole"
    assert spec.description.strip(), f"{spec.key} non ha descrizione"

    for rule in spec.rules:
        assert len(rule.pattern) <= PATTERN_MAX_LENGTH, f"{spec.key}: pattern troppo lungo"
        # Un pattern non compilabile passerebbe l'installazione e fallirebbe la
        # prima ingestion: va scoperto qui, non in produzione.
        compile_pattern(rule.pattern, rule.case_insensitive)


@pytest.mark.unit
@pytest.mark.parametrize("spec", BUILTIN_PRESETS, ids=lambda spec: spec.key)
def test_i_preset_alzano_soltanto_la_severity(spec):
    """Le regole di un preset segnalano problemi. Una regola che assegna info o
    debug corrisponderebbe a una riga innocua e, vincendo per prima, coprirebbe
    l'errore vero che arriva dopo nello stesso log."""
    for rule in spec.rules:
        assert rule.severity in (
            Severity.WARNING,
            Severity.ERROR,
            Severity.CRITICAL,
        ), f"{spec.key}: la regola '{rule.pattern}' abbassa la severity"


@pytest.mark.unit
@pytest.mark.parametrize("spec", BUILTIN_PRESETS, ids=lambda spec: spec.key)
def test_regole_ordinate_dalla_piu_grave(spec):
    """Vince la prima che corrisponde: una regola warning messa sopra una
    critical renderebbe la critical irraggiungibile per gli stessi log."""
    peso = {Severity.CRITICAL: 3, Severity.ERROR: 2, Severity.WARNING: 1}
    pesi = [peso[rule.severity] for rule in spec.rules]
    assert pesi == sorted(pesi, reverse=True), f"{spec.key}: regole non ordinate per gravita"
