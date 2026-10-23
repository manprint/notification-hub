"""Testo del corpo per i formatter outbound: escape dei caratteri di markup e
troncamento con segnalazione (spec 8.5).

Slack (mrkdwn) e Google Chat (testo HTML semplice) interpretano `&`, `<` e `>`:
senza escape, `<!channel>` pinga tutto il canale e `<url|label>` diventa un link.
"""

# Allineato a CONTENT_PREVIEW_CHARS in services/ingest.py: la preview salvata
# viene tagliata a questa lunghezza, quindi una preview che la raggiunge puo'
# essere a sua volta un troncamento (vedi `is_stored_truncation`).
CONTENT_PREVIEW_CHARS = 4096

_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def fit_escaped(text: str, limit: int) -> tuple[str, bool]:
    """Escape di `&`, `<`, `>` con tetto di `limit` caratteri sull'output escapato.

    Ritorna il testo escapato e se e' stato tagliato. Il tetto vale sull'output: un
    `&` diventa `&amp;` e il taglio sul testo grezzo supererebbe il limite del
    provider. Il taglio non cade mai dentro un'entita'.
    """
    out: list[str] = []
    size = 0
    for char in text:
        piece = _ESCAPES.get(char, char)
        if size + len(piece) > limit:
            return "".join(out), True
        out.append(piece)
        size += len(piece)
    return "".join(out), False


def is_stored_truncation(content_preview: str, content_size: int) -> bool:
    """La preview salvata e' un troncamento del corpo originale?

    `content_size` conta i byte originali (spec 6.2), che la normalizzazione (NUL
    rimossi, UTF-8 sostituito) puo' far divergere dai byte della preview: il solo
    confronto dei byte darebbe un falso "troncato". Una preview piu' corta del tetto
    di salvataggio e' sempre il corpo intero.
    """
    return len(content_preview) >= CONTENT_PREVIEW_CHARS and content_size > len(
        content_preview.encode()
    )
