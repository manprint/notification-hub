# Guida alla configurazione delle severity

Come NotifyHub decide che una notifica è `critical` invece che `info`, e come si
configura quella decisione.

- [In una frase](#in-una-frase)
- [La catena di precedenza](#la-catena-di-precedenza)
- [1. Severity esplicita](#1-severity-esplicita)
- [2. Exit code diverso da zero](#2-exit-code-diverso-da-zero)
- [3. Regole di severity (analisi del contenuto)](#3-regole-di-severity-analisi-del-contenuto)
- [4. Severity di default del receiver](#4-severity-di-default-del-receiver)
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
passaggi in ordine fisso: chi invia può **dichiararla**, altrimenti un **exit
code diverso da zero** la impone, altrimenti le **regole del receiver** la
deducono dal contenuto, altrimenti vale la **severity di default**.

La severity non è un'etichetta decorativa: è la soglia che decide se il
messaggio finisce su Slack o Google Chat, o se resta solo in dashboard.

---

## La catena di precedenza

```
                    ┌──────────────────────────────────────────┐
  POST /ingest/SLUG │ 1. Severity esplicita?                   │
        ────────────▶│    header X-Severity o query ?severity=  │──sì──▶ severity_source = explicit
                    └──────────────────┬───────────────────────┘
                                       │ no (o valore non valido)
                    ┌──────────────────▼───────────────────────┐
                    │ 2. Exit code diverso da zero?            │
                    │    header X-Exit-Code + politica del     │──sì──▶ severity_source = exit_code
                    │    receiver                              │
                    └──────────────────┬───────────────────────┘
                                       │ assente, uguale a 0, o politica disattivata
                    ┌──────────────────▼───────────────────────┐
                    │ 3. Regole di severity del receiver       │
                    │    match sul contenuto INTERO, in ordine │──sì──▶ severity_source = rule
                    └──────────────────┬───────────────────────┘
                                       │ nessuna regola ha fatto match
                    ┌──────────────────▼───────────────────────┐
                    │ 4. Severity di default del receiver      │───────▶ severity_source = receiver_default
                    └──────────────────────────────────────────┘
```

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

## 3. Regole di severity (analisi del contenuto)

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
3. La **prima** che trova corrispondenza vince e la valutazione si ferma lì. Le
   successive non vengono nemmeno provate.
4. La corrispondenza è una *ricerca*: il pattern può comparire in qualsiasi
   punto del testo, senza bisogno di `.*` iniziali.

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

## 4. Severity di default del receiver

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

## Lo script wrapper `notifyhub-run.sh`

`scripts/notifyhub-run.sh` esegue un comando, ne raccoglie l'output e lo invia a
NotifyHub insieme all'esito.

```bash
notifyhub-run.sh -s SLUG_DEL_RECEIVER -- /usr/local/bin/backup.sh /dati
```

Ogni invio porta l'header `X-Exit-Code` con l'exit code reale del comando. Il
wrapper **non** decide la severity: la decide il receiver, con la politica del
[passaggio 2](#2-exit-code-diverso-da-zero). Il risultato pratico con la
configurazione di default è "comando fallito = `critical`", ma la regola vive
sul server e si cambia senza toccare le macchine.

Rientrano nel caso "diverso da zero" anche il comando inesistente (exit 127) e
il timeout di `--timeout` (exit 124).

**Il wrapper termina sempre con l'exit code del comando avvolto**, così cron,
systemd o il chiamante vedono l'esito reale. Un invio fallito (rete giù,
NotifyHub irraggiungibile) produce un avviso su stderr ma non altera l'exit
code, a meno di `--strict`.

### Il messaggio prodotto

```
[notifyhub] job=backup notturno esito=errore exit=3 durata=41s host=srv01 avvio=2026-08-03T03:00:01+02:00
[notifyhub] comando: /usr/local/bin/backup.sh /dati
[notifyhub] output (66 byte):
Avvio backup di /dati
copiati 128 file
ERRORE: disco pieno su /var
```

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
NOTIFYHUB_SLUG=Kj8mQ2xN7vB4pR9wLs3tYc

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

Si incolla un contenuto di esempio, opzionalmente un exit code simulato, e la
dashboard mostra la severity risolta, il passaggio che ha deciso e — se ha vinto
una regola — quale pattern ha fatto match. Non scrive nessuna notifica.

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
  "matched_pattern": "ERROR|ERRORE|FALL(ITO|IMENTO)"
}
```

### Sui messaggi già arrivati

Il pulsante **Prova sulle ultime notifiche ricevute** rivaluta gli ultimi
messaggi realmente arrivati su quel receiver con le regole *attuali*, e mostra
riga per riga la severity registrata all'epoca accanto a quella che avrebbero
oggi, marcando con `cambia` quelle che differiscono.

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

- Soglia del canale: `error`. Il backup riuscito resta in dashboard, quello
  fallito arriva su Slack.

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
| La severity esplicita viene ignorata | Valore fuori dai cinque ammessi: viene scartato in silenzio. `severity_source` lo conferma. |
| `severity_source` dice sempre `receiver_default` | Nessuna regola attiva sul receiver, o tutte disattivate. |
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
| Severity di default e politica exit code | `PATCH /api/v1/receivers/{id}` | member |
| Invio | `POST /ingest/{slug}` con `X-Severity`, `?severity=`, `X-Exit-Code` | — (slug) |

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
politica.

```json
{ "exit_code_severity": "warning" }
{ "exit_code_severity": null }
```

Risposte di errore rilevanti: `422` se il pattern non è compilabile da RE2 (il
dettaglio riporta il messaggio di RE2) o se il riordino non elenca tutte le
regole; `409` se la priorità richiesta è già occupata; `403` se il receiver
appartiene a un gruppo non associato all'utenza.

---

## Dove vive il codice

| Cosa | File |
|---|---|
| Catena di precedenza, cache dei pattern, offload su thread | `backend/app/services/severity.py` |
| Scansione del contenuto in ingestione | `backend/app/services/ingest.py` |
| Endpoint di ingestione (`X-Severity`, `?severity=`, `X-Exit-Code`) | `backend/app/api/ingest.py` |
| CRUD regole, riordino, prova, replay | `backend/app/api/v1/receivers.py` |
| Politica exit code per receiver | migrazione `0007`, colonna `receivers.exit_code_severity` |
| Unicità delle priorità | migrazione `0008` |
| Soglie di inoltro e override | `backend/app/services/outbound_resolver.py` |
| Ordine delle severity | `backend/app/db/types.py` (`SEVERITY_ORDER`) |
| Pannello regole in dashboard | `frontend/src/components/SeverityRulesPanel.tsx` |
| Script wrapper | `scripts/notifyhub-run.sh` |
