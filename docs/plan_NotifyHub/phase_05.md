# Fase 4 — Management di dominio: gruppi, receiver, regole di severity, impostazioni del tenant

> **Intent:** rendere configurabile il dominio dalla API, cosi che la fase 5 abbia receiver reali da interrogare.
> **Shippable alone?** si — al termine si crea un gruppo, un receiver con slug e le sue regole, e le si prova, senza che l'ingestion esista ancora.
> **Preconditions:** fase 3 DONE.

Fonti autoritative: `notifyhub-spec.md` sezione 4.2 (colonne), sezione 9.3 (superficie API, cancellazione confermata, cap del tenant), sezione 7 (catena di severity).

Regola valida per tutti gli endpoint di questa fase: la sessione si ottiene **solo** con `Depends(db)` della fase 3 sotto-fase 3.5, e ogni rotta dichiara esattamente una fra `require_owner`, `require_admin`, `require_member`, `require_viewer`, secondo la matrice ruoli della specifica sezione 4.1.

---

## Sub-phases

### 4.1 Gruppi

- **Model:** Sonnet
- **Files:** `backend/app/schemas/group.py` (nuovo), `backend/app/api/v1/groups.py` (nuovo), `backend/app/main.py` (modificato).
- **Insertion point:** registrazione del router in `create_app()` sopra il commento sentinella `# ROUTERS:`, dopo i router della fase 3.
- **Pattern:** router con prefisso `/groups`, montato sotto `/api/v1` come i router esistenti in `app/api/v1/auth.py`.
- **Change:**
  - `GET /api/v1/groups` — `require_viewer`. Elenco dei gruppi del tenant con il numero di receiver.
  - `POST /api/v1/groups` — `require_member`. Nome unico per tenant: violazione -> `409` con `type=/problems/conflict`.
  - `GET|PATCH /api/v1/groups/{id}` — `require_viewer` in lettura, `require_member` in modifica.
  - `GET /api/v1/groups/{id}/delete-impact` — `require_member`. Restituisce i conteggi reali: `{"receivers": n, "notifications": n, "deliveries": n}`, calcolati con tre `SELECT count(*)`.
  - `DELETE /api/v1/groups/{id}` — `require_member`. Richiede il parametro di query `confirm`, che deve corrispondere **esattamente** al nome del gruppo. Se manca o non corrisponde -> `422` con `type=/problems/validation-error` e `detail` che indica il nome atteso. Se corrisponde, cancella: il `CASCADE` dello schema porta via receiver, notifiche e delivery, e il trigger della fase 1 accoda le chiavi degli oggetti (invariante I-8).
