import { Link } from "react-router-dom";
import type { AuditEventOut } from "../api/types";

/** Dove sta la risorsa di una riga di audit: receiver in evidenza, gruppo
 *  sotto.
 *
 *  Senza, la tabella diceva "receiver / Backup notturno" e "severity_rule /
 *  disco pieno" senza dire dove: con tre gruppi che hanno un receiver con lo
 *  stesso nome, la riga non identifica niente. Il backend risolve la posizione
 *  in lettura, quindi quando la risorsa e' stata cancellata non c'e' piu': si
 *  mostra un trattino invece di indovinare. */
export default function ResourceLocation({ event }: { event: AuditEventOut }) {
  if (event.receiver_name === null && event.group_name === null) {
    return <span className="cell-diagnostics">—</span>;
  }

  if (event.receiver_name === null) {
    return event.group_id ? (
      <Link to={`/groups/${event.group_id}`}>{event.group_name}</Link>
    ) : (
      <span>{event.group_name}</span>
    );
  }

  return (
    <div className="cell-preview">
      {event.receiver_id ? (
        <Link to={`/receivers/${event.receiver_id}`}>{event.receiver_name}</Link>
      ) : (
        <span>{event.receiver_name}</span>
      )}
      {event.group_name && <div className="cell-diagnostics">{event.group_name}</div>}
    </div>
  );
}
