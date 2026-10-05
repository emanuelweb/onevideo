import { Link } from "react-router-dom";
import { Logo } from "../components/Logo";
import { isAuthenticated } from "../lib/api";

// URL estable de GitHub Releases: siempre sirve el APK de la versión más reciente.
const APK_URL = "https://github.com/emanuelweb/onevideo/releases/latest/download/onevideo.apk";

const STEPS = [
  "Abre esta página desde el navegador de tu celular Android y toca «Descargar la app».",
  "Abre el archivo descargado. Si Android lo pide, permite «instalar apps desconocidas» solo para tu navegador o el administrador de archivos.",
  "Abre OneVideo y concede cámara, micrófono y notificaciones.",
  "En el panel web crea un dispositivo y escribe en la app el código de 8 caracteres que aparece.",
  "Toca «Transmitir». Puedes bloquear la pantalla: la transmisión continúa.",
];

export default function DownloadPage() {
  const authenticated = isAuthenticated();

  return (
    <div className="public-page">
      <header className="public-header">
        <Link to="/" className="public-logo">
          <Logo />
        </Link>
        <nav className="public-header-links">
          {authenticated ? (
            <Link to="/app" className="btn btn-primary btn-sm">
              Ir al panel
            </Link>
          ) : (
            <>
              <Link to="/login" className="nav-link">
                Iniciar sesión
              </Link>
              <Link to="/registro" className="btn btn-primary btn-sm">
                Crear cuenta
              </Link>
            </>
          )}
        </nav>
      </header>

      <main className="public-main">
        <section className="hero">
          <h1 className="hero-title">Descarga OneVideo para Android</h1>
          <p className="hero-sub">
            Convierte tu celular en la cámara de tu stream. Transmite a la nube con la pantalla
            bloqueada y contrólalo todo desde el panel web.
          </p>
          <div className="btn-row download-cta">
            <a href={APK_URL} className="btn btn-primary" download>
              Descargar la app (APK)
            </a>
          </div>
          <p className="muted download-meta">Android 8.0 o superior · aprox. 50 MB</p>
        </section>

        <section className="card download-steps">
          <h2>Cómo instalarla</h2>
          <ol>
            {STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="muted">
            ¿Ya la tenías instalada? Descarga e instala encima: conservas el emparejamiento.
          </p>
        </section>
      </main>
    </div>
  );
}
