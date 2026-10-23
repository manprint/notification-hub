import type { ReactNode } from "react";
import { useSession } from "../hooks/useSession";
import type { UserRole } from "../api/types";

interface RequireRoleProps {
  allowed: UserRole[];
  children: ReactNode;
}

export default function RequireRole({ allowed, children }: RequireRoleProps) {
  const { role } = useSession();

  if (role === null || !allowed.includes(role)) {
    // Il titolo c'è come in ogni altra schermata: senza, la pagina non ha un h1
    // e chi usa lo schermo lettore non sa dove si trova.
    return (
      <div className="access-denied">
        <div className="page-header">
          <h1>Accesso negato</h1>
        </div>
        <p className="page-subtitle">Il tuo ruolo non può vedere questa pagina.</p>
      </div>
    );
  }

  return <>{children}</>;
}
