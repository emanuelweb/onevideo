import { Link } from "react-router-dom";
import { Logo } from "../components/Logo";

export default function NotFoundPage() {
  return (
    <div className="auth-page">
      <div className="auth-brand">
        <Logo />
      </div>
      <div className="auth-card card">
        <h1 className="auth-title">Página no encontrada</h1>
        <p className="muted">La dirección que buscas no existe o fue movida.</p>
        <Link to="/app" className="btn btn-primary btn-block">
          Ir al panel
        </Link>
      </div>
    </div>
  );
}
