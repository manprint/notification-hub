import type { QueryClient } from "@tanstack/react-query";

/** Tutte le cache che mostrano un receiver dentro un elenco. Creare, rinominare,
 *  disabilitare, rigenerare lo slug o eliminare un receiver cambia ognuna di
 *  queste, non solo la pagina del receiver: invalidando solo ["receiver", id]
 *  la pagina del gruppo, le notifiche e il selettore degli override restavano
 *  col nome, lo stato o il conteggio vecchi.
 *
 *  - ["receivers", groupId]: tabella dei receiver nella pagina del gruppo;
 *  - ["group-receivers", groupId]: tabelle per receiver nelle notifiche;
 *  - ["receivers-all"]: selettore degli override nella pagina dei canali;
 *  - ["group", groupId] e ["groups"]: il conteggio `receiver_count`. */
export async function invalidateReceiverLists(
  queryClient: QueryClient,
  groupId: string,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["receivers", groupId] }),
    queryClient.invalidateQueries({ queryKey: ["group-receivers", groupId] }),
    queryClient.invalidateQueries({ queryKey: ["receivers-all"] }),
    queryClient.invalidateQueries({ queryKey: ["group", groupId] }),
    queryClient.invalidateQueries({ queryKey: ["groups"] }),
  ]);
}
