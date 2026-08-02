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
    return <div className="access-denied">Accesso negato: il tuo ruolo non può vedere questa pagina.</div>;
  }

  return <>{children}</>;
}
