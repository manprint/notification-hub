import type { UserRole } from "../api/types";

// Rispecchia i Depends(require_admin) / Depends(require_member) del backend
// (backend/app/api/deps.py): stessa soglia, per nascondere lato UI le azioni
// che il backend rifiuterebbe comunque.
export const ADMIN_ROLES: UserRole[] = ["owner", "admin"];
export const MEMBER_ROLES: UserRole[] = ["owner", "admin", "member"];

export function hasRole(role: UserRole | null, allowed: UserRole[]): boolean {
  return role !== null && allowed.includes(role);
}
