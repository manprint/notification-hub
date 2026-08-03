"""Catalogo dei preset predefiniti e loro installazione in un tenant.

COME SI AGGIUNGE UN PRESET
--------------------------
Si scrive un `PresetSpec` e lo si mette in `BUILTIN_PRESETS`. Non serve altro:
nessuna migrazione, nessuna modifica alle API, nessuna modifica alla dashboard.
I tenant esistenti lo ricevono con `python -m app.cli sync-presets` o con il
pulsante "Installa i preset mancanti" nella sezione Preset; i tenant nuovi lo
trovano gia installato.

    NUOVO = PresetSpec(
        key="nome-tecnico-stabile",   # non cambiarlo piu: identifica la copia
        name="Nome mostrato",
        description="Una riga che dica di che log si tratta.",
        rules=(
            PresetRuleSpec(r"pattern", Severity.ERROR),
            ...
        ),
    )

CRITERI DI SCRITTURA DELLE REGOLE
---------------------------------
1. I pattern sono espressioni regolari in sintassi RE2: niente lookahead, niente
   backreference. Massimo 200 caratteri, come le regole dei receiver.
2. Un preset contiene solo regole che ALZANO la severity. La prima regola che
   corrisponde vince e ferma la catena, quindi una regola su una riga innocua
   ("Removing leading / from member names" di tar) mascherebbe l'errore vero che
   arriva dopo. Il rumore si ignora, non si classifica.
3. Ordine dal caso piu grave e piu specifico al piu generico: `priority` viene
   assegnata 10, 20, 30... seguendo l'ordine di scrittura qui sotto.
4. `case_insensitive=False` quando le maiuscole sono l'informazione: `ERROR:` in
   un log PostgreSQL e un livello di log, "error" dentro una frase inglese no.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.types import Severity
from app.models.severity_preset import SeverityPreset, SeverityPresetRule

PRIORITY_STEP = 10


@dataclass(frozen=True)
class PresetRuleSpec:
    pattern: str
    severity: Severity
    case_insensitive: bool = True


@dataclass(frozen=True)
class PresetSpec:
    key: str
    name: str
    description: str
    rules: tuple[PresetRuleSpec, ...]


BASH_GENERIC = PresetSpec(
    key="bash-generic",
    name="Bash generico",
    description=(
        "Errori comuni di shell e coreutils: comando assente, permessi, disco pieno, "
        "segmentation fault, rete irraggiungibile. Da applicare a quasi tutti gli script."
    ),
    rules=(
        PresetRuleSpec(
            r"No space left on device|Spazio esaurito sul dispositivo|Disk quota exceeded",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"Segmentation fault|core dumped|Bus error|Aborted \(core",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"Out of memory|Cannot allocate memory|oom.kill|Killed process|Impossibile allocare",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"Input/output error|Errore di input/output|Structure needs cleaning",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"Read-only file system|File system in sola lettura|Stale file handle",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"command not found|comando non trovato|: not found|Exec format error|"
            r"cannot execute binary file",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Permission denied|Permesso negato|Operation not permitted|Operazione non permessa",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"No such file or directory|File o directory non esistente",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"syntax error near unexpected token|unexpected EOF while looking for|"
            r"unbound variable|bad substitution",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Connection refused|Connection timed out|No route to host|"
            r"Network is unreachable|Name or service not known",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Too many open files|Argument list too long|Cannot fork|Resource deadlock",
            Severity.ERROR,
        ),
        # Rete di sicurezza in fondo: prende quello che le regole sopra non hanno
        # riconosciuto. Volutamente larga, quindi anche capace di falsi positivi
        # ("nessun errore rilevato"): se disturba si disattiva dalla dashboard.
        PresetRuleSpec(
            r"\b(ERROR|ERRORE|FATAL|FATALE|FAILED|FAILURE|FALLITO|FALLIMENTO)\b",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Device or resource busy|Text file busy|Resource temporarily unavailable",
            Severity.WARNING,
        ),
        PresetRuleSpec(
            r"\b(WARNING|WARN|ATTENZIONE|AVVISO|deprecated|deprecato)\b",
            Severity.WARNING,
        ),
    ),
)


POSTGRES = PresetSpec(
    key="postgres",
    name="PostgreSQL",
    description=(
        "Livelli di log del server (PANIC, FATAL, ERROR, WARNING) piu gli errori tipici di "
        "psql, pg_dump e pg_restore."
    ),
    rules=(
        # I livelli di log di Postgres sono maiuscoli per definizione: cercarli
        # senza distinguere le maiuscole significherebbe scattare sulla parola
        # "error" dentro una frase qualsiasi.
        PresetRuleSpec(r"PANIC:", Severity.CRITICAL, case_insensitive=False),
        PresetRuleSpec(r"FATAL:", Severity.CRITICAL, case_insensitive=False),
        PresetRuleSpec(
            r"could not write to file|could not fsync file|invalid page in block|"
            r"data directory .* is not accessible",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"No space left on device|could not extend file|database is not accepting commands",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"could not connect to server|server closed the connection unexpectedly|"
            r"could not translate host name",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"pg_dump: error|pg_restore: error|pg_basebackup: error|psql: error|"
            r"pg_dumpall: error",
            Severity.ERROR,
        ),
        PresetRuleSpec(r"deadlock detected|deadlock rilevato", Severity.ERROR),
        PresetRuleSpec(
            r"permission denied for|must be owner of|role .* does not exist|"
            r"database .* does not exist",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"violates unique constraint|violates foreign key constraint|"
            r"violates not-null constraint|violates check constraint",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"too many clients already|remaining connection slots are reserved",
            Severity.ERROR,
        ),
        PresetRuleSpec(r"ERROR:", Severity.ERROR, case_insensitive=False),
        PresetRuleSpec(
            r"canceling statement due to statement timeout|"
            r"canceling statement due to lock timeout|terminating connection due to",
            Severity.WARNING,
        ),
        PresetRuleSpec(
            r"checkpoints are occurring too frequently|using stale statistics|"
            r"skipping vacuum of",
            Severity.WARNING,
        ),
        PresetRuleSpec(r"WARNING:", Severity.WARNING, case_insensitive=False),
    ),
)


MONGODB = PresetSpec(
    key="mongodb",
    name="MongoDB",
    description=(
        "Log del server (campo di severita F/E/W del formato JSON), errori di connessione e "
        "autenticazione, esiti di mongodump e mongorestore."
    ),
    rules=(
        PresetRuleSpec(
            r"Fatal assertion|invariant failure|Unrecoverable error|WiredTiger error|"
            r"Got signal: [0-9]+",
            Severity.CRITICAL,
        ),
        # Formato di log JSON di mongod: {"t":...,"s":"F",...}. La severita sta
        # nel campo "s" ed e una lettera maiuscola.
        PresetRuleSpec(r'"s":"F"', Severity.CRITICAL, case_insensitive=False),
        PresetRuleSpec(
            r"out of memory|Cannot allocate memory|exceeded memory limit|OOM",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"MongoNetworkError|No suitable servers found|server selection timed out|"
            r"connection refused|couldn't connect to server",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Authentication failed|AuthenticationFailed|requires authentication|"
            r"not authorized on|Unauthorized",
            Severity.ERROR,
        ),
        PresetRuleSpec(r"E11000 duplicate key error", Severity.ERROR),
        PresetRuleSpec(
            r"NotPrimaryError|not master|ReplicaSetNoPrimary|No primary detected|"
            r"InterruptedDueToReplStateChange",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Failed: |failed to restore|failed to dump|error writing data|error connecting",
            Severity.ERROR,
        ),
        PresetRuleSpec(r'"s":"E"', Severity.ERROR, case_insensitive=False),
        PresetRuleSpec(
            r"MaxTimeMSExpired|operation exceeded time limit|WriteConflict|slow query",
            Severity.WARNING,
        ),
        PresetRuleSpec(r'"s":"W"', Severity.WARNING, case_insensitive=False),
    ),
)


TAR = PresetSpec(
    key="tar",
    name="tar",
    description=(
        "Archiviazione con tar e gzip: archivi danneggiati, file illeggibili, spazio "
        "esaurito, uscita con errori differiti."
    ),
    rules=(
        PresetRuleSpec(
            r"No space left on device|Wrote only .* of .* bytes|Cannot write",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"Unexpected EOF in archive|Damaged tar archive|[Cc]hecksum error|"
            r"invalid compressed data|unexpected end of file",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"Error is not recoverable|Skipping to next header|"
            r"This does not look like a tar archive",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Error exit delayed from previous errors|Exiting with failure status",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"Cannot open|Cannot stat|Cannot read|Cannot mkdir|Cannot hard link|Cannot symlink",
            Severity.ERROR,
        ),
        PresetRuleSpec(r"Permission denied|Permesso negato", Severity.ERROR),
        PresetRuleSpec(r"Not found in archive|Required occurrence not found", Severity.ERROR),
        PresetRuleSpec(
            r"Cowardly refusing to create an empty archive|"
            r"Refusing to read archive contents from terminal",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"file changed as we read it|socket ignored|Cannot utime|Cannot change mode|"
            r"Cannot change ownership",
            Severity.WARNING,
        ),
    ),
)


RCLONE = PresetSpec(
    key="rclone",
    name="rclone",
    description=(
        "Sincronizzazioni con rclone: livelli di log CRITICAL/ERROR, quota esaurita, "
        "credenziali scadute, file corrotti in transito, riga finale di statistiche."
    ),
    rules=(
        # rclone scrive il livello in maiuscolo a inizio riga: "ERROR : file: ...".
        PresetRuleSpec(r"CRITICAL", Severity.CRITICAL, case_insensitive=False),
        PresetRuleSpec(
            r"corrupted on transfer|sizes differ|hashes differ|md5 differ|"
            r"failed to authenticate",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(
            r"quota exceeded|storageQuotaExceeded|insufficient space|No space left on device|"
            r"over quota",
            Severity.CRITICAL,
        ),
        PresetRuleSpec(r"\bERROR\b", Severity.ERROR, case_insensitive=False),
        PresetRuleSpec(
            r"Failed to (copy|sync|move|check|delete|purge|mkdir|rmdir|transfer)",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"didn't find section in config file|couldn't connect|couldn't fetch token|"
            r"config file not found",
            Severity.ERROR,
        ),
        PresetRuleSpec(
            r"401 Unauthorized|403 Forbidden|invalid_grant|token expired|" r"authentication failed",
            Severity.ERROR,
        ),
        # Riga di statistiche finale: "Errors: 3 (retrying may help)".
        PresetRuleSpec(r"Errors: +[1-9]", Severity.ERROR, case_insensitive=False),
        PresetRuleSpec(r"directory not found|object not found|not found in source", Severity.ERROR),
        PresetRuleSpec(
            r"429 Too Many Requests|rate limit|connection reset by peer|i/o timeout|"
            r"context deadline exceeded",
            Severity.WARNING,
        ),
        PresetRuleSpec(
            r"Attempt [0-9]+/[0-9]+ failed|Can't transfer non file|will retry",
            Severity.WARNING,
        ),
        PresetRuleSpec(r"\bWARNING\b", Severity.WARNING, case_insensitive=False),
    ),
)


# L'unico elenco da toccare per aggiungere un preset predefinito.
BUILTIN_PRESETS: tuple[PresetSpec, ...] = (BASH_GENERIC, POSTGRES, MONGODB, TAR, RCLONE)

BUILTIN_BY_KEY: dict[str, PresetSpec] = {spec.key: spec for spec in BUILTIN_PRESETS}


def _add_rules(session: AsyncSession, preset: SeverityPreset, spec: PresetSpec) -> None:
    for index, rule in enumerate(spec.rules, start=1):
        session.add(
            SeverityPresetRule(
                id=uuid.uuid4(),
                tenant_id=preset.tenant_id,
                preset_id=preset.id,
                priority=index * PRIORITY_STEP,
                pattern=rule.pattern,
                case_insensitive=rule.case_insensitive,
                severity=rule.severity,
                enabled=True,
            )
        )


async def install_builtin_preset(
    session: AsyncSession, tenant_id: uuid.UUID, spec: PresetSpec
) -> SeverityPreset:
    """Copia un preset del catalogo dentro il tenant. Il chiamante garantisce che
    non ci sia gia una copia con la stessa chiave."""
    preset = SeverityPreset(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        builtin_key=spec.key,
        name=spec.name,
        description=spec.description,
    )
    session.add(preset)
    _add_rules(session, preset, spec)
    await session.flush()
    return preset


async def sync_builtin_presets(session: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    """Installa i preset del catalogo che questo tenant non ha ancora.

    Idempotente e non distruttiva: una copia gia presente non viene MAI toccata,
    nemmeno se nel frattempo il catalogo e cambiato. Le modifiche fatte dagli
    utenti valgono piu del catalogo; per tornare ai valori di fabbrica c'e il
    ripristino esplicito (`reset_preset_to_builtin`).

    Restituisce le chiavi installate ora.
    """
    result = await session.execute(
        select(SeverityPreset.builtin_key).where(
            SeverityPreset.tenant_id == tenant_id,
            SeverityPreset.builtin_key.is_not(None),
        )
    )
    already = {row[0] for row in result.all()}

    installed: list[str] = []
    for spec in BUILTIN_PRESETS:
        if spec.key in already:
            continue
        await install_builtin_preset(session, tenant_id, spec)
        installed.append(spec.key)
    return installed


async def missing_builtin_keys(session: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(SeverityPreset.builtin_key).where(
            SeverityPreset.tenant_id == tenant_id,
            SeverityPreset.builtin_key.is_not(None),
        )
    )
    already = {row[0] for row in result.all()}
    return [spec.key for spec in BUILTIN_PRESETS if spec.key not in already]


async def reset_preset_to_builtin(session: AsyncSession, preset: SeverityPreset) -> PresetSpec:
    """Riporta le regole di un preset ai valori del catalogo, buttando via le
    modifiche locali. Nome e descrizione tornano anch'essi ai valori di fabbrica.

    Solleva KeyError se il preset non viene da un preset predefinito: e il
    chiamante a doverlo tradurre nella risposta HTTP giusta.
    """
    if preset.builtin_key is None:
        raise KeyError("preset non predefinito")
    spec = BUILTIN_BY_KEY[preset.builtin_key]

    await session.execute(
        delete(SeverityPresetRule).where(SeverityPresetRule.preset_id == preset.id)
    )
    # Il DELETE deve arrivare al database prima degli INSERT: l'unita di lavoro
    # di SQLAlchemy emette gli INSERT prima dei DELETE, e il vincolo di unicita
    # su (preset_id, priority) scatterebbe a meta strada.
    await session.flush()

    preset.name = spec.name
    preset.description = spec.description
    _add_rules(session, preset, spec)
    await session.flush()
    return spec
