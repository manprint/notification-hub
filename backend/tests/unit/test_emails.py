"""Un solo criterio di validazione delle email fra API e CLI.

Il difetto chiuso qui: `bootstrap --email admin@notifyhub.local` creava l'owner,
ma il login lo rifiutava con 422. Il primo utente dell'istanza risultava creato e
inutilizzabile.
"""

import pytest
from pydantic import ValidationError

from app.core.emails import INTERNAL_TLDS, InvalidEmailError, normalize_email
from app.schemas.auth import InvitationIn, LoginIn


@pytest.mark.unit
@pytest.mark.parametrize(
    "indirizzo",
    [
        "admin@notifyhub.local",  # il caso del difetto
        "admin@notifyhub.test",
        "admin@notifyhub.internal",
        "owner@acme.it",
        "nome.cognome+tag@example.com",
    ],
)
def test_indirizzi_accettati(indirizzo):
    assert normalize_email(indirizzo) == indirizzo


@pytest.mark.unit
@pytest.mark.parametrize(
    "indirizzo",
    [
        "",
        "senza-chiocciola",
        "admin@@notifyhub.local",
        "admin@",
        "@notifyhub.local",
        "admin@notifyhub..local",
        "admin@dominio con spazi.local",
        # Restano rifiutati i domini special-use che nessuno configura come
        # dominio interno.
        "admin@qualcosa.invalid",
        "admin@qualcosa.onion",
    ],
)
def test_indirizzi_rifiutati(indirizzo):
    with pytest.raises(InvalidEmailError):
        normalize_email(indirizzo)


@pytest.mark.unit
def test_normalizzazione_del_dominio():
    """La forma normalizzata e' quella che finisce in colonna e con cui si
    confronta al login: il dominio va minuscolo."""
    assert normalize_email("Admin@NotifyHub.LOCAL") == "Admin@notifyhub.local"


@pytest.mark.unit
@pytest.mark.parametrize("tld", sorted(INTERNAL_TLDS))
def test_gli_schemi_accettano_i_domini_interni(tld):
    """Il test che protegge il meccanismo: `EmailStr` deve accettare gli stessi
    indirizzi di `normalize_email`. L'allineamento passa da una lista che
    `email-validator` rilegge a ogni chiamata, quindi un aggiornamento che
    cambiasse quel dettaglio deve far fallire questo test invece di riportare il
    difetto in silenzio."""
    indirizzo = f"admin@notifyhub.{tld}"
    assert LoginIn(email=indirizzo, password="x").email == indirizzo
    assert InvitationIn(email=indirizzo, role="admin").email == indirizzo


@pytest.mark.unit
def test_gli_schemi_rifiutano_quello_che_rifiuta_la_cli():
    with pytest.raises(ValidationError):
        LoginIn(email="admin@@notifyhub.local", password="x")
