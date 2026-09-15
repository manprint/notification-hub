import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import NotificationsPage from "../NotificationsPage";
import { server } from "../../api/mocks/server";
import { fixtureNotificationDetailObject, fixtureNotificationsPage1 } from "../../api/mocks/handlers";
import { renderWithProviders } from "./testUtils";

describe("NotificationsPage", () => {
  it("T-GRP1 landing mostra la griglia dei gruppi e non chiama le notifiche", async () => {
    let notificationsCalled = false;
    server.use(
      http.get("/api/v1/notifications", () => {
        notificationsCalled = true;
        return HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 });
      }),
    );

    renderWithProviders(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /server produzione/i })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /backup/i })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(notificationsCalled).toBe(false);
    expect(screen.getByText(/Seleziona un gruppo/)).toBeInTheDocument();
  });  it("T-GRP2 clic su un gruppo naviga alla tabella scoped a quel gruppo", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(fixtureNotificationsPage1);
      }),
    );

    renderWithProviders(<NotificationsPage />);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /server produzione/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /server produzione/i }));

    await waitFor(() => {
      expect(urls.some((u) => new URL(u).searchParams.get("group_id") === "g1")).toBe(true);
    });
    const tabella = within(await screen.findByRole("table"));
    expect(tabella.getByText(/Backup FALLITO/)).toBeInTheDocument();
  });

  it("T-GRP3 'Torna ai gruppi' torna alla griglia senza combobox gruppo", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: /torna ai gruppi/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /server produzione/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("Tutti i gruppi")).not.toBeInTheDocument();
  });

  it("T-UI7 test_carica_altri_usa_il_cursore: il secondo caricamento usa next_cursor e accoda senza duplicati", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);

    await waitFor(() => {
      expect(screen.getByText(/Backup FALLITO/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Terza notifica/)).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Carica altri" }));

    await waitFor(() => {
      expect(screen.getByText(/Terza notifica/)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Backup FALLITO/)).toHaveLength(1);
  });

  it("T-UI8 test_nota_sulla_ricerca_presente: la nota dichiara la ricerca sull'intero contenuto", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);

    await waitFor(() => {
      expect(screen.getByText(/Backup FALLITO/)).toBeInTheDocument();
    });

    expect(screen.getByText(/La ricerca esamina l'intero contenuto del messaggio/)).toBeInTheDocument();
    expect(screen.getByText(/object storage esamina i primi 4096 caratteri/)).toBeInTheDocument();
  });

  it("T-GRP5 test_evidenza_gruppo_nel_titolo: dentro un gruppo il titolo dice quale", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);

    await waitFor(() => {
      expect(screen.getByText(/Backup FALLITO/)).toBeInTheDocument();
    });

    const titolo = screen.getByRole("heading", { level: 1 });
    expect(titolo).toHaveTextContent("Notifiche");
    expect(titolo).toHaveTextContent("Server Produzione");
    expect(screen.getByText("Ambiente di produzione")).toBeInTheDocument();
  });

  it("T-GRP6 test_filtro_receiver: il select dei receiver del gruppo filtra la lista", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json(fixtureNotificationsPage1);
      }),
    );

    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const user = userEvent.setup();

    const select = await screen.findByLabelText("Receiver del gruppo");
    await waitFor(() => {
      expect(within(select).getByRole("option", { name: /backup notturno/i })).toBeInTheDocument();
    });

    await user.selectOptions(select, "r1");

    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("receiver_id")).toBe("r1");
      expect(capturedUrl?.searchParams.get("group_id")).toBe("g1");
    });
  });

  it("T-GRP7 test_bulk_read_rispetta_il_receiver: 'segna tutte come lette' passa il receiver filtrato", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/notifications/bulk-read", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ marked_read: 3 });
      }),
    );

    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1&receiver_id=r1"]);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/Backup FALLITO/)).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Segna tutte come lette" }));

    await waitFor(() => {
      expect(body).not.toBeNull();
    });
    expect(body).toMatchObject({ group_id: "g1", receiver_id: "r1" });
  });

  it("T-GRP8 test_scelta_gruppo_azzera_receiver: un receiver_id orfano non sopravvive alla scelta del gruppo", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(fixtureNotificationsPage1);
      }),
    );

    // receiver_id senza group_id: la pagina mostra la griglia dei gruppi, e il
    // receiver appartiene a un gruppo che non e' ancora stato scelto.
    renderWithProviders(<NotificationsPage />, ["/notifications?receiver_id=r1"]);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /backup/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /backup/i }));

    await waitFor(() => {
      expect(urls.length).toBeGreaterThan(0);
    });
    const ultima = new URL(urls[urls.length - 1]);
    expect(ultima.searchParams.get("group_id")).toBe("g2");
    expect(ultima.searchParams.get("receiver_id")).toBeNull();
  });

  it("T-GRP4 test_filtri_group_scoped: filtri severity restano scoped al gruppo", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 });
      }),
    );

    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);

    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("group_id")).toBe("g1");
    });

    const user = userEvent.setup();
    await user.selectOptions(screen.getByDisplayValue("Qualsiasi severity"), "error");

    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("group_id")).toBe("g1");
      expect(capturedUrl?.searchParams.get("severity_min")).toBe("error");
    });
  });

  it("mostra l'origine di ogni notifica, sorveglianza compresa", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "nm1",
              receiver_id: "r1",
              content_preview: "[notifyhub] nessun invio da «backup notturno»",
              content_size: 200,
              content_normalized: false,
              storage_backend: "inline",
              severity: "critical",
              severity_source: "missing",
              status: "unread",
              verified: false,
              received_at: "2026-08-05T03:31:00Z",
            },
            {
              id: "nr1",
              receiver_id: "r1",
              content_preview: "[notifyhub] «backup notturno» ha ripreso a inviare",
              content_size: 180,
              content_normalized: false,
              storage_backend: "inline",
              severity: "info",
              severity_source: "recovered",
              status: "unread",
              verified: false,
              received_at: "2026-08-05T09:00:00Z",
            },
          ],
          next_cursor: null,
          unread_count: 2,
        }),
      ),
    );

    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);

    await waitFor(() => {
      expect(screen.getByText(/nessun invio da/)).toBeInTheDocument();
    });
    // Le due notifiche scritte dal server si riconoscono dall'origine, senza
    // dover leggere il contenuto. Si guarda dentro la tabella: le stesse
    // etichette compaiono anche fra le opzioni del filtro.
    const tabella = within(screen.getByRole("table"));
    expect(tabella.getByText("notifica mancante")).toBeInTheDocument();
    expect(tabella.getByText("ripresa degli invii")).toBeInTheDocument();
  });

  it("distingue un ping di avvio da un esito", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "ns1",
              receiver_id: "r1",
              content_preview: "[notifyhub] job=backup avvio host=srv01",
              content_size: 60,
              content_normalized: false,
              storage_backend: "inline",
              severity: "debug",
              severity_source: "explicit",
              phase: "start",
              duration_ms: null,
              exit_code: null,
              status: "unread",
              verified: false,
              received_at: "2026-08-05T03:00:01Z",
            },
            {
              id: "ne1",
              receiver_id: "r1",
              content_preview: "[notifyhub] job=backup esito=ok exit=0",
              content_size: 80,
              content_normalized: false,
              storage_backend: "inline",
              severity: "info",
              severity_source: "receiver_default",
              phase: "end",
              duration_ms: 750_123,
              exit_code: 0,
              status: "unread",
              verified: false,
              received_at: "2026-08-05T03:12:00Z",
            },
          ],
          next_cursor: null,
          unread_count: 2,
        }),
      ),
    );

    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);

    await waitFor(() => {
      expect(screen.getByText(/job=backup avvio/)).toBeInTheDocument();
    });
    const tabella = within(screen.getByRole("table"));
    // Solo l'avvio porta la marca: la conclusione e' il caso normale e non ha
    // bisogno di essere annunciata.
    expect(tabella.getAllByText("avvio")).toHaveLength(1);
    expect(tabella.queryByText("conclusione")).not.toBeInTheDocument();
  });

  it("il filtro sull'origine arriva nella richiesta e nel bulk-read", async () => {
    let capturedUrl: URL | null = null;
    let bulkBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 });
      }),
      http.post("/api/v1/notifications/bulk-read", async ({ request }) => {
        bulkBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ marked_read: 0 });
      }),
    );

    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Origine della notifica"), "missing");

    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("source")).toBe("missing");
    });

    // "Segna tutte come lette" non deve agire su cio' che il filtro esclude.
    await user.click(screen.getByRole("button", { name: "Segna tutte come lette" }));
    await waitFor(() => expect(bulkBody).not.toBeNull());
    expect(bulkBody).toMatchObject({ source: "missing" });
  });

  it("T-LIST1 le etichette commutano in base a status: unread mostra letta, read mostra non letta", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const tabella = within(await screen.findByRole("table"));
    const rigaN1 = tabella.getByText(/Backup FALLITO/).closest("tr") as HTMLElement;
    const rigaN2 = tabella.getByText(/Tutto ok/).closest("tr") as HTMLElement;
    expect(within(rigaN1).getByRole("button", { name: "Segna come letta" })).toBeInTheDocument();
    expect(within(rigaN2).getByRole("button", { name: "Segna come non letta" })).toBeInTheDocument();
  });

  it("T-LIST2 segna come non letta manda status unread", async () => {
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/notifications/:id", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...fixtureNotificationDetailObject,
          ...patchBody,
        });
      }),
    );
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const tabella = within(await screen.findByRole("table"));
    const rigaN2 = tabella.getByText(/Tutto ok/).closest("tr") as HTMLElement;
    await userEvent.setup().click(within(rigaN2).getByRole("button", { name: "Segna come non letta" }));
    await waitFor(() => expect(patchBody).toEqual({ status: "unread" }));
  });

  it("T-LIST3 toggle verifica manda verified true e mostra la pill", async () => {
    let patchBody: Record<string, unknown> | null = null;
    let n2Verified = false;
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "n1",
              receiver_id: "r1",
              content_preview: "Backup FALLITO: disco pieno su /var",
              content_size: 40,
              content_normalized: false,
              storage_backend: "inline",
              severity: "error",
              severity_source: "rule",
              phase: "end",
              status: "unread",
              verified: true,
              received_at: "2026-08-01T03:00:00Z",
            },
            {
              id: "n2",
              receiver_id: "r1",
              content_preview: "Tutto ok",
              content_size: 8,
              content_normalized: true,
              storage_backend: "inline",
              severity: "info",
              severity_source: "receiver_default",
              phase: null,
              status: "read",
              verified: n2Verified,
              received_at: "2026-08-01T02:00:00Z",
            },
          ],
          next_cursor: null,
          unread_count: 0,
        }),
      ),
      http.patch("/api/v1/notifications/:id", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        if (patchBody.verified === true) n2Verified = true;
        return HttpResponse.json({ ...fixtureNotificationDetailObject, ...patchBody });
      }),
    );
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const tabella = within(await screen.findByRole("table"));
    const rigaN2 = tabella.getByText(/Tutto ok/).closest("tr") as HTMLElement;
    await userEvent.setup().click(within(rigaN2).getByRole("button", { name: "Segna come verificata" }));
    await waitFor(() => expect(patchBody).toEqual({ verified: true }));
    await waitFor(() => {
      expect(within(rigaN2).getByText("Verificata")).toBeInTheDocument();
    });
  });

  it("T-LIST4 le pill Verificata/Non verificata sono presenti dentro .status-cell", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const tabella = within(await screen.findByRole("table"));
    expect(tabella.getByText("Verificata")).toBeInTheDocument();
    expect(tabella.getByText("Non verificata")).toBeInTheDocument();
    expect(screen.getByText("Verificata").closest(".status-cell")).not.toBeNull();
  });

  it("status_cell_wraps_pills_aligned: le pill di stato stanno nello stesso contenitore .status-cell", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const tabella = within(await screen.findByRole("table"));

    const rigaN1 = tabella.getByText(/Backup FALLITO/).closest("tr") as HTMLElement;
    const cellN1 = within(rigaN1).getByText("Verificata").closest(".status-cell") as HTMLElement;
    expect(cellN1).not.toBeNull();
    expect(cellN1).toHaveClass("status-cell");
    expect(within(rigaN1).getByText("Non letta").closest(".status-cell")).toBe(cellN1);

    const rigaN2 = tabella.getByText(/Tutto ok/).closest("tr") as HTMLElement;
    const cellN2 = within(rigaN2).getByText("Non verificata").closest(".status-cell") as HTMLElement;
    expect(cellN2).not.toBeNull();
    expect(within(rigaN2).getByText("Letta").closest(".status-cell")).toBe(cellN2);
  });

  it("action_buttons_stay_on_same_row: i due pulsanti stanno nello stesso 'row-actions'", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    const tabella = within(await screen.findByRole("table"));
    const rigaN2 = tabella.getByText(/Tutto ok/).closest("tr") as HTMLElement;
    const btnNonLetta = within(rigaN2).getByRole("button", { name: "Segna come non letta" });
    const btnVerificata = within(rigaN2).getByRole("button", { name: "Segna come verificata" });

    expect(btnNonLetta.parentElement).toBe(btnVerificata.parentElement);
    expect(btnNonLetta.parentElement as HTMLElement).toHaveClass("row-actions");
  });

  it("table_wrap_scrolls_horizontally: la tabella e' dentro un contenitore scrollabile", async () => {
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    await screen.findByRole("table");
    expect(document.querySelector(".table-wrap")).not.toBeNull();
  });

  it("T-EMPTY2 un gruppo senza notifiche mostra il messaggio vuoto", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 }),
      ),
    );
    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1"]);
    await waitFor(() => {
      expect(screen.getByText("Nessuna notifica trovata.")).toBeInTheDocument();
    });
  });

  it("T-ERR1 un errore sui gruppi mostra il banner e non crasha", async () => {
    server.use(
      http.get("/api/v1/groups", () =>
        HttpResponse.json(
          {
            type: "/problems/internal-error",
            title: "Internal Server Error",
            status: 500,
            detail: "Errore interno nel caricamento dei gruppi",
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Errore interno/)).toBeInTheDocument();
    });
  });

  it("T-ACCEPT1 flusso completo: griglia -> gruppo -> visual fixes -> torna ai gruppi", async () => {
    server.use(
      http.get("/api/v1/notifications", () => HttpResponse.json(fixtureNotificationsPage1)),
    );

    renderWithProviders(<NotificationsPage />);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /server produzione/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /server produzione/i }));

    const tabella = within(await screen.findByRole("table"));

    expect(screen.getByText("Errore").closest(".severity-badge")).not.toBeNull();

    const rigaN1 = tabella.getByText(/Backup FALLITO/).closest("tr") as HTMLElement;
    expect(within(rigaN1).getByText("Verificata").closest(".status-cell")).not.toBeNull();

    const btnLetta = within(rigaN1).getByRole("button", { name: "Segna come letta" });
    const btnVerificata = within(rigaN1).getByRole("button", { name: "Segna come non verificata" });
    expect(btnLetta.parentElement).toBe(btnVerificata.parentElement);
    expect(btnLetta.parentElement as HTMLElement).toHaveClass("row-actions");

    await user.click(screen.getByRole("link", { name: /torna ai gruppi/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /server produzione/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  // .planning/ROADMAP.md fase 4: read e verified sono due dimensioni di stato
  // filtrabili in modo indipendente, dall'URL, senza perdere gli altri filtri.
  // Il parametro `status` veniva letto dall'URL ma nessun controllo lo scriveva,
  // e `verified` non esisteva ne qui ne nell'API.
  it("i filtri di stato e verifica finiscono nell'URL e nella richiesta", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 });
      }),
    );

    renderWithProviders(<NotificationsPage />, ["/notifications?group_id=g1&severity_min=error"]);
    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("group_id")).toBe("g1");
    });

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Stato di verifica"), "true");
    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("verified")).toBe("true");
    });

    await user.selectOptions(screen.getByLabelText("Stato di lettura"), "unread");
    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("status")).toBe("unread");
      // Le due dimensioni si combinano fra loro e con i filtri preesistenti.
      expect(capturedUrl?.searchParams.get("verified")).toBe("true");
      expect(capturedUrl?.searchParams.get("severity_min")).toBe("error");
    });
  });

  it("'segna tutte come lette' non tocca cio' che il filtro verifica esclude", async () => {
    let bulkBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/notifications/bulk-read", async ({ request }) => {
        bulkBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ marked_read: 1 });
      }),
    );

    renderWithProviders(<NotificationsPage />, [
      "/notifications?group_id=g1&verified=false",
    ]);
    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Segna tutte come lette" }));

    await waitFor(() => {
      expect(bulkBody).not.toBeNull();
    });
    expect(bulkBody).toMatchObject({ group_id: "g1", verified: false });
  });
});
