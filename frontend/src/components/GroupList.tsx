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
              <span className="group-card-name">{g.name}</span>
              {g.description && <span className="group-card-desc">{g.description}</span>}
            </button>
          ))}
        </div>
      )}
    </>
  );
}