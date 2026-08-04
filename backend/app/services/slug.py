"""Slug dei receiver: prefisso leggibile + token casuale (spec 4.2).

Lo slug e' l'unica credenziale dell'endpoint di ingestion, quindi la parte
casuale resta di 22 caratteri urlsafe (128 bit) esattamente come prima. Davanti
ci vanno gruppo e nome del receiver, che non aggiungono ne' togliono entropia ma
rendono riconoscibile una riga di crontab, un log di nginx o l'elenco dei
receiver in dashboard:

    maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ

invece di `cw2k2WWnmLalhpeyvfnCCQ`.

Il prefisso e' una fotografia dei nomi al momento in cui lo slug nasce, non un
riferimento vivo: rinominare gruppo o receiver NON riscrive lo slug, perche'
cambiarlo romperebbe di nascosto ogni crontab che lo usa. Per allinearlo ai nomi
nuovi c'e' `rotate-slug`, che e' un'azione esplicita e riservata ad admin+.

Nessuna espressione regolare qui dentro: l'invariante I-3 vieta il modulo `re`
in tutto `app/`, e per un controllo di alfabeto un insieme di caratteri e'
comunque piu' diretto.
"""

import secrets
import string
import unicodedata

SLUG_TOKEN_BYTES = 16  # secrets.token_urlsafe(16) -> 22 caratteri (spec 4.2)
SLUG_TOKEN_CHARS = 22
SLUG_PART_MAX_CHARS = 32
SLUG_MAX_CHARS = 120  # colonna receivers.slug, migrazione 0011

SLUG_SEPARATOR = "-"
_PART_CHARS = frozenset(string.ascii_lowercase + string.digits)


def slugify_part(value: str) -> str:
    """Riduce un nome a `[a-z0-9-]`: minuscole, accenti decomposti e scartati,
    ogni altro carattere diventa un separatore (senza doppioni ne' separatori ai
    bordi). Puo' restituire stringa vuota, per un nome fatto solo di emoji o
    ideogrammi: in quel caso il pezzo si omette e lo slug resta valido, solo
    meno parlante."""
    ascii_only = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    )
    chars: list[str] = []
    for char in ascii_only:
        if char in _PART_CHARS:
            chars.append(char)
        elif chars and chars[-1] != SLUG_SEPARATOR:
            chars.append(SLUG_SEPARATOR)
    return "".join(chars).strip(SLUG_SEPARATOR)[:SLUG_PART_MAX_CHARS].strip(SLUG_SEPARATOR)


def new_slug_token() -> str:
    return secrets.token_urlsafe(SLUG_TOKEN_BYTES)


def build_receiver_slug(group_name: str, receiver_name: str, *, token: str | None = None) -> str:
    """`gruppo-receiver-token`, saltando i pezzi che si riducono a nulla."""
    parts = [part for part in (slugify_part(group_name), slugify_part(receiver_name)) if part]
    parts.append(token if token is not None else new_slug_token())
    return SLUG_SEPARATOR.join(parts)
