import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "../components/Logo";
import { getErrorMessage } from "../lib/api";

export default function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user !== null) navigate("/app", { replace: true });
  }, [user, navigate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(name.trim(), email, password);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-brand">
        <Logo />
        <p className="tagline">La app de vídeo del futuro</p>
      </div>
      <div className="auth-card card">
        <h1 className="auth-title">Crear cuenta</h1>
        <p className="auth-subtitle">
          Empieza gratis: convierte tu celular en una cámara profesional para OBS.
        </p>
        <form onSubmit={(event) => void handleSubmit(event)}>
          <div className="field">
            <label className="label" htmlFor="name">
              Nombre
            </label>
            <input
              id="name"
              className="input"
              type="text"
              autoComplete="name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="email">
              Correo electrónico
            </label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="password">
              Contraseña
            </label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <p className="field-hint">Mínimo 8 caracteres.</p>
          </div>
          {error !== null && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? "Creando cuenta…" : "Crear cuenta gratis"}
          </button>
        </form>
      </div>
      <div className="auth-links">
        <span>
          ¿Ya tienes cuenta? <Link to="/login">Inicia sesión</Link>
        </span>
        <Link to="/precios">Ver planes y precios</Link>
      </div>
    </div>
  );
}
