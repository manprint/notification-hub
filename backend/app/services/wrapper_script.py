"""Consegna di `scripts/notifyhub-run.sh` precompilato per un receiver.

Il file servito e' lo STESSO che sta nel repository, non una copia riscritta
qui: due versioni dello stesso script divergono al primo bugfix. L'unica cosa
che cambia sono le due righe del blocco "configurazione" in cima, dove finiscono
l'URL pubblica dell'istanza e lo slug del receiver.

Il valore interpolato finisce dentro `"${NOTIFYHUB_URL:-...}"`, cioe' dentro uno
script eseguito su un'altra macchina: entrambi vengono validati su un alfabeto
che non contiene niente di interpretabile dalla shell (`"`, `$`, backtick, `}`,
ritorno a capo). L'URL arriva gia' filtrata da `normalize_base_url`, lo slug lo
ricontrolla `_is_safe_slug` qui sotto; se uno dei due non passa, il download
fallisce invece di produrre uno script sbagliato.
"""

import string
from pathlib import Path

from app.core.config import get_settings
from app.services.slug import SLUG_MAX_CHARS, slugify_part

TEMPLATE_FILENAME = "notifyhub-run.sh"

# Le due righe da riscrivere, riconosciute dal prefisso: cosi' il template resta
# uno script normale, senza segnaposto da ricordarsi di aggiornare.
URL_LINE_PREFIX = 'URL="${NOTIFYHUB_URL:-'
SLUG_LINE_PREFIX = 'SLUG="${NOTIFYHUB_SLUG:-'
LINE_SUFFIX = '}"'

_SLUG_CHARS = frozenset(string.ascii_letters + string.digits + "_-")
_URL_CHARS = frozenset(string.ascii_letters + string.digits + ":/._~-[]")
_URL_MAX_CHARS = 300
# Nomi mostrati nel commento di provenienza: dentro un commento shell l'unico
# carattere davvero pericoloso e' il ritorno a capo, che uscirebbe dal commento.
_COMMENT_EXTRA_CHARS = frozenset(" .:,;@/()[]+-_'")
COMMENT_NAME_MAX_CHARS = 60


class WrapperTemplateError(RuntimeError):
    """Il template non e' raggiungibile o non ha piu' la forma attesa."""


def _is_safe_slug(slug: str) -> bool:
    return bool(slug) and len(slug) <= SLUG_MAX_CHARS and set(slug) <= _SLUG_CHARS


def _is_safe_base_url(url: str) -> bool:
    return (
        url.startswith(("http://", "https://"))
        and len(url) <= _URL_MAX_CHARS
        and set(url) <= _URL_CHARS
    )


def template_candidates() -> list[Path]:
    """In ordine: percorso configurato, copia dentro l'immagine
    (`<radice del backend>/scripts`), repository di sviluppo."""
    candidates: list[Path] = []
    configured = get_settings().notifyhub_wrapper_script_path
    if configured:
        candidates.append(Path(configured))
    here = Path(__file__).resolve()
    # .../app/services/wrapper_script.py -> parents[2] e' la radice del backend
    # (nell'immagine e' /app, dove il Dockerfile copia scripts/), parents[3] la
    # radice del repository quando si lavora dal checkout.
    for parent in (here.parents[2], here.parents[3]):
        candidates.append(parent / "scripts" / TEMPLATE_FILENAME)
    return candidates


def load_template() -> str:
    for candidate in template_candidates():
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise WrapperTemplateError(
        f"{TEMPLATE_FILENAME} not found in any of: "
        + ", ".join(str(candidate) for candidate in template_candidates())
    )


def _comment_name(value: str) -> str:
    """Nome ridotto a una riga sola: `isalnum()` tiene le lettere accentate e
    scarta per costruzione i caratteri di controllo, ritorno a capo compreso."""
    cleaned = "".join(
        char if (char.isalnum() or char in _COMMENT_EXTRA_CHARS) else " " for char in value
    )
    return " ".join(cleaned.split())[:COMMENT_NAME_MAX_CHARS].strip() or "senza nome"


def render_wrapper_script(
    template: str,
    *,
    base_url: str,
    slug: str,
    receiver_name: str,
    group_name: str,
) -> str:
    if not _is_safe_base_url(base_url):
        raise WrapperTemplateError(f"base URL not safe to embed in a shell script: {base_url!r}")
    if not _is_safe_slug(slug):
        raise WrapperTemplateError(f"slug not safe to embed in a shell script: {slug!r}")

    provenance = (
        f"# Precompilato dalla dashboard per il receiver "
        f'"{_comment_name(receiver_name)}" del gruppo "{_comment_name(group_name)}".'
    )

    rendered: list[str] = []
    seen_url = 0
    seen_slug = 0
    for line in template.split("\n"):
        if line.startswith(URL_LINE_PREFIX):
            seen_url += 1
            rendered.append(provenance)
            rendered.append(f"{URL_LINE_PREFIX}{base_url}{LINE_SUFFIX}")
        elif line.startswith(SLUG_LINE_PREFIX):
            seen_slug += 1
            rendered.append(f"{SLUG_LINE_PREFIX}{slug}{LINE_SUFFIX}")
        else:
            rendered.append(line)

    if seen_url != 1 or seen_slug != 1:
        raise WrapperTemplateError(
            f"{TEMPLATE_FILENAME} must contain exactly one URL line and one SLUG line, "
            f"found {seen_url} and {seen_slug}"
        )
    return "\n".join(rendered)


def script_filename(receiver_name: str) -> str:
    """`notifyhub-run-<receiver>.sh`. Il nome del file non porta lo slug: e' una
    credenziale, e finisce in chiaro nell'elenco della cartella dei download."""
    part = slugify_part(receiver_name)
    return f"notifyhub-run-{part}.sh" if part else TEMPLATE_FILENAME
