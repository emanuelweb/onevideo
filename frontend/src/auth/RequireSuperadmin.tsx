import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { Loader } from "../components/Loader";
import { useAuth } from "./AuthContext";

/**
 * Envoltura para las rutas del panel de administración: solo pasan los super-admins.
 * El resto vuelve al panel principal (la autenticación ya la garantiza RequireAuth).
 */
export function RequireSuperadmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="page-loader">
        <Loader text="Verificando permisos…" />
      </div>
    );
  }
  if (user === null || !user.is_superadmin) {
    return <Navigate to="/app" replace />;
  }
  return <>{children}</>;
}
