import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiGet, apiPut } from "../api/client";
import type { ApiError, ReceiverPresetOut, SeverityPresetOut } from "../api/types";
import EmptyState from "./EmptyState";
import ErrorBanner from "./ErrorBanner";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { MEMBER_ROLES, hasRole } from "../lib/roles";

/** Errore da mostrare quando la lettura fresca smentisce la schermata: l'elenco
 *  non si invia. Ha la forma di un ApiError, così il banner lo tratta come gli
 *  altri errori. */
function staleListError(detail: string): ApiError {
  return {
    status: 0,
    type: "/problems/generic",
    title: "Elenco non modificato",
    detail,
    extra: {},
  };
}

/** Preset applicati a un receiver: quali, e in che ordine vengono valutati.
 *
 *  Ogni modifica invia l'elenco completo (PUT): attaccare, staccare e riordinare
 *  sono la stessa operazione, quindi non esistono stati intermedi in cui il
 *  receiver ha posizioni doppie o buchi. */
export default function ReceiverPresetsPanel({ receiverId }: { receiverId: string }) {
  const { role } = useSession();
  const canManage = hasRole(role, MEMBER_ROLES);
  const queryClient = useQueryClient();
  const { busy, error, run } = useAction();

  const appliedKey = ["receiver-presets", receiverId] as const;
  const fetchApplied = () =>
    apiGet<ReceiverPresetOut[]>(`/api/v1/receivers/${receiverId}/presets`);

  const {
    data: applied,
    error: appliedError,
    isLoading: appliedLoading,
  } = useQuery<ReceiverPresetOut[], ApiError>({
    queryKey: appliedKey,
    queryFn: fetchApplied,
  });

  const { data: all, error: allError } = useQuery<SeverityPresetOut[], ApiError>({
    queryKey: ["presets"],
    queryFn: () => apiGet<SeverityPresetOut[]>("/api/v1/severity-presets"),
  });

  // Ogni azione manda l'elenco completo: senza l'elenco applicato letto davvero
  // (in caricamento, o con l'ultima lettura fallita) "Applica X" mandava [X] e
  // staccava in silenzio tutti gli altri preset. Finche' non e' affidabile, le
  // azioni restano ferme.
  const ready = applied !== undefined && !appliedError;
  const appliedList = applied ?? [];
  const appliedIds = appliedList.map((p) => p.preset_id);
  const available = (all ?? []).filter((p) => !appliedIds.includes(p.id));
  const locked = busy !== null || !ready;

  /** Ogni azione costruisce l'elenco completo da quello letto adesso dal server,
   *  non dalla cache: una modifica fatta altrove nel frattempo non viene
   *  riportata indietro. Se la lettura fallisce, o la modifica non ha più senso
   *  su quell'elenco, non si invia niente. */
  async function change(build: (currentIds: string[]) => string[], messaggio: string) {
    if (!ready) return;
    await run(
      async () => {
        try {
          const fresh = await queryClient.fetchQuery({
            queryKey: appliedKey,
            queryFn: fetchApplied,
            staleTime: 0,
          });
          const presetIds = build(fresh.map((p) => p.preset_id));
          await apiPut(`/api/v1/receivers/${receiverId}/presets`, { preset_ids: presetIds });
        } finally {
          // Anche dopo un errore: la lista in cache è quella che il 409 o il 404
          // hanno appena smentito, e va riletta prima della prossima azione.
          await queryClient.invalidateQueries({ queryKey: ["receiver-presets", receiverId] });
          await queryClient.invalidateQueries({ queryKey: ["severity-chain", receiverId] });
          await queryClient.invalidateQueries({ queryKey: ["severity-replay", receiverId] });
        }
      },
      { success: messaggio },
    );
  }

  function move(presetId: string, delta: number) {
    void change((ids) => {
      const next = [...ids];
      const index = next.indexOf(presetId);
      const target = index + delta;
      if (index === -1 || target < 0 || target >= next.length) {
        throw staleListError(
          "L'elenco dei preset è cambiato nel frattempo: ricontrolla l'ordine e riprova.",
        );
      }
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    }, "Ordine dei preset aggiornato.");
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Preset di regole applicati</h3>
      </div>
      <p className="card-hint">
        Un preset porta con sé le sue regole, valutate <strong>dopo</strong> quelle scritte su
        questo receiver e nell'ordine in cui compaiono qui. I preset si creano e si modificano
        nella sezione <Link to="/presets">Preset di regole</Link>.
      </p>
      <p className="card-hint">
        Metti i preset specifici (tar, rclone, PostgreSQL…) <strong>prima</strong> di «Bash
        generico»: quest'ultimo contiene una regola di riserva molto larga che vincerebbe su
        tutto quello che viene dopo.
      </p>
      {appliedError && <ErrorBanner error={appliedError} />}
      {allError && <ErrorBanner error={allError} />}
      {error && <ErrorBanner error={error} />}

      {appliedLoading ? (
        <p className="card-hint">Caricamento dei preset applicati…</p>
      ) : applied === undefined ? null : appliedList.length === 0 ? (
        // Con l'ultima lettura fallita "nessun preset" sarebbe un falso: il banner dice il resto.
        !appliedError && (
          <EmptyState message="Nessun preset applicato: valgono solo le regole qui sotto." />
        )
      ) : (
        <ol className="chain-list" aria-label="Preset applicati">
          {appliedList.map((preset, index) => (
            <li key={preset.preset_id}>
              <strong>{preset.name}</strong> — {preset.rules_count}{" "}
              {preset.rules_count === 1 ? "regola" : "regole"}
              {preset.description && <div className="cell-diagnostics">{preset.description}</div>}
              {canManage && (
                <div className="row-actions">
                  <button
                    aria-label={`Sposta su ${preset.name}`}
                    disabled={index === 0 || locked}
                    onClick={() => move(preset.preset_id, -1)}
                  >
                    ↑
                  </button>
                  <button
                    aria-label={`Sposta giù ${preset.name}`}
                    disabled={index === appliedList.length - 1 || locked}
                    onClick={() => move(preset.preset_id, 1)}
                  >
                    ↓
                  </button>
                  <button
                    disabled={locked}
                    onClick={() =>
                      void change(
                        (ids) => ids.filter((id) => id !== preset.preset_id),
                        `Preset «${preset.name}» tolto da questo receiver.`,
                      )
                    }
                  >
                    Togli
                  </button>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}

      {canManage && ready && available.length > 0 && (
        <>
          <h4>Preset disponibili</h4>
          <ul className="check-list" aria-label="Preset disponibili">
            {available.map((preset) => (
              <li key={preset.id}>
                <div className="row-actions">
                  <button
                    aria-label={`Applica ${preset.name}`}
                    disabled={locked}
                    onClick={() =>
                      void change(
                        (ids) => (ids.includes(preset.id) ? ids : [...ids, preset.id]),
                        `Preset «${preset.name}» applicato.`,
                      )
                    }
                  >
                    Applica
                  </button>
                  <span>
                    <strong>{preset.name}</strong> — {preset.rules_count}{" "}
                    {preset.rules_count === 1 ? "regola" : "regole"}
                  </span>
                </div>
                {preset.description && <div className="cell-diagnostics">{preset.description}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
