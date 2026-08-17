import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "./Logo";

function navClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link active" : "nav-link";
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout(): void {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/app" end className="sidebar-logo">
          <Logo />
        </NavLink>
        <nav className="sidebar-nav" aria-label="Navegación principal">
          <NavLink to="/app" end className={navClass}>
            Dispositivos
          </NavLink>
          <NavLink to="/app/guia-obs" className={navClass}>
            Guía OBS
          </NavLink>
          <NavLink to="/app/cuenta" className={navClass}>
            Cuenta
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          {user && (
            <div className="user-chip">
              <span className="user-name">{user.name}</span>
              <span className="user-email">{user.email}</span>
            </div>
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={handleLogout}>
            Cerrar sesión
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