- **Test strategy:** e2e con client autenticato; per il cascade si conta prima e dopo.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_groups.py`:
  `T-MGMT1` `test_crea_e_elenca_gruppo` — creazione `201`, elenco contiene il gruppo con `receivers_count == 0`.
  `T-MGMT2` `test_nome_duplicato_rifiutato` — la seconda creazione con lo stesso nome restituisce `409`.
  `T-MGMT3` `test_delete_senza_conferma_rifiutato` — `DELETE` senza `confirm` restituisce `422` e il gruppo esiste ancora. Test di percorso negativo.
  `T-MGMT4` `test_delete_con_conferma_sbagliata_rifiutato` — `confirm=nome-errato` restituisce `422`.
  `T-MGMT5` `test_delete_impact_e_cascade` — creati due receiver e tre notifiche, `delete-impact` riporta i conteggi esatti; dopo la cancellazione confermata, receiver e notifiche del gruppo sono spariti e quelli di un secondo gruppo sono intatti.
  `T-MGMT6` `test_viewer_non_puo_creare` — con token `viewer`, `POST` restituisce `403`.
- **Done:** i sei test passano; `make gates` verde.

### 4.2 Receiver e slug

- **Model:** Sonnet
- **Files:** `backend/app/schemas/receiver.py` (nuovo), `backend/app/api/v1/receivers.py` (nuovo), `backend/app/main.py` (modificato).
- **Pattern:** la generazione dello slug e in una funzione unica `generate_slug() -> str` dentro `app/services/slug.py` (file nuovo), cosi esiste un solo punto che decide l'entropia.
- **Change:**
  - `generate_slug()` restituisce `secrets.token_urlsafe(16)`, che produce sempre 22 caratteri (128 bit di entropia, specifica sezione 4.2). Non usare `uuid4().hex`, non troncare, non aggiungere prefissi leggibili: uno slug prevedibile e l'unico modo di bucare l'ingestion.
  - `POST /api/v1/groups/{id}/receivers` — `require_member`. Genera lo slug, imposta i default (`status=active`, `ingestion_module=http_raw`, `default_severity=info`, `rate_limit_per_min=60`, `max_body_bytes` uguale al cap del tenant). Sulla collisione di slug, improbabile ma possibile, ritenta una volta e poi risponde `500`.
  - `GET /api/v1/groups/{id}/receivers` — `require_viewer`.
  - `GET|PATCH|DELETE /api/v1/receivers/{id}` — lettura `require_viewer`, modifica e cancellazione `require_member`.
  - **Validazione di `max_body_bytes` sul PATCH:** deve restare `<= tenants.max_body_bytes`; se lo supera -> `422` con `detail` che riporta il cap corrente. Deve inoltre restare `<= settings.notifyhub_hard_max_body_bytes`.
  - `POST /api/v1/receivers/{id}/rotate-slug` — **`require_admin`, non `require_member`**: rigenerare lo slug rompe gli script gia in produzione (specifica sezione 4.1). Restituisce il nuovo slug e lo vecchio non funziona piu.
  - La risposta di dettaglio include l'URL completo di ingestion, costruito da una nuova impostazione? No: costruiscilo dal solo `slug`, il frontend antepone l'origine. Non introdurre variabili d'ambiente nuove.
- **Test strategy:** e2e; per lo slug basta una asserzione sulla lunghezza e sull'alfabeto.
- **Unit tests:** `backend/tests/unit/test_slug.py::test_slug_22_caratteri_urlsafe` — mille generazioni, tutte lunghe 22, tutte composte solo da caratteri `A-Za-z0-9_-`, tutte distinte. Fallisce se qualcuno cambia la lunghezza o l'alfabeto.
- **e2e tests:** in `backend/tests/e2e/test_receivers.py`:
  `T-MGMT7` `test_crea_receiver_con_slug` — `201`, slug di 22 caratteri, `max_body_bytes` uguale al cap del tenant.
  `T-MGMT8` `test_max_body_oltre_cap_rifiutato` — `PATCH` con un valore superiore al cap del tenant restituisce `422`. Test di percorso negativo.
  `T-MGMT9` `test_rotate_slug_cambia_valore` — dopo la rotazione lo slug e diverso e non e il precedente.
  `T-MGMT10` `test_member_non_puo_ruotare_slug` — con token `member`, `POST .../rotate-slug` restituisce `403`. Fallisce se qualcuno usa `require_member` invece di `require_admin`.
- **Done:** i quattro test passano.

### 4.3 Regole di severity e validazione RE2

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/services/severity.py` (nuovo), `backend/app/schemas/severity_rule.py` (nuovo), `backend/app/api/v1/severity_rules.py` (nuovo), `backend/app/main.py` (modificato).
- **Pattern:** `app/services/severity.py` e **l'unico modulo del progetto autorizzato a importare `re2`** e l'unico punto in cui una regex fornita da un utente viene compilata o eseguita (invariante I-3, decisione D8).
- **Change:**
  - il modulo espone:
    ```python
    def compile_pattern(pattern: str, case_insensitive: bool) -> re2._Regexp
    def evaluate_rules(text: str, rules: Sequence[CompiledRule]) -> RuleMatch | None
    ```
    `compile_pattern` antepone `(?i)` quando `case_insensitive` e vero, perche RE2 non accetta il flag come argomento separato. Solleva `Problem(422, "/problems/validation-error", ...)` con un messaggio esplicito se la compilazione fallisce.
    `evaluate_rules` valuta le regole gia ordinate per `priority` crescente **sui primi 8192 caratteri** del testo e restituisce la prima corrispondenza con l'id della regola che ha vinto. Il troncamento a 8KB e nel servizio, non nei chiamanti: cosi vale ovunque.
  - `POST|GET /api/v1/receivers/{id}/severity-rules` e `PATCH|DELETE /api/v1/severity-rules/{id}` — `require_member` in scrittura, `require_viewer` in lettura. La validazione alla creazione chiama `compile_pattern`: un pattern non compilabile da RE2 non entra mai in tabella.
  - **Sintassi non supportata da RE2**: backreference (`\1`) e lookahead o lookbehind (`(?=`, `(?!`, `(?<=`, `(?<!`). Il messaggio di errore del `422` deve nominarli esplicitamente, altrimenti l'utente non capisce perche il suo pattern PCRE viene rifiutato.
  - Aggiungi un test di conformita che protegge l'invariante: scansiona i sorgenti di `backend/app` e fallisce se un modulo diverso da `services/severity.py` contiene `import re2` oppure usa `re.compile`, `re.search`, `re.match`, `re.findall` su un valore che non sia una costante letterale. In pratica: nessun `import re` in `app/services/`, `app/api/`, `app/outbound/`, `app/tasks/`.
