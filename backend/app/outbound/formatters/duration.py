"""Durata dell'esecuzione, resa leggibile nei messaggi verso i canali.

Il corpo della notifica contiene gia' la durata quando il mittente e' il wrapper
`notifyhub-run.sh`, ma dentro la sua intestazione di testo. Qui la durata diventa
una riga a se', fuori dal contenuto: chi guarda l'alert su Slack deve capire in
un colpo d'occhio *perche'* e' arrivato, e "oltre la soglia di 10m00s" e' il
motivo, non un dettaglio del log.
"""


def format_duration_ms(duration_ms: int) -> str:
    """Millisecondi -> forma breve leggibile (`0.750s`, `12m30s`, `1h02m03s`).

    Stessa resa di human_duration() nel wrapper: sotto il minuto i millisecondi
    restano visibili, sopra si passa a minuti e ore perche' "750123ms" non dice
    niente a chi legge un allarme.
    """
    seconds, millis = divmod(max(duration_ms, 0), 1000)
    if seconds < 60:
        return f"{seconds}.{millis:03d}s"
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


def duration_note(duration_ms: int | None, threshold_seconds: int | None) -> str | None:
    """Riga da mostrare nel messaggio, o None se non c'e' durata da dichiarare.

    La soglia compare solo quando e' stata davvero superata: dire "durata 3s
    (soglia 10m)" su ogni notifica sarebbe rumore, mentre dirlo quando la soglia
    e' scattata spiega l'alert.
    """
    if duration_ms is None:
        return None
    shown = f"durata {format_duration_ms(duration_ms)}"
    if threshold_seconds is not None and duration_ms > threshold_seconds * 1000:
        return f"{shown} — oltre la soglia di {format_duration_ms(threshold_seconds * 1000)}"
    return shown
