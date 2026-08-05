import { useState } from "react";
import EmptyState from "./EmptyState";
import type { GroupOut } from "../api/types";

interface GroupListProps {
  groups: GroupOut[];
  onSelect: (groupId: string) => void;
  loading?: boolean;
}

export default function GroupList({ groups, onSelect, loading }: GroupListProps) {
  const [query, setQuery] = useState("");

  if (loading) {
    return <EmptyState message="Caricamento…" />;
  }

  if (groups.length === 0) {
    return <EmptyState message="Nessun gruppo configurato." />;
  }

  const q = query.trim().toLowerCase();
  const filtered = q
    ? groups.filter(
        (g) =>
          g.name.toLowerCase().includes(q) ||
          (g.description ?? "").toLowerCase().includes(q),
      )
    : groups;

  return (
    <>
      <div className="group-search">
        <input
          type="search"
          aria-label="Cerca gruppi"
          placeholder="Cerca gruppi…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      {filtered.length === 0 ? (
        <EmptyState message="Nessun gruppo corrisponde alla ricerca." />
      ) : (
        <div className="group-grid">
          {filtered.map((g) => (
            <button key={g.id} className="group-card" onClick={() => onSelect(g.id)}>
              <div className="group-card-head">
                <span className="group-card-eyebrow">Gruppo</span>
                <span className="group-card-meta">{g.receiver_count} receiver</span>
              </div>
              <span className="group-card-name">{g.name}</span>
              {g.description && <span className="group-card-desc">{g.description}</span>}
              {typeof g.notification_count === "number" && (
                <div className="group-card-stats">
                  <span className="group-card-stat group-card-stat-unread">
                    {g.unread_count} non lette
                  </span>
                  <span className="group-card-stat">
                    {g.notification_count - (g.unread_count ?? 0)} lette
                  </span>
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </>
  );
}