- **Test strategy:** unitari puri sul servizio, e2e sull'endpoint, piu il test di conformita sui sorgenti.
- **Unit tests:** in `backend/tests/unit/test_severity_rules.py`:
  `test_prima_regola_vince` — due regole che corrispondono entrambe, quella con `priority` minore vince.
  `test_valutazione_limitata_a_8kb` — un testo con la corrispondenza al carattere 9000 non produce match; la stessa corrispondenza al carattere 100 lo produce. Test di percorso negativo che dimostra il troncamento.
  `test_case_insensitive` — pattern `errore` con `case_insensitive=True` trova `ERRORE`.
  `test_lookahead_rifiutato` — `compile_pattern("(?=x)y", False)` solleva `Problem` 422 e il messaggio contiene la parola `lookahead`.
  In `backend/tests/unit/test_conformita_regex.py`:
  `test_nessun_uso_del_modulo_re` — la scansione dei sorgenti descritta sopra. Fallisce se un domani qualcuno introduce `re` per valutare pattern utente.
- **e2e tests:** in `backend/tests/e2e/test_severity_rules.py`:
  `T-MGMT11` `test_crea_regola_valida` — `201` e la regola compare nell'elenco.
  `T-MGMT12` `test_regola_con_backreference_rifiutata` — pattern `(a)\1` restituisce `422` e la tabella resta vuota.
  `T-MGMT13` `test_pattern_troppo_lungo_rifiutato` — pattern di 201 caratteri restituisce `422`.
- **Done:** tutti i test passano; il test di conformita e verde.

### 4.4 Endpoint di prova della severity

- **Model:** Haiku
- **Files:** `backend/app/api/v1/severity_rules.py` (modificato).
- **Insertion point:** nello stesso router creato in 4.3, in coda alle rotte esistenti.
- **Pattern:** endpoint sottile che riusa `evaluate_rules` di 4.3 senza duplicare logica.
- **Change:** `POST /api/v1/receivers/{id}/test-severity` — `require_viewer`. Corpo `{"text": "..."}`. Carica le regole abilitate del receiver ordinate per `priority`, chiama `evaluate_rules`, e risponde:
  ```json
  {"severity": "error", "source": "rule", "matched_rule_id": "...", "matched_pattern": "..."}
  ```
  Se nessuna regola corrisponde: `{"severity": "<default del receiver>", "source": "receiver_default", "matched_rule_id": null, "matched_pattern": null}`.
  L'endpoint **non** salva nulla e **non** applica la severity esplicita: prova solo l'anello delle regole e il default.
