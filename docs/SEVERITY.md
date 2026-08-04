# Guida alla configurazione delle severity

Come NotifyHub decide che una notifica è `critical` invece che `info`, e come si
configura quella decisione.

- [In una frase](#in-una-frase)
- [La catena di precedenza](#la-catena-di-precedenza)
- [1. Severity esplicita](#1-severity-esplicita)
- [2. Exit code diverso da zero](#2-exit-code-diverso-da-zero)
- [3. Durata oltre la soglia](#3-durata-oltre-la-soglia)
- [4. Regole di severity (analisi del contenuto)](#4-regole-di-severity-analisi-del-contenuto)
- [5. Severity di default del receiver](#5-severity-di-default-del-receiver)
- [Quando la notifica non arriva](#quando-la-notifica-non-arriva)
- [Lo script wrapper `notifyhub-run.sh`](#lo-script-wrapper-notifyhub-runsh)
- [Provare prima di mettere in produzione](#provare-prima-di-mettere-in-produzione)
- [Dalla severity all'inoltro sui canali](#dalla-severity-allinoltro-sui-canali)
- [Ricette pronte](#ricette-pronte)
- [Errori tipici](#errori-tipici)
- [Riferimento API](#riferimento-api)

---

## In una frase

Ogni notifica riceve **una** severity fra `debug`, `info`, `warning`, `error`,
`critical`. La sceglie il server al momento dell'ingestione, seguendo quattro
passaggi in ordine fisso: chi invia può **dichiararla**, altrimenti la impone
l'**esito dell'esecuzione** (exit code diverso da zero, oppure durata oltre la
soglia configurata), altrimenti le **regole** la deducono dal contenuto,
altrimenti vale la **severity di default**.

Le regole sono di due tipi e vengono provate in quest'ordine: prima quelle
scritte sul singolo receiver, poi quelle dei **preset** applicati — insiemi di
regole già pronti (`Bash generico`, `PostgreSQL`, `MongoDB`, `tar`, `rclone`),
condivisi fra i receiver e modificabili dalla dashboard.

La severity non è un'etichetta decorativa: è la soglia che decide se il
messaggio finisce su Slack o Google Chat, o se resta solo in dashboard.

Tutto questo vale per le notifiche che **arrivano**. Il guasto che non ne
produce nessuna — macchina spenta, cron rimosso, rete assente — lo copre la
[sorveglianza dell'attesa](#quando-la-notifica-non-arriva), che è l'unica cosa
in questa guida a nascere dal server e non da un invio.

---

## La catena di precedenza

```
                    ┌──────────────────────────────────────────┐
  POST /ingest/SLUG │ 1. Severity esplicita?                   │
        ────────────▶│    header X-Severity o query ?severity=  │──sì──▶ severity_source = explicit
                    └──────────────────┬───────────────────────┘
                                       │ no (o valore non valido)
                    ┌──────────────────▼───────────────────────┐
                    │ 2/3. Esito dell'esecuzione               │
                    │  exit code != 0  (X-Exit-Code)           │──sì──▶ severity_source = exit_code
                    │  durata > soglia (X-Duration-Ms)         │──sì──▶ severity_source = duration
                    │  entrambi → vince la severity più grave  │
                    └──────────────────┬───────────────────────┘
                                       │ nessuno dei due (header assenti, exit 0,
                                       │ durata sotto soglia, politiche disattivate)
                    ┌──────────────────▼───────────────────────┐
                    │ 4a. Regole scritte sul receiver          │
                    │    match sul contenuto INTERO, in ordine │──sì──▶ severity_source = rule
                    └──────────────────┬───────────────────────┘
                                       │ nessuna ha fatto match
                    ┌──────────────────▼───────────────────────┐
                    │ 4b. Regole dei preset applicati          │
                    │    nell'ordine dei preset                │──sì──▶ severity_source = preset_rule
                    └──────────────────┬───────────────────────┘
                                       │ nessuna regola ha fatto match
                    ┌──────────────────▼───────────────────────┐
                    │ 5. Severity di default del receiver      │───────▶ severity_source = receiver_default
                    └──────────────────────────────────────────┘
```

Exit code e durata sono **due fatti indipendenti allo stesso livello**, non due
passaggi in fila: se scattano entrambi vince la severity più grave delle due, e a
pari severity la notifica dichiara `exit_code`. Nessuno dei due può nascondere
l'altro — un job fallito con politica `warning` che ha anche sforato una soglia
`error` esce `error`.

La catena, con i valori configurati sul receiver che stai guardando, è
riassunta anche in dashboard: dettaglio del receiver, riquadro **Come viene
decisa la severity**.

Il passaggio che ha deciso resta scritto nella notifica come `severity_source`,
visibile nel dettaglio della notifica. **Quando una severity non torna, quello è
il primo campo da guardare**: dice subito se è stata imposta dal mittente,
dedotta dall'exit code, dedotta da una regola (e quale), o semplicemente il
default.

La risposta dell'ingestione lo riporta già:

```json
{
  "id": "0f2b…",
  "severity": "error",
  "severity_source": "rule",
  "forwarded_to": 1,
  "storage_backend": "inline"
}
```

---

## 1. Severity esplicita

Chi invia dichiara la severity e **salta tutti i passaggi successivi**:

```bash
curl --data "Servizio ripartito" -H "X-Severity: info" http://notifyhub/ingest/SLUG
curl --data "Servizio ripartito" "http://notifyhub/ingest/SLUG?severity=info"
```

L'header ha la precedenza sul parametro di query. Il valore non distingue
maiuscole e minuscole (`CRITICAL` = `critical`).

> **Un valore non valido non è un errore.** `X-Severity: banana` non fa fallire
> l'ingestione: viene ignorato in silenzio e la catena scende al passaggio
> successivo. Nessuna notifica deve andare persa per colpa di un'etichetta
> scritta male. Se una severity esplicita sembra ignorata, controlla
> `severity_source`: se dice qualcosa di diverso da `explicit`, il valore
> inviato non era valido.

Usa la severity esplicita solo quando il mittente ha una classificazione
propria da imporre. Per l'esito di uno script conviene il passaggio 2, che è
configurabile dal server.

---

## 2. Exit code diverso da zero

Chi invia dichiara **com'è andata**, non che severity vuole:

```bash
curl --data "@log.txt" -H "X-Exit-Code: 3" http://notifyhub/ingest/SLUG
```

Un exit code diverso da zero è il segnale più affidabile che esista: non dipende
da come lo script formatta i suoi messaggi, e non richiede nessuna regex. Cosa
farne lo decide il **receiver**, campo **Severity per exit code diverso da
zero** nel dettaglio del receiver:

| Valore | Effetto |
|---|---|
| `critical` (default) | ogni esecuzione fallita diventa `critical`, scavalcando le regole |
| altra severity | stessa cosa con la severity scelta |
| *nessun effetto* | l'header viene ignorato e decidono le regole |

Il vantaggio pratico: la politica si cambia **dalla dashboard**, non modificando
il crontab di ogni macchina che invia.

`X-Exit-Code: 0` non fa nulla — è il caso "tutto è andato bene", dove ha senso
lasciare la parola alle regole sul contenuto. Un valore non numerico viene
ignorato come una severity esplicita non valida.

Lo [script wrapper](#lo-script-wrapper-notifyhub-runsh) invia questo header da
solo, a ogni esecuzione.

---

## 3. Durata oltre la soglia

C'è un guasto che né l'exit code né nessuna regola sul contenuto sa vedere: il
job che **finisce bene, ma troppo tardi**. Il backup notturno che di solito
chiude in 5 minuti e stanotte ne ha impiegati 40 ha finito con exit code 0 e non
ha stampato una riga di errore, ma qualcosa non va — un disco che sta morendo, un
lock che non arriva, una rete che rallenta.

Chi invia dichiara quanto è durata l'esecuzione, in millisecondi:

```bash
curl --data "@log.txt" -H "X-Duration-Ms: 1200000" http://notifyhub/ingest/SLUG
```

Cosa farne lo decide il **receiver**, nel suo dettaglio, con due campi che vanno
sempre insieme:

| Campo | Significato |
|---|---|
| **Soglia di durata** | Quantità + unità (secondi, minuti, ore). Vuota = nessun controllo. |
| **Severity oltre la soglia di durata** | Severity applicata quando la durata supera la soglia. *nessun effetto* = controllo disattivato. |

Impostarne uno solo è un errore (`422`): una soglia senza severity non saprebbe
cosa assegnare, una severity senza soglia non scatterebbe mai. Per disattivare il
controllo si svuotano entrambi.

Il confronto è **stretto**: soglia di 10 minuti significa "avvisami se supera i
10 minuti", quindi un'esecuzione di esattamente 10 minuti non fa scattare niente.

Esempio della configurazione tipica — un backup che gira in 5 minuti, soglia a
10, severity `error`:

| Esecuzione | Exit code | Durata | Risultato |
|---|---|---|---|
| notte normale | 0 | 5m | `info` (default del receiver) |
| notte lenta | 0 | 20m | **`error`**, `severity_source = duration` |
| notte fallita | 1 | 30s | `critical` (politica sull'exit code) |
| fallita e lenta | 1 | 20m | `critical` — vince la più grave delle due |

Un valore non numerico o negativo viene ignorato come una severity esplicita non
valida, e l'ingestione non fallisce.

> **La durata viene registrata sempre**, anche senza nessuna soglia configurata:
> resta nel dettaglio della notifica e nell'elenco, e la si ritrova nel messaggio
> inviato ai canali. Serve anche a scoprire *dove* mettere la soglia — prima si
> guarda quanto durano davvero le esecuzioni, poi si sceglie il numero. E se la
> soglia viene aggiunta dopo, il [replay](#sui-messaggi-già-arrivati) mostra su
> quali esecuzioni passate avrebbe fatto scattare l'allarme.

Lo [script wrapper](#lo-script-wrapper-notifyhub-runsh) misura e invia questo
header da solo, a ogni esecuzione: nel crontab non cambia niente.

---

## 4. Regole di severity (analisi del contenuto)

È il cuore della configurazione: dashboard, dettaglio del receiver, sezione
**Regole di severity**. Ogni regola ha:

| Campo | Significato |
|---|---|
| **Ordine** | Posizione nella lista. Si cambia con le frecce ↑ ↓, non digitando numeri. |
| **Pattern** | Espressione regolare RE2, max 200 caratteri. |
| **Severity** | Severity assegnata se il pattern trova corrispondenza. |
| **Maiuscole** | *ignorate* (default) oppure *distinte*: con "ignorate", `errore` corrisponde anche a `ERRORE`. |
| **Stato** | Una regola disattivata viene saltata, senza doverla cancellare. |

### Come vengono valutate

1. Le regole vengono valutate **nell'ordine in cui compaiono nella tabella**,
   dall'alto verso il basso. La prima della lista porta il badge *valutata per
   prima*.
2. Si scartano quelle disattivate.
3. Esaurite le regole scritte qui, si passa a quelle dei **preset applicati**,
   nell'ordine dei preset (vedi [Preset di regole](#preset-di-regole)).
4. La **prima** che trova corrispondenza vince e la valutazione si ferma lì. Le
   successive non vengono nemmeno provate.
5. La corrispondenza è una *ricerca*: il pattern può comparire in qualsiasi
   punto del testo, senza bisogno di `.*` iniziali.

Il riquadro **Catena effettiva**, nel dettaglio del receiver, mostra l'elenco
già fuso: regole proprie e regole dei preset numerate nell'ordine reale di
valutazione, con l'indicazione di dove modificare ciascuna.

Esempio con tre regole su uno stesso receiver:

| # | Pattern | Severity |
|---|---|---|
| 1 | `PANIC\|FATAL\|OOMKilled` | critical |
| 2 | `ERROR\|ERRORE\|FALL(ITO\|IMENTO)` | error |
| 3 | `WARN\|attenzione\|deprecat` | warning |

Un messaggio che contiene sia `ERRORE` sia `attenzione` diventa `error`: la
seconda regola viene valutata prima della terza e ferma la catena. Per ottenere
`warning` bisogna **spostare la regola**, non riscrivere i pattern.

### L'ordine è unico e visibile

Dietro le quinte ogni regola ha un numero di priorità (10, 20, 30...) e il
database impone che sia **unico per receiver**: due regole non possono
condividere lo stesso posto in coda, quindi non esiste il caso "non si sa quale
vince". L'API risponde `409` a chi prova a salvare una priorità già occupata; la
dashboard non espone affatto il numero, usa le frecce e rinumera da sola.

### Nessun limite di lunghezza

**Le regole leggono il messaggio per intero.** Un errore in fondo a un log da 20
MB fa scattare la regola esattamente come uno in prima riga; non c'è nessuna
finestra iniziale da rispettare né bisogno di anteporre riepiloghi.

> Versioni precedenti campionavano solo i primi 8192 caratteri, e un errore
> oltre quella soglia non faceva scattare nulla. Il limite non esiste più.

RE2 ha tempo di esecuzione lineare, quindi la scansione completa ha un costo
prevedibile anche su corpi grandi; sopra qualche centinaio di kilobyte l'API
sposta la valutazione su un thread separato per non rallentare le altre
richieste. Nessuna configurazione richiesta.

### La sintassi dei pattern: RE2, non PCRE

I pattern sono compilati con [RE2](https://github.com/google/re2/wiki/Syntax),
non con le regex di Perl o Python. La scelta è deliberata: RE2 garantisce un
tempo di esecuzione lineare, quindi un pattern scritto male può essere inutile
ma **non può bloccare l'ingestione** con backtracking catastrofico.

| Costrutto | RE2 |
|---|---|
| `\d` `\w` `\s`, classi `[a-z]`, quantificatori `*` `+` `?` `{n,m}` | supportati |
| Alternanza `\|`, gruppi `( )`, ancore `^` `$` | supportati |
| Gruppi non catturanti `(?: )`, flag inline `(?i)` | supportati |
| **Lookahead / lookbehind** `(?= )` `(?! )` `(?<= )` | **non supportati** |
| **Backreference** `\1` | **non supportati** |

Un pattern non compilabile viene rifiutato al salvataggio con un errore 422 e il
messaggio di RE2 mostrato sotto il campo: non è possibile salvare una regola
rotta.

Attenzione ai caratteri speciali: per cercare il testo letterale `[ERRORE]`
serve `\[ERRORE\]`, perché le parentesi quadre nude aprono una classe di
caratteri.

---

## Preset di regole

Un **preset** è un insieme di regole con un nome, riusabile su quanti receiver
si vuole. Serve a non riscrivere venti volte le stesse righe: gli errori di
`tar` sono gli stessi su ogni macchina, quelli di `rclone` pure.

Si gestiscono nella sezione **Preset di regole** del menu; si applicano a un
receiver dal suo dettaglio, riquadro **Preset di regole applicati**.

### Quelli già pronti

| Preset | Copre |
|---|---|
| **Bash generico** | Errori di shell e coreutils: comando assente, permessi, disco pieno, segmentation fault, rete irraggiungibile, OOM. Da applicare a quasi tutti gli script. |
| **PostgreSQL** | Livelli di log del server (`PANIC:`, `FATAL:`, `ERROR:`, `WARNING:`) più gli errori tipici di `psql`, `pg_dump`, `pg_restore`. |
| **MongoDB** | Severità del log JSON di `mongod` (`"s":"F"`, `"s":"E"`, `"s":"W"`), errori di connessione e autenticazione, esiti di `mongodump`/`mongorestore`. |
| **tar** | Archivi danneggiati, file illeggibili, spazio esaurito, uscita con errori differiti; include gli errori di `gzip`. |
| **rclone** | Livelli `CRITICAL`/`ERROR`, quota esaurita, credenziali scadute, file corrotti in transito, riga finale `Errors: N`. |

Un receiver può usarne **più di uno** insieme: per un backup notturno che
comprime e sincronizza, la combinazione naturale è `Bash generico` + `tar` +
`rclone`.

### Come vengono installati

I preset predefiniti non sono codice immutabile: al momento dell'installazione
vengono **copiati dentro il tuo tenant** e da lì in poi sono regole come tutte le
altre, che puoi modificare, disattivare, cancellare.

- Un tenant nuovo li trova già installati.
- Un tenant esistente li installa con il pulsante **Installa i preset mancanti**
  nella sezione Preset (visibile solo se ne mancano), oppure da riga di comando:

  ```bash
  docker compose run --rm migrate python -m app.cli sync-presets
  ```

L'operazione è **additiva e ripetibile**: installa solo quello che manca e non
tocca mai una copia già presente, nemmeno se l'hai modificata. Un aggiornamento
dell'applicazione non ti sovrascrive le regole.

Per tornare ai valori di fabbrica di un preset predefinito c'è il pulsante
**Ripristina i valori predefiniti**, che rimette nome, descrizione e regole del
catalogo scartando le modifiche locali.

### Ordine e precedenza

1. Le regole scritte **sul receiver** vengono valutate per prime. Sono
   l'eccezione locale: servono a correggere un preset condiviso senza doverlo
   duplicare. Esempio: il preset `Bash generico` classifica `Permission denied`
   come `error`, ma su un receiver specifico quel messaggio è atteso — basta una
   regola locale che lo porti a `info`, e vincerà lei.
2. Poi vengono i preset, **nell'ordine in cui compaiono** nel riquadro del
   receiver (frecce ↑ ↓ per cambiarlo), e dentro ogni preset nell'ordine delle
   sue regole.

Quando decide una regola di preset, la notifica registra
`severity_source = preset_rule` e la dashboard mostra da quale preset arriva:
sai subito dove andare a correggerla.

> **Metti `Bash generico` per ultimo.** La sua ultima regola è una rete di
> sicurezza volutamente larga (`ERROR|ERRORE|FATAL|FAILED|…` → `error`), e vince
> su qualunque regola che venga dopo. Con l'ordine `Bash generico, tar, rclone`
> una riga come
>
> ```
> 2024/06/01 03:12:44 ERROR : dati/foto.jpg: corrupted on transfer: sizes differ
> ```
>
> diventa `error`, perché la rete di sicurezza la intercetta prima che rclone
> possa riconoscerla come `critical`. Con l'ordine `tar, rclone, Bash generico`
> la stessa riga diventa `critical`. Regola pratica: **prima i preset specifici,
> il generico in fondo.**

> **Attenzione**: modificare un preset cambia il comportamento di **tutti** i
> receiver che lo usano. La pagina Preset mostra per ognuno quanti receiver lo
> stanno usando.

### Preset personalizzati

Il pulsante **Nuovo preset** crea un insieme vuoto a cui aggiungere le proprie
regole. Vale la pena crearne uno quando le stesse regole servono su più
receiver; per una regola che riguarda un solo receiver conviene scriverla
direttamente su quel receiver.

I nomi sono unici per tenant: un nome già usato viene rifiutato con `409`.

### Permessi

| Azione | Ruolo minimo |
|---|---|
| Vedere i preset e le loro regole | qualsiasi ruolo |
| Creare, modificare, eliminare, ripristinare un preset | **admin** |
| Applicare o togliere preset a un receiver | **member** (sul gruppo del receiver) |

La scrittura richiede admin perché un preset è condiviso fra gruppi: chi lo
modifica tocca anche receiver che non gestisce. Applicarlo al proprio receiver,
invece, è una scelta locale.

### Aggiungere un preset predefinito (per chi sviluppa)

Il catalogo è un elenco di strutture dati in
`backend/app/services/severity_presets.py`. Per aggiungerne uno si scrive una
voce e la si mette in `BUILTIN_PRESETS`:

```python
RSYNC = PresetSpec(
    key="rsync",                      # identificatore stabile, non si cambia più
    name="rsync",
    description="Sincronizzazioni con rsync.",
    rules=(
        PresetRuleSpec(r"No space left on device", Severity.CRITICAL),
        PresetRuleSpec(r"rsync error:|failed to set times", Severity.ERROR),
        PresetRuleSpec(r"some files vanished", Severity.WARNING),
    ),
)

BUILTIN_PRESETS = (BASH_GENERIC, POSTGRES, MONGODB, TAR, RCLONE, RSYNC)
```

Non serve altro: nessuna migrazione, nessuna modifica alle API, nessuna modifica
alla dashboard. Gli utenti lo installano con `sync-presets` o con il pulsante.

Tre regole di scrittura, verificate da `tests/unit/test_severity_presets_catalog.py`:

1. **Solo regole che alzano la severity.** Niente `info` o `debug`: la prima
   regola che corrisponde vince, quindi classificare una riga innocua
   (`Removing leading / from member names` di tar) maschererebbe l'errore vero
   che arriva subito dopo nello stesso log. Il rumore si ignora, non si
   classifica.
2. **Ordine dal più grave al più lieve**: tutte le `critical`, poi le `error`,
   poi le `warning`. Una `warning` messa sopra una `critical` renderebbe la
   seconda irraggiungibile sugli stessi log.
3. **`case_insensitive=False` quando le maiuscole sono l'informazione**:
   `ERROR:` in un log PostgreSQL è un livello di log, `error` dentro una frase
   inglese no.

---

## 5. Severity di default del receiver

È l'ultima parola quando nessuna regola ha fatto match. Si imposta nel dettaglio
del receiver, campo **Severity di default**, ed è anche il valore scelto alla
creazione.

Come sceglierla:

- **`info`** per i receiver "rumorosi" (job periodici, log applicativi): il
  traffico normale resta silenzioso e solo le regole promuovono i casi degni di
  nota. È la scelta giusta quasi sempre.
- **`warning` o `error`** per i receiver che *dovrebbero tacere*: un endpoint su
  cui arriva un messaggio solo quando qualcosa non va. Qui il default alto
  significa "se questo receiver parla, guardalo".

---

## Quando la notifica non arriva

Un backup che fallisce manda un messaggio. Un backup che **non parte** non manda
niente: la macchina è spenta, cron è stato disabilitato, la rete verso NotifyHub
non c'è. Nessuna regola sul contenuto può vedere un contenuto che non esiste, e
l'unico che può accorgersene è il server.

Si dichiara sul receiver ogni quanto ci si aspetta un invio; un job di Celery
beat controlla ogni minuto chi ha sforato e scrive una **notifica di assenza**
con la severity configurata. Da lì in poi è una notifica come le altre: si vede
in elenco, ha un dettaglio, e passa dallo stesso instradamento per severity verso
Slack e Google Chat.

### Configurazione

| Campo del receiver | Significato |
|---|---|
| `expected_every_seconds` | intervallo fisso: "mi aspetto un invio ogni 24 ore" |
| `expected_cron` + `expected_timezone` | la stessa riga che sta nel crontab: `0 3 * * 1-5`, col fuso in cui quella macchina la interpreta |
| `expected_grace_seconds` | tolleranza: jitter di cron e durata del job |
| `missing_severity` | severity della notifica di assenza. `NULL` su tutto = sorveglianza spenta |

**Intervallo o cron, non entrambi.** L'intervallo è più semplice e non ha fusi
orari; l'espressione cron serve ai job non equispaziati. `0 3 * * 1-5` con un
intervallo fisso di 24 ore darebbe un falso allarme ogni sabato mattina, ed è
esattamente il motivo per cui esistono entrambe le modalità.

In dashboard: pagina del receiver → *Modifica receiver* → riquadro **Sorveglianza
dell'attesa**. La vista di sola lettura mostra la politica, l'ultimo invio vero e
la data entro cui è atteso il prossimo.

### Come si conta la scadenza

Con l'intervallo: `ultimo invio + intervallo + tolleranza`.

Con il cron: si guarda l'ultima occorrenza prevista. Se l'invio di quella
occorrenza è arrivato, si attende la prossima; se non è arrivato, la scadenza è
quella, più la tolleranza. Il conto avviene nel fuso dichiarato, quindi `0 3 * * *`
su `Europe/Rome` resta "le 3 di notte" anche nella notte in cui cambia l'ora
legale.

Un receiver che non ha mai ricevuto niente conta da quando la politica è entrata
in vigore (`expected_since`), non dall'inizio dei tempi: appena si accende la
sorveglianza c'è una finestra intera prima del primo allarme.

### Una notifica per assenza, non una al minuto

Quando l'assenza scatta, il receiver resta segnato (`missing_alerted_at`) e non
produce altre notifiche: una macchina spenta per una settimana genera **una**
notifica, non 10.080.

Al primo invio vero la sorveglianza si riarma e scrive una notifica di
**ripresa** con severity `info`, che chiude il cerchio sul canale dove era
arrivato l'allarme. Le notifiche sintetiche non contano come invio: se
contassero, l'assenza si riarmerebbe da sola.

| Origine (`severity_source`) | Severity | Chi l'ha scritta |
|---|---|---|
| `missing` | `missing_severity` del receiver | il server, job `check_expected_schedules` |
| `recovered` | sempre `info` | il server, allo stesso giro |

Nella sezione **Notifiche** le due origini si leggono nella colonna *Origine* e
si isolano col filtro *Origine della notifica* (`?source=missing`): "fammi vedere
solo i job che non hanno inviato". Nel dettaglio, `source_ip` vuoto e la nota in
testa dicono che il messaggio non l'ha mandato nessuno.

### Non e' partito, o non ha finito?

L'assenza dice che la conclusione non e' arrivata, non **perche'**. Sono due
guasti diversi da cercare in posti diversi:

- il cron non e' scattato (macchina spenta, riga rimossa dal crontab, unita
  systemd disabilitata);
- il job e' partito alle 3 e si e' interrotto a metà (macchina caduta, OOM killer,
  riavvio, processo ucciso).

Per distinguerli serve che qualcuno dica "sto partendo". Il wrapper lo fa con
`--ping-start`: prima di eseguire il comando manda un ping con l'header
`X-Phase: start` e severity `debug`.

```cron
0 3 * * *  /opt/notifyhub-run.sh -q --ping-start -- /usr/local/bin/backup.sh /dati
```

Il ping di avvio **non** e' un esito, e questo e' il punto:

- aggiorna `receivers.last_start_at`, non `last_notification_at`. Se contasse come
  conclusione, la sorveglianza tacerebbe proprio nel caso peggiore — il job morto
  a metà lavoro;
- viaggia con severity `debug` esplicita, cosi' nessuna regola sul contenuto puo'
  promuovere un "avvio" a `critical` e mandarlo su Slack;
- se non parte, il comando viene eseguito comunque: perdere un ping degrada la
  diagnosi, fermare un backup per un ping perso sarebbe peggio del guasto.

Con il dato disponibile la notifica di assenza cambia una riga:

| Situazione | Cosa dice l'allarme |
|---|---|
| avvio dopo l'ultima conclusione | «l'esecuzione partita il … non ha mai inviato la conclusione: il job **E' partito e si e' interrotto**» |
| nessun avvio dopo l'ultima conclusione | «non ne risulta partita nessun'altra: il job **non e' stato avviato**» |
| nessun ping di avvio mai ricevuto | «non e' possibile dire … questo receiver non riceve ping di avvio (`--ping-start`)» |

L'ultima riga e' voluta: senza il dato il sistema dichiara di non sapere invece di
indovinare. Nell'elenco delle notifiche i ping di avvio portano la marca *avvio*,
e in dashboard il receiver mostra *Ultimo avvio* accanto a *Ultima conclusione*.

Il costo e' un invio in piu' per esecuzione (quota e rate limit compresi): per un
backup notturno sono due notifiche al giorno, per un controllo ogni 5 minuti sono
576. Per questo l'opzione e' esplicita e non attiva per default.


### Trappole

**`--only-on-failure` e la sorveglianza non convivono.** Se il job invia solo
quando fallisce, ogni esecuzione riuscita è un'assenza e l'allarme scatta ogni
giorno senza motivo. Con la sorveglianza attiva il wrapper deve inviare sempre;
per non far comparire i successi sui canali basta abbassarne la severity
(`--severity-ok debug`), non tacere.

**Receiver disabilitato e tenant sospeso non allarmano.** Sono stati voluti, non
guasti: sarebbero in assenza per definizione, per sempre.

**Il guardiano non guarda se stesso.** Vive dentro NotifyHub: vede morire le
macchine sorvegliate, non sé stesso. Se cade NotifyHub non se ne accorge nessuno,
e per quello serve un controllo esterno che interroghi `/healthz`.

**Tolleranza troppo stretta.** Un job che dura venti minuti e parte alle 3 arriva
alle 3:20: con tolleranza di cinque minuti l'assenza scatta ogni notte. La
tolleranza deve coprire il ritardo di partenza **più** la durata del job, perché
la notifica parte a fine esecuzione.


---

## Lo script wrapper `notifyhub-run.sh`

`scripts/notifyhub-run.sh` esegue un comando, ne raccoglie l'output e lo invia a
NotifyHub insieme all'esito.

```bash
notifyhub-run.sh -s SLUG_DEL_RECEIVER -- /usr/local/bin/backup.sh /dati
```

**Da dove prenderlo.** Nella pagina del receiver c'è il pulsante **Scarica lo
script**: restituisce questo stesso file con URL dell'istanza e slug già scritti
in due variabili in cima, nel blocco `configurazione`. Le variabili restano
modificabili a mano, e `NOTIFYHUB_URL`/`NOTIFYHUB_SLUG` e le opzioni `-u`/`-s`
continuano a scavalcarle. L'URL è quella pubblica risolta dal server (reverse
proxy e https compresi), la stessa mostrata come "URL di invio" nella pagina: non
va indovinata, e non cambia di nascosto fra dashboard e script.

Ogni invio porta due dati misurati dal wrapper:

| Header | Contenuto |
|---|---|
| `X-Exit-Code` | exit code reale del comando |
| `X-Duration-Ms` | durata dell'esecuzione in millisecondi |

Il wrapper **non** decide la severity: la decidono le politiche del receiver, i
[passaggi 2 e 3](#2-exit-code-diverso-da-zero). Il risultato pratico con la
configurazione di default è "comando fallito = `critical`", ma la regola vive
sul server e si cambia senza toccare le macchine — e la soglia di durata si
aggiunge dalla dashboard su un crontab già in produzione, senza toccare niente
sulle macchine.

Rientrano nel caso "diverso da zero" anche il comando inesistente (exit 127) e
il timeout di `--timeout` (exit 124).

**Il wrapper termina sempre con l'exit code del comando avvolto**, così cron,
systemd o il chiamante vedono l'esito reale. Un invio fallito (rete giù,
NotifyHub irraggiungibile) produce un avviso su stderr ma non altera l'exit
code, a meno di `--strict`.

### Il messaggio prodotto

```
[notifyhub] job=backup notturno esito=errore exit=3 durata=41.320s (41320ms) host=srv01 avvio=2026-08-03T03:00:01+02:00
[notifyhub] comando: /usr/local/bin/backup.sh /dati
[notifyhub] output (66 byte):
Avvio backup di /dati
copiati 128 file
ERRORE: disco pieno su /var
```

La durata compare in forma leggibile e in millisecondi: `41.320s` sotto il
minuto, `12m30s` sopra, `1h02m03s` oltre l'ora. È la stessa resa che si vede in
dashboard e nel messaggio inviato ai canali.

L'intestazione è testo come tutto il resto, quindi è aggredibile dalle regole
(`esito=errore`, `exit=3`) se vuoi trattarla come contenuto. L'unico taglio che
il wrapper applica è quello dimensionale di `--max-bytes`, per non farsi
rifiutare con `413` dal receiver: in quel caso tiene testa e coda del log e
segnala i byte omessi.

### Opzioni principali

| Opzione | Effetto |
|---|---|
| `-s, --slug SLUG` | Receiver di destinazione (obbligatorio, oppure `NOTIFYHUB_SLUG`) |
| `-u, --url URL` | URL base di NotifyHub (default `http://localhost`, oppure `NOTIFYHUB_URL`) |
| `-n, --name NOME` | Nome del job nell'intestazione (default: nome del comando) |
| `--severity SEV` | Forza la severity esplicita, scavalcando politica ed exit code |
| `--severity-ok SEV` / `--severity-fail SEV` | Forza la severity solo in caso di successo / fallimento |
| `--only-on-failure` | Invia solo se il comando fallisce |
| `--timeout SEC` | Uccide il comando dopo SEC secondi (exit 124 → fallimento) |
| `--max-bytes N` | Tronca il corpo a N byte (default 1000000) |
| `--dry-run` | Stampa messaggio e header invece di inviarli |
| `--strict` | Esce con 1 se l'invio fallisce |
| `-q, --quiet` | Non ristampa l'output del comando |

`notifyhub-run.sh --help` per l'elenco completo.

### In crontab

```cron
NOTIFYHUB_URL=http://notifyhub.interno
NOTIFYHUB_SLUG=maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ

# Al posto di:  0 3 * * * /usr/local/bin/backup.sh /dati
0 3 * * *  /opt/notifyhub-run.sh -q -n "backup notturno" --timeout 7200 -- /usr/local/bin/backup.sh /dati

# Controllo che deve parlare solo quando qualcosa non va
*/5 * * * * /opt/notifyhub-run.sh -q --only-on-failure -- /usr/local/bin/check_disco.sh
```

`-q` evita che cron mandi un'email con lo stesso output che sta già andando a
NotifyHub.

---

## Provare prima di mettere in produzione

Nel dettaglio del receiver, sezione **Prova severity**, ci sono due strumenti.

### Su un testo inventato

Si incolla un contenuto di esempio, opzionalmente un exit code e una durata
simulati, e la dashboard mostra la severity risolta, il passaggio che ha deciso e
— se ha vinto una regola — quale pattern ha fatto match. Non scrive nessuna
notifica. La durata simulata è il modo per provare una soglia senza dover
aspettare che un job vada davvero lungo.

```bash
curl -X POST http://notifyhub/api/v1/receivers/$RECEIVER_ID/test-severity \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"content": "ERRORE: disco pieno su /var", "exit_code": 0}'
```

```json
{
  "severity": "error",
  "source": "rule",
  "matched_rule_id": "9c1e…",
  "matched_pattern": "ERROR|ERRORE|FALL(ITO|IMENTO)",
  "duration_exceeded": false
}
```

Con una durata simulata oltre la soglia (`{"content": "tutto liscio",
"duration_ms": 1200000}`) la risposta diventa `"source": "duration"` e
`"duration_exceeded": true`. Il campo `duration_exceeded` resta `true` anche
quando ha deciso un altro passaggio: dice che quell'esecuzione era comunque
lenta.

### Sui messaggi già arrivati

Il pulsante **Prova sulle ultime notifiche ricevute** rivaluta gli ultimi
messaggi realmente arrivati su quel receiver con le politiche *attuali* — regole,
politica sull'exit code e soglia di durata — e mostra riga per riga la severity
registrata all'epoca accanto a quella che avrebbero oggi, marcando con `cambia`
quelle che differiscono. Exit code e durata di ogni esecuzione sono conservati
sulla notifica, quindi la rivalutazione è fedele: è il modo per vedere su quali
notti passate una soglia appena scelta avrebbe suonato.

È il modo per rispondere alla domanda che il testo inventato non copre: *questa
modifica che effetto ha sul traffico vero?*

```bash
curl "http://notifyhub/api/v1/receivers/$RECEIVER_ID/severity-rules/replay?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

Nota: per le notifiche il cui payload è finito su object storage viene
rivalutata solo l'anteprima, ed è segnalato nella riga.

Per il wrapper, il modo più fedele di provare è `--dry-run`: mostra esattamente
corpo e header che verrebbero inviati, senza toccare il server.

---

## Dalla severity all'inoltro sui canali

La severity da sola non inoltra niente. L'ordine è:

```
debug  <  info  <  warning  <  error  <  critical
```

Una notifica viene inoltrata a un canale quando **la sua severity raggiunge o
supera la soglia** configurata per la coppia (gruppo, canale) — pagina
**Canali**, sezione *Soglie per gruppo*. Con soglia `warning` passano `warning`,
`error` e `critical`; restano fuori `info` e `debug`.

Il singolo receiver può deviare da quella soglia con un **override** (pagina
Canali, sezione *Override per receiver*):

- **silenzia**: quel receiver non inoltra mai su quel canale, qualunque severity;
- **sostituisci la soglia**: quel receiver usa una soglia sua invece di quella
  del gruppo.

Quindi una notifica `critical` può non arrivare su Slack per tre motivi diversi:
il canale non è collegato al gruppo, un override la silenzia, o il canale è
disattivato. La pagina **Consegne** mostra riga per riga cosa è stato inoltrato
e perché è fallito.

---

## Ricette pronte

### Job periodico (backup, sincronizzazioni, pulizie)

- Severity di default del receiver: **`info`**.
- Severity per exit code diverso da zero: **`critical`** (default).
- Invio tramite `notifyhub-run.sh`: il fallimento diventa `critical` senza
  scrivere nessuna regola.
- Regole per i guasti che *non* alzano l'exit code (uno script che stampa
  l'errore ed esce comunque con 0):

  | # | Pattern | Severity |
  |---|---|---|
  | 1 | `ERRORE\|ERROR\|FALL(ITO\|IMENTO)\|failed` | error |
  | 2 | `attenzione\|WARN\|spazio residuo` | warning |

- Soglia di durata: misura qualche notte a vuoto, guarda le durate registrate nel
  dettaglio delle notifiche, poi imposta la soglia al **doppio** del tempo tipico
  con severity `error`. Un backup da 5 minuti che ne impiega 20 diventa un allarme
  anche se è finito con exit code 0.
- Soglia del canale: `error`. Il backup riuscito e nei tempi resta in dashboard,
  quello fallito o lento arriva su Slack.

### Log applicativo inoltrato in streaming

- Severity di default: **`info`**, exit code: *nessun effetto* (non c'è nessun
  comando che termina).
- Regole ancorate al formato del log, non a parole sparse — molto più preciso:

  | # | Pattern | Severity |
  |---|---|---|
  | 1 | `^\[(FATAL\|PANIC)\]` | critical |
  | 2 | `^\[ERROR\]` | error |
  | 3 | `^\[WARN\]` | warning |

  Con `^` serve che la riga cominci così: `mostra un [ERROR] risolto` non fa
  scattare nulla, mentre con il pattern `ERROR` nudo sarebbe scattato.

### Monitor che deve tacere

- Severity di default: **`error`** — se questo receiver parla, è un problema.
- Nessuna regola, oppure una sola per declassare il rumore noto:

  | # | Pattern | Severity |
  |---|---|---|
  | 1 | `manutenzione programmata` | info |

### Silenziare un rumore noto senza perdere il resto

Una regola in cima alla lista che assegna `debug`:

| # | Pattern | Severity |
|---|---|---|
| 1 | `connessione ristabilita\|retry riuscito` | debug |
| 2 | `ERRORE` | error |

Il messaggio resta consultabile in dashboard ma non supera nessuna soglia di
inoltro.

### Job che deve stare dentro una finestra

Un job notturno che deve finire prima che ricominci il lavoro degli utenti: la
soglia non serve a dire "è andato male", ma "sta invadendo la finestra". Soglia di
durata pari al tempo residuo della finestra, severity `warning`, politica
sull'exit code lasciata a `critical`. Chi guarda Slack distingue subito il job
fallito (`critical`) dal job che ha sforato (`warning`).

### Job dove il fallimento non è grave

Un job che fallisce spesso e senza conseguenze: metti la politica sull'exit code
a `warning` invece di `critical`. Nessuna modifica agli script sulle macchine.

---

## Errori tipici

| Sintomo | Causa quasi sempre |
|---|---|
| Scatta la regola sbagliata | Un'altra regola **più in alto nella lista** ha fatto match prima e ha fermato la catena. Guarda `matched_pattern` nel dettaglio della notifica, poi usa le frecce per spostare le regole. |
| La regola non scatta mai | Pattern con lookahead o backreference (non esistono in RE2), oppure caratteri speciali non protetti: `[ERRORE]` va scritto `\[ERRORE\]`. Provalo con **Prova severity**. |
| Tutto è `critical`, le regole sembrano ignorate | Il mittente sta inviando `X-Exit-Code` diverso da zero e la politica del receiver è `critical`: è il passaggio 2 che vince, `severity_source` dice `exit_code`. |
| La soglia di durata non scatta mai | Il mittente non manda `X-Duration-Ms` (non passa dal wrapper, o è una versione precedente alla 1.2.0): senza durata dichiarata il passaggio 3 tace. Nel dettaglio della notifica il campo durata è vuoto. |
| La soglia di durata scatta ma la notifica non arriva su Slack | La severity scelta per la soglia è sotto la soglia del canale: una soglia di durata `warning` su un canale a `error` resta in dashboard. |
| Salvando la soglia di durata arriva `422` | Soglia e severity vanno impostate insieme: o entrambe, o nessuna delle due. |
| La severity esplicita viene ignorata | Valore fuori dai cinque ammessi: viene scartato in silenzio. `severity_source` lo conferma. |
| `severity_source` dice sempre `receiver_default` | Nessuna regola attiva sul receiver e nessun preset applicato, o tutte disattivate. Il riquadro **Catena effettiva** lo mostra a colpo d'occhio. |
| Una regola di un preset non scatta | Un'altra regola vince prima: guarda la **Catena effettiva**, dove le regole proprie del receiver compaiono sopra quelle dei preset. |
| Ho modificato un preset e sono cambiati receiver che non volevo | Un preset è condiviso. La pagina Preset dice quanti receiver lo usano; per l'eccezione locale scrivi una regola sul singolo receiver invece di modificare il preset. |
| Salvando una regola arriva `409` | Stai usando l'API con una priorità già occupata su quel receiver: le priorità sono uniche. Dalla dashboard il problema non si presenta. |
| La notifica ha la severity giusta ma non arriva su Slack | È un problema di soglie, non di severity: vedi [Dalla severity all'inoltro](#dalla-severity-allinoltro-sui-canali). |

---

## Riferimento API

Tutte le rotte richiedono `Authorization: Bearer <access_token>`, tranne
l'ingestione che usa lo slug come sola credenziale.

| Operazione | Chiamata | Ruolo minimo |
|---|---|---|
| Elenco regole del receiver | `GET /api/v1/receivers/{id}/severity-rules` | viewer (sui propri gruppi) |
| Crea regola | `POST /api/v1/receivers/{id}/severity-rules` | member (sui propri gruppi) |
| Modifica regola | `PATCH /api/v1/severity-rules/{rule_id}` | member |
| Elimina regola | `DELETE /api/v1/severity-rules/{rule_id}` | member |
| Riordina tutte le regole | `PUT /api/v1/receivers/{id}/severity-rules/order` | member |
| Prova la catena su un testo | `POST /api/v1/receivers/{id}/test-severity` | viewer |
| Rivaluta le ultime notifiche | `GET /api/v1/receivers/{id}/severity-rules/replay` | viewer |
| Catena effettiva (regole proprie + preset, in ordine) | `GET /api/v1/receivers/{id}/severity-chain` | viewer |
| Severity di default, politica exit code e soglia di durata | `PATCH /api/v1/receivers/{id}` | member |
| Invio | `POST /ingest/{slug}` con `X-Severity`, `?severity=`, `X-Exit-Code`, `X-Duration-Ms` | — (slug) |

Campi del receiver che governano i passaggi 2 e 3:

```bash
curl -X PATCH http://notifyhub/api/v1/receivers/$RECEIVER_ID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"exit_code_severity": "critical",
       "duration_threshold_seconds": 600,
       "duration_severity": "error"}'
```

`duration_threshold_seconds` e `duration_severity` vanno inviati insieme; per
disattivare il controllo si mandano entrambi a `null`. La durata e l'exit code di
ogni esecuzione si rileggono su `GET /api/v1/notifications/{id}` (campi
`duration_ms`, `exit_code`) e nell'elenco delle notifiche.

Preset:

| Operazione | Chiamata | Ruolo minimo |
|---|---|---|
| Elenco preset del tenant | `GET /api/v1/severity-presets` | viewer |
| Catalogo predefinito e stato di installazione | `GET /api/v1/severity-presets/catalog` | viewer |
| Installa i predefiniti mancanti | `POST /api/v1/severity-presets/sync-builtin` | admin |
| Dettaglio con le regole | `GET /api/v1/severity-presets/{id}` | viewer |
| Crea / rinomina / elimina | `POST`, `PATCH`, `DELETE /api/v1/severity-presets[/{id}]` | admin |
| Ripristina i valori di catalogo | `POST /api/v1/severity-presets/{id}/reset` | admin |
| Regole del preset | `POST /api/v1/severity-presets/{id}/rules`, `PATCH`/`DELETE /api/v1/severity-preset-rules/{rule_id}` | admin |
| Riordina le regole del preset | `PUT /api/v1/severity-presets/{id}/rules/order` | admin |
| Preset applicati a un receiver | `GET /api/v1/receivers/{id}/presets` | viewer |
| Applica preset a un receiver | `PUT /api/v1/receivers/{id}/presets` | member |

L'applicazione dei preset a un receiver è una **sostituzione**: il corpo elenca
tutti i preset voluti, nell'ordine di valutazione. Un elenco vuoto li stacca
tutti.

```json
{ "preset_ids": ["4a1c…", "77b0…", "0e93…"] }
```

Creazione di una regola — `priority` è **opzionale**: se assente la regola viene
accodata in fondo (massima priorità esistente + 10).

```json
{
  "pattern": "ERRORE|FALL(ITO|IMENTO)",
  "case_insensitive": true,
  "severity": "error",
  "enabled": true
}
```

Riordino — l'elenco deve contenere **tutte** le regole del receiver esattamente
una volta; il backend rinumera 10, 20, 30...

```json
{ "rule_ids": ["9c1e…", "3f0a…", "b721…"] }
```

Politica sull'exit code — `null` è un valore, non "campo assente": disattiva la
politica. Vale allo stesso modo per la coppia della durata.

```json
{ "exit_code_severity": "warning" }
{ "exit_code_severity": null }
{ "duration_threshold_seconds": 600, "duration_severity": "error" }
{ "duration_threshold_seconds": null, "duration_severity": null }
```

Risposte di errore rilevanti: `422` se il pattern non è compilabile da RE2 (il
dettaglio riporta il messaggio di RE2), se il riordino non elenca tutte le
regole o se lo stesso preset compare due volte; `409` se la priorità richiesta è
già occupata, se il nome del preset è già usato o se si tenta di ripristinare un
preset creato a mano; `404` per un preset di un altro tenant; `403` se il
receiver appartiene a un gruppo non associato all'utenza.

---

## Dove vive il codice

| Cosa | File |
|---|---|
| Catena di precedenza, cache dei pattern, offload su thread | `backend/app/services/severity.py` |
| Costruzione della catena (regole proprie + preset, in ordine) | `backend/app/services/rule_chain.py` |
| Catalogo dei preset predefiniti e installazione | `backend/app/services/severity_presets.py` |
| CRUD preset e loro regole | `backend/app/api/v1/presets.py` |
| Tabelle dei preset | migrazione `0009` |
| Scansione del contenuto in ingestione | `backend/app/services/ingest.py` |
| Endpoint di ingestione (`X-Severity`, `?severity=`, `X-Exit-Code`, `X-Duration-Ms`) | `backend/app/api/ingest.py` |
| CRUD regole, riordino, prova, replay | `backend/app/api/v1/receivers.py` |
| Politica exit code per receiver | migrazione `0007`, colonna `receivers.exit_code_severity` |
| Soglia di durata per receiver, durata ed exit code sulle notifiche | migrazione `0010`, colonne `receivers.duration_threshold_seconds`, `receivers.duration_severity`, `notifications.duration_ms`, `notifications.exit_code` |
| Durata leggibile nei messaggi ai canali | `backend/app/outbound/formatters/duration.py`, `frontend/src/lib/duration.ts` |
| Unicità delle priorità | migrazione `0008` |
| Soglie di inoltro e override | `backend/app/services/outbound_resolver.py` |
| Ordine delle severity | `backend/app/db/types.py` (`SEVERITY_ORDER`) |
| Pannello regole in dashboard | `frontend/src/components/SeverityRulesPanel.tsx` |
| Sezione Preset e pannello preset del receiver | `frontend/src/pages/PresetsPage.tsx`, `frontend/src/components/ReceiverPresetsPanel.tsx` |
| Script wrapper | `scripts/notifyhub-run.sh` |
| Sorveglianza dell'attesa: calcolo e testi | `backend/app/services/surveillance.py` |
| Job che genera assenza e ripresa | `check_expected_schedules` in `backend/app/tasks/maintenance.py`, ogni 60s |
| Colonne dell'attesa | migrazione `0012` su `receivers` |
| Fase dell'esecuzione (`X-Phase`) | migrazione `0013`: `notifications.phase`, `receivers.last_start_at`; parser in `services/severity.py` |
| Download dello script precompilato | `backend/app/services/wrapper_script.py`, endpoint `GET /api/v1/receivers/{id}/wrapper-script` |
| Slug parlante e URL pubblica | `backend/app/services/slug.py`, `backend/app/core/urls.py`, migrazione `0011` |
