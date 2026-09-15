# Audit — Plan Overview

> **Status:** DONE (2026-09-15) | **Autore:** 2026-09-15
> **Cartella:** `docs/plans/plan_audit/`

## Goal

Owner e admin hanno sotto **Impostazioni** una sezione **Audit** che mostra chi ha
fatto cosa nell'applicazione, con una sotto-sezione dedicata alle operazioni
"segna come letta" e "segna come verificata", perché è lì che sta la domanda
ricorrente: *chi ha gestito questa notifica?*

```
Scenario di riferimento:
1. Un member apre /notifications e clicca "Segna come verificata" su n1.
2. L'owner apre /settings/audit: la riga c'è — quando, chi, da quale IP,
   verified false -> true.
3. L'owner apre /settings/audit/notifiche e filtra per quella notifica:
   vede tutta la storia, compresi i ripristini (verificata -> non verificata).
4. Un admin vede le stesse due pagine. Un member o un viewer riceve 403
   dall'API e "Accesso negato" dalla UI.
5. Un tenant non vede mai gli eventi di un altro: RLS come per ogni altra
   tabella di tenant.
```

## Decisioni (rispondono alle aree grigie poste all'utente)

| # | Decisione | Perché |
|---|---|---|
| D1 | **Copertura**: ogni mutazione autenticata di `/api/v1` più gli eventi di autenticazione | Un endpoint nuovo è tracciato per costruzione, senza doverselo ricordare: l'evento nasce da un hook `before_flush` di SQLAlchemy, non da una riga scritta a mano nel router |
| D2 | **Contenuto**: metadati (attore, ruolo, azione, risorsa, esito, IP, user-agent, request id) più il diff prima/dopo dei soli campi cambiati, con mascheramento dei segreti | Risponde a "cosa è stato cambiato" senza copiare in una tabella leggibile dagli admin i corpi delle notifiche o le credenziali dei canali |
| D3 | **Letta/verificata**: storico completo di ogni passaggio, non solo l'ultimo stato | "Chi ha gestito la notifica" deve restare vero anche dopo un ripristino; l'ultimo stato lo dice già la notifica stessa |
| D4 | **Ritenzione**: campo dedicato `tenants.audit_retention_days` (default 365) con purge notturna, ed export CSV/JSON di ciò che è filtrato a schermo | L'audit deve sopravvivere alle notifiche che descrive: `retention_days` è spesso 90 o meno |
| D5 | Una sola tabella `audit_events`; la sezione letta/verificata è una **vista filtrata** su di essa | Due tabelle vorrebbero dire due ritenzioni, due purge e due verità sullo stesso fatto |
| D6 | L'evento nasce **nella stessa transazione** della modifica | Un audit scritto a parte può mancare proprio quando serve (crash fra la modifica e la scrittura dell'evento). Se l'audit non si scrive, la modifica non si scrive |
| D7 | L'ingestion e i job Celery **non** producono eventi | Non hanno un attore umano e la notifica stessa è già il proprio registro; l'audit sarebbe un secondo giornale del traffico di macchina |
| D8 | `/settings` passa da owner a **owner + admin**, con la scheda "Generali" ancora riservata all'owner | L'utente chiede l'audit per entrambi i ruoli, ma le quote del tenant restano una decisione dell'owner |
| D9 | **Login falliti**: evento solo quando l'email corrisponde a un utente esistente; email sconosciuta resta nei soli log strutturati | La tabella e tenant-scoped sotto RLS: senza utente non c'e tenant, e una riga senza tenant vorrebbe dire o una policy di eccezione o una seconda tabella. L'admin vede comunque gli attacchi ai *suoi* account |
| D10 | **bulk-read**: un solo evento con i filtri usati, il conteggio e l'array degli id toccati (jsonb + indice GIN), con un tetto di 5.000 id oltre il quale si registrano solo filtri e conteggio | N righe per un bulk da 50.000 non lette sarebbero 50.000 insert in transazione; l'array indicizzato risponde lo stesso a "chi ha segnato letta QUESTA notifica" |
| D11 | **Nessuna FK verso `notifications`**: `resource_id` e un uuid nudo, accompagnato da `resource_label` (snapshot leggibile al momento del fatto) | L'audit vive 365 giorni, la notifica 90: una FK la cancellerebbe (CASCADE) o la renderebbe muta (SET NULL). Lo snapshot sopravvive alla purge |
| D12 | **Attore**: `actor_user_id` con `ON DELETE SET NULL`, piu `actor_email` e `actor_role` congelati nella riga | Cancellare un utente non deve rendere anonima la sua storia |
| D13 | **Sulla notifica** restano denormalizzati `read_by`/`read_at`/`verified_by`/`verified_at`, visibili a chiunque veda la notifica; l'audit completo resta owner+admin | Il member che lavora la coda deve sapere chi ha gia verificato senza avere accesso all'audit; lo storico dei ripristini resta riservato |
| D14 | `audit_events` e append-only per l'applicazione via `REVOKE UPDATE`; il `DELETE` resta perche la purge di ritenzione gira con lo stesso ruolo `notifyhub_app` | Un `REVOKE DELETE` richiederebbe un quarto ruolo solo per la purge notturna: il guadagno non paga la complessita operativa (vedi "Fuori scope": il DBA resta fidato) |


## Fasi

1. **Schema** — enum `audit_outcome`, tabella `audit_events` con RLS e `REVOKE UPDATE`, colonna `tenants.audit_retention_days` (default 365), colonne denormalizzate `notifications.read_by/read_at/verified_by/verified_at`, migrazione `0016`.
2. **Motore** — `app/services/audit.py`: contesto di richiesta, hook `before_flush` con diff e mascheramento, registro delle risorse, API di registrazione esplicita.
3. **Eventi espliciti** — login riuscito e fallito, logout, `bulk-read` (che non passa dall'ORM).
4. **API** — `GET /api/v1/audit/events`, `/audit/notification-status`, `/audit/export`, tutti `require_admin`.
5. **Ritenzione** — task Celery `purge_audit_events` e voce di beat; `audit_retention_days` in Impostazioni.
6. **Frontend** — `/settings` a schede: Generali (owner), Audit, Letture e verifiche; voce di menu per owner e admin.
7. **Documentazione** — spec §4.4, §9.6 e §11, OPERAZIONI (sezione "Audit" e job 2).

## Esito

Tutte le fasi sono implementate e verificate:

- migrazione `0016_audit_events` (tabella, RLS, `REVOKE UPDATE`, indice GIN, `tenants.audit_retention_days`, colonne denormalizzate sulle notifiche);
- `app/services/audit.py` (contesto di richiesta, hook `before_flush`, mascheramento, registro risorse);
- eventi espliciti per login riuscito/fallito, logout e `bulk-read`;
- `GET /api/v1/audit/events|notification-status|export`, tutti `require_admin`;
- job `purge_audit_events` (05:00) e campo di ritenzione in Impostazioni;
- frontend: Impostazioni a schede, pagine Audit e Letture e verifiche, "letta/verificata da" sul dettaglio notifica;
- test: 13 unit, 17 e2e, 5 integration lato backend; 4 e2e di pagina + 2 di Impostazioni lato frontend.

## Fuori scope dichiarato

- Eventi per le richieste **rifiutate** (403/422): nulla è cambiato, e il rifiuto è già nei log strutturati. Fa eccezione il login fallito, che è il segnale di sicurezza per cui l'audit esiste.
- Firma o catena di hash delle righe (append-only crittografico): la tabella è append-only per l'applicazione, ma un DBA resta fidato.
