"""Validazione delle email: un solo criterio per API e CLI.

In NotifyHub l'email e' il **nome utente**, non un recapito: SMTP e' opzionale
(`smtp_enabled`), e un'istanza self-hosted senza posta configurata non manda mai
niente a quell'indirizzo. Per questo qui non si controlla la deliverability, e i
domini di rete privata sono ammessi: `admin@notifyhub.local` e' un nome utente
perfettamente sensato su una LAN.

Il difetto che questo modulo chiude: `python -m app bootstrap` accettava
`admin@notifyhub.local` e creava l'owner, ma `POST /auth/login` lo rifiutava con
422 perche' `email-validator` considera `.local` un dominio special-use. Il primo
utente dell'istanza risultava creato e inutilizzabile, e l'unico rimedio era una
UPDATE a mano sul database.

La correzione e' un allineamento, non una deroga in un solo punto: si restringe
l'elenco dei domini special-use di `email-validator`, che ogni validazione
rilegge a ogni chiamata. Cosi' `EmailStr` degli schemi (login, registrazione,
inviti, creazione utenti) e `normalize_email` della CLI dicono la stessa cosa
senza che nessun call site debba ricordarsene.

Il meccanismo dipende da un dettaglio della libreria (l'elenco viene importato
dentro la funzione di validazione, non legato al modulo all'import): e' coperto da
un test che valida un indirizzo `.local` attraverso lo schema pydantic vero, cosi'
un aggiornamento che lo cambiasse fallirebbe subito invece di far tornare il
difetto in silenzio.
"""

import email_validator

# Domini di rete privata ammessi come nome utente. Restano fuori `invalid`,
# `onion`, `arpa` e `localhost`: nessuno di questi e' un dominio interno che un
# operatore configura, e `localhost` non ha nemmeno un punto.
INTERNAL_TLDS = frozenset({"local", "test"})

SPECIAL_USE_DOMAIN_NAMES = [
    name for name in email_validator.SPECIAL_USE_DOMAIN_NAMES if name not in INTERNAL_TLDS
]
email_validator.SPECIAL_USE_DOMAIN_NAMES = SPECIAL_USE_DOMAIN_NAMES


class InvalidEmailError(ValueError):
    """Email non utilizzabile come nome utente."""


def normalize_email(value: str) -> str:
    """Valida con lo stesso criterio degli schemi e restituisce la forma
    normalizzata (quella che finisce nella colonna `citext` e con cui si fa il
    confronto al login).

    Serve alla CLI, che non passa da pydantic: senza, `bootstrap` accetterebbe
    qualunque stringa e il difetto si sposterebbe da `.local` a `admin@@x`.
    """
    try:
        validated = email_validator.validate_email(value, check_deliverability=False)
    except email_validator.EmailNotValidError as exc:
        raise InvalidEmailError(str(exc)) from exc
    return validated.normalized
