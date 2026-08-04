"""URL pubbliche dell'istanza: una sola funzione decide qual e' l'origine.

Un link sbagliato dietro reverse proxy non da' errore: da' un indirizzo che non
risponde, o che risponde solo dalla macchina dell'API. Vale per i link nelle
notifiche inoltrate, per quelli negli inviti e soprattutto per lo script wrapper
scaricato dalla dashboard, che finisce in un crontab su un'altra macchina.

Ordine di autorita':

1. `NOTIFYHUB_PUBLIC_BASE_URL`, se e' configurata e non punta al loopback. E'
   la dichiarazione dell'operatore: `https://notifyhub.example.com`, eventuale
   sottopercorso compreso.
2. la richiesta in corso, quando ce n'e' una: `X-Forwarded-Proto`,
   `X-Forwarded-Host` e `X-Forwarded-Prefix` se il proxy li manda, altrimenti
   scheme e header `Host`. Copre il caso in cui la configurazione e' rimasta al
   default di sviluppo mentre l'istanza gira dietro nginx in https.
3. la configurazione comunque, anche loopback, come ultima spiaggia.

Il valore viene sempre normalizzato e validato su un alfabeto sicuro: la stessa
stringa finisce dentro uno script bash, e un `Host:` ostile non deve poter
diventare codice. La validazione e' fatta a insiemi di caratteri e non con
espressioni regolari, perche' l'invariante I-3 vieta il modulo `re` in `app/`.
"""

import string
from urllib.parse import urlsplit

from starlette.requests import Request

from app.core.config import get_settings

DEFAULT_BASE_URL = "http://localhost"

# Confrontati con urlsplit().hostname, che minuscola e toglie le parentesi
# quadre degli IPv6. Sono host da RICONOSCERE, non indirizzi su cui mettersi in
# ascolto.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # noqa: S104

_HOST_CHARS = frozenset(string.ascii_letters + string.digits + "._~-")
_IPV6_CHARS = frozenset(string.hexdigits + ":.")
_PATH_CHARS = frozenset(string.ascii_letters + string.digits + "._~-")
_DIGITS = frozenset(string.digits)
_MAX_PORT_DIGITS = 5


def _is_safe_netloc(netloc: str) -> bool:
    """Nome (o IP) piu' porta, senza credenziali `utente:password@`."""
    if not netloc:
        return False
    port = ""
    if netloc.startswith("["):
        closing = netloc.find("]")
        if closing == -1:
            return False
        address = netloc[1:closing]
        if not address or not set(address) <= _IPV6_CHARS:
            return False
        rest = netloc[closing + 1 :]
        if rest:
            if not rest.startswith(":"):
                return False
            port = rest[1:]
    else:
        host = netloc
        if ":" in host:
            host, _, port = host.partition(":")
        if not host or not set(host) <= _HOST_CHARS:
            return False
    if port and not (set(port) <= _DIGITS and len(port) <= _MAX_PORT_DIGITS):
        return False
    return True


def _is_safe_path(path: str) -> bool:
    """Prefisso di percorso: vuoto, oppure segmenti non vuoti dopo ogni `/`."""
    if not path:
        return True
    if not path.startswith("/"):
        return False
    return all(segment and set(segment) <= _PATH_CHARS for segment in path.split("/")[1:])


def normalize_base_url(raw: str | None) -> str | None:
    """`scheme://host[:porta][/prefisso]` senza slash finale, oppure None se la
    stringa non e' utilizzabile come origine pubblica.

    Scarta di proposito credenziali nell'URL (`utente:password@host`), query
    string, frammenti e qualunque carattere fuori dall'alfabeto degli URL: cio'
    che resta e' innocuo da interpolare in uno script."""
    if raw is None:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    # urlsplit toglie in silenzio ritorni a capo e tabulazioni: senza questo
    # controllo un valore di configurazione con un "\n" di troppo diventerebbe un
    # host diverso da quello scritto, invece di essere rifiutato.
    if any(char.isspace() or not char.isprintable() for char in candidate):
        return None
    if "://" not in candidate:
        # "notifyhub.example.com" -> https: davanti a un nome nudo l'unica
        # ipotesi sensata e' TLS.
        candidate = f"https://{candidate}"

    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https"):
        return None
    if parts.query or parts.fragment:
        return None
    if not _is_safe_netloc(parts.netloc):
        return None
    # Lo slash finale si toglie qui e non con rstrip sulla stringa intera:
    # "https://" ridotto a "https:" tornerebbe a sembrare un host senza schema.
    path = parts.path.rstrip("/")
    if not _is_safe_path(path):
        return None
    return f"{parts.scheme}://{parts.netloc}{path}"


def is_loopback_base_url(url: str) -> bool:
    return (urlsplit(url).hostname or "") in LOOPBACK_HOSTS


def configured_base_url() -> str:
    """La sola configurazione, normalizzata. Per i contesti senza richiesta:
    worker Celery, job di manutenzione."""
    return normalize_base_url(get_settings().notifyhub_public_base_url) or DEFAULT_BASE_URL


def _first_forwarded_value(raw: str | None) -> str | None:
    """`X-Forwarded-*` puo' arrivare come catena "primo, secondo": il primo
    valore e' quello visto dal client."""
    if not raw:
        return None
    first = raw.split(",")[0].strip()
    return first or None


def base_url_from_request(request: Request) -> str | None:
    scheme = _first_forwarded_value(request.headers.get("x-forwarded-proto")) or request.url.scheme
    host = (
        _first_forwarded_value(request.headers.get("x-forwarded-host"))
        or request.headers.get("host")
        or request.url.netloc
    )
    prefix = _first_forwarded_value(request.headers.get("x-forwarded-prefix")) or ""
    if prefix and not prefix.startswith("/"):
        prefix = f"/{prefix}"
    return normalize_base_url(f"{scheme}://{host}{prefix}")


def public_base_url(request: Request | None = None) -> str:
    configured = normalize_base_url(get_settings().notifyhub_public_base_url)
    if configured is not None and not is_loopback_base_url(configured):
        return configured
    if request is not None:
        # Anche in sviluppo la richiesta sa la porta giusta, la configurazione
        # spesso no: fra due loopback vince quella da cui si sta parlando.
        derived = base_url_from_request(request)
        if derived is not None:
            return derived
    return configured or DEFAULT_BASE_URL


def ingest_url(slug: str, request: Request | None = None) -> str:
    return f"{public_base_url(request)}/ingest/{slug}"
