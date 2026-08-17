import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { isAuthenticated } from "../lib/api";
import { Loader } from "../components/Loader";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { loading } = useAuth();
  const location = useLocation();

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (loading) {
    return (
      <div className="page-loader">
        <Loader text="Cargando tu cuenta…" />
      </div>
    );
  }
  return <>{children}</>;
}
