import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice } from "../components/ErrorNotice";
import { Loader } from "../components/Loader";
import { Logo } from "../components/Logo";
import { api, getErrorMessage, isAuthenticated } from "../lib/api";
import { formatPrice } from "../lib/format";
import type { PlanPublic } from "../lib/types";

function planSpecs(plan: PlanPublic): string[] {
  return [
    plan.max_devices === 1 ? "1 dispositivo" : `${plan.max_devices} dispositivos`,
    `Hasta ${plan.max_resolution} · ${plan.max_fps} fps`,
    plan.monthly_hours === null
      ? "Horas ilimitadas (uso justo)"
      : `${plan.monthly_hours} horas de transmisión al mes`,
  ];
}

export default function PricingPage() {
  const [plans, setPlans] = useState<PlanPublic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const authenticated = isAuthenticated();

  const load = useCallback(() => {
    setError(null);
    setPlans(null);
    api
      .plans()
      .then(setPlans)
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  useEffect(load, [load]);

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
          <h1 className="hero-title">Planes simples para cada streamer</h1>
          <p className="hero-sub">
            Tu celular Android como cámara cloud para OBS, Kick y Twitch. Control remoto, calidad
            configurable y URLs listas para tu escena. Empieza gratis y mejora cuando lo necesites.
          </p>
        </section>

        {error !== null && <ErrorNotice message={error} onRetry={load} />}
        {error === null && plans === null && <Loader text="Cargando planes…" />}

        {plans !== null && (
          <section className="plans-grid">
            {plans.map((plan) => {
              const popular = plan.code === "pro";
              return (
                <article
                  key={plan.code}
                  className={popular ? "plan-card card plan-popular" : "plan-card card"}
                >
                  {popular && <span className="plan-ribbon">Más popular</span>}
                  <h2 className="plan-name">{plan.name}</h2>
                  <p className="plan-price">
                    {formatPrice(plan.price_usd_month)}
                    {Number(plan.price_usd_month) > 0 && (
                      <span className="plan-price-period"> USD/mes</span>
                    )}
                  </p>
                  <ul className="plan-specs">
                    {planSpecs(plan).map((spec) => (
                      <li key={spec}>{spec}</li>
                    ))}
                  </ul>
                  {plan.features.length > 0 && (
                    <ul className="plan-features">
                      {plan.features.map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                  )}
                  <Link
                    to={authenticated ? "/app/cuenta" : "/registro"}
                    className={
                      popular ? "btn btn-primary btn-block plan-cta" : "btn btn-ghost btn-block plan-cta"
                    }
                  >
                    {Number(plan.price_usd_month) === 0 ? "Comenzar gratis" : `Elegir ${plan.name}`}
                  </Link>
                </article>
              );
            })}
          </section>
        )}

        <p className="pricing-note muted">
          Precios en USD. La calidad máxima (resolución y fps) se aplica automáticamente en tu
          dispositivo según el plan. Puedes cambiar de plan cuando quieras.
        </p>
      </main>
    </div>
  );
}