- **Unit tests:** nessuno (nessuna logica propria).
- **e2e tests:** `T-MGMT14` in `backend/tests/e2e/test_severity_rules.py::test_prova_severity` — con una regola `FALL(ITO|IMENT)` verso `error`, il testo `Backup FALLITO` restituisce `severity=error`, `source=rule` e l'id della regola; il testo `tutto bene` restituisce il default del receiver con `source=receiver_default`.
- **Done:** il test passa.

### 4.5 Impostazioni del tenant

- **Model:** Sonnet
- **Files:** `backend/app/schemas/tenant.py` (nuovo), `backend/app/api/v1/tenant.py` (nuovo), `backend/app/main.py` (modificato).
- **Change:**
  - `GET /api/v1/tenant` — `require_viewer`. Restituisce nome, slug, `retention_days`, `max_body_bytes`, le due quote e lo stato.
  - `PATCH /api/v1/tenant` — **`require_owner`**, come da matrice ruoli. Campi modificabili: `name`, `retention_days`, `max_body_bytes`, `max_notifications_per_day`, `max_storage_bytes`.
  - **Guardia sull'abbassamento del cap:** se il nuovo `max_body_bytes` e inferiore al `max_body_bytes` di uno o piu receiver del tenant, la richiesta fallisce con `409`, `type=/problems/conflict`, e `extra["conflicting_receivers"]` popolato con `[{"id": ..., "name": ..., "max_body_bytes": ...}, ...]`. **Nessun adeguamento automatico dei receiver** (specifica sezione 9.3): la modifica silenziosa della configurazione altrui e proprio cio che si vuole evitare.
  - `max_body_bytes` non puo superare `settings.notifyhub_hard_max_body_bytes` -> `422`.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_tenant.py`:
  `T-MGMT15` `test_abbassare_cap_sotto_receiver_rifiutato` — con un receiver a 5MB, portare il cap del tenant a 1MB restituisce `409` e l'elenco contiene quel receiver; il cap del tenant e invariato e il receiver e invariato. Test di percorso negativo.
  `T-MGMT16` `test_abbassare_cap_senza_conflitti_riesce` — con tutti i receiver sotto la nuova soglia, il `PATCH` restituisce `200`.
  `T-MGMT17` `test_admin_non_puo_modificare_tenant` — con token `admin`, il `PATCH` restituisce `403`. Fallisce se si usa `require_admin` al posto di `require_owner`.
- **Done:** i tre test passano; `make gates` verde.

---

## Files touched (this phase)

- `backend/app/services/slug.py` — creato — generazione dello slug
- `backend/app/services/severity.py` — creato — unico punto di compilazione ed esecuzione delle regex utente
- `backend/app/schemas/group.py`, `receiver.py`, `severity_rule.py`, `tenant.py` — creati
- `backend/app/api/v1/groups.py`, `receivers.py`, `severity_rules.py`, `tenant.py` — creati
- `backend/app/main.py` — modificato — registrazione dei quattro router
- `backend/tests/unit/test_slug.py`, `test_severity_rules.py`, `test_conformita_regex.py` — creati
- `backend/tests/e2e/test_groups.py`, `test_receivers.py`, `test_severity_rules.py`, `test_tenant.py` — creati

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** `T-AUTH1` .. `T-AUTH22` e `T-RLS1` .. `T-RLS9` restano verdi.

## Phase done criterion

`make gates` verde con `T-MGMT1` .. `T-MGMT17`. Il test di conformita `test_nessun_uso_del_modulo_re` e verde e dimostra che nessun modulo oltre a `services/severity.py` puo valutare regex utente. Un owner puo creare gruppo, receiver e regole e provarle con `test-severity` ottenendo la severity corretta e il nome della regola vincente.
