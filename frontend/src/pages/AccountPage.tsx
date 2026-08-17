import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ErrorNotice } from "../components/ErrorNotice";
import { Loader } from "../components/Loader";
import { ProgressBar } from "../components/ProgressBar";
import { api, getErrorMessage } from "../lib/api";
import { formatDate, formatHours, formatPrice } from "../lib/format";
import type { Usage } from "../lib/types";

export default function AccountPage() {
  const { user } = useAuth();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .usage()
      .then(setUsage)
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  useEffect(load, [load]);

  const plan = user?.plan ?? null;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Tu cuenta</h1>
          {user !== null && (
            <p className="page-subtitle">
              {user.name} · {user.email} · miembro desde {formatDate(user.created_at)}
            </p>
          )}
        </div>
      </div>

      <div className="account-grid">
        <section className="card">
          <h2 className="section-title">Plan actual</h2>
          {plan !== null ? (
            <>
              <p className="plan-price">
                {plan.name}
                <span className="plan-price-period">
                  {" "}
                  · {formatPrice(plan.price_usd_month)}
                  {Number(plan.price_usd_month) > 0 ? " USD/mes" : ""}
                </span>
              </p>
              <ul className="plan-specs">
                <li>
                  {plan.max_devices === 1
                    ? "1 dispositivo"
                    : `${plan.max_devices} dispositivos`}
                </li>
                <li>
                  Hasta {plan.max_resolution} · {plan.max_fps} fps
                </li>
                <li>
                  {plan.monthly_hours === null
                    ? "Horas ilimitadas (uso justo)"
                    : `${plan.monthly_hours} horas de transmisión al mes`}
                </li>
              </ul>
              {plan.features.length > 0 && (
                <ul className="plan-features">
                  {plan.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
              )}
              <Link to="/precios" className="btn btn-ghost btn-sm">
                Ver todos los planes
              </Link>
            </>
          ) : (
            <Loader text="Cargando plan…" />
          )}
        </section>

        <section className="card">
          <h2 className="section-title">Uso del período</h2>
          {error !== null && <ErrorNotice message={error} onRetry={load} />}
          {error === null && usage === null && <Loader text="Cargando uso…" />}
          {usage !== null && (
            <>
              <p className="muted small">
                Período: {formatDate(usage.period_start)} — {formatDate(usage.period_end)}
              </p>
              <div className="usage-row">
                <div className="usage-head">
                  <span>Horas de transmisión</span>
                  <span>
                    {formatHours(usage.hours_used)}
                    {usage.hours_limit !== null
                      ? ` de ${formatHours(usage.hours_limit)}`
                      : " · sin límite (uso justo)"}
                  </span>
                </div>
                <ProgressBar value={usage.hours_used} max={usage.hours_limit} />
              </div>
              <div className="usage-row">
                <div className="usage-head">
                  <span>Dispositivos</span>
                  <span>
                    {usage.devices_used} de {usage.devices_limit}
                  </span>
                </div>
                <ProgressBar value={usage.devices_used} max={usage.devices_limit} />
              </div>
              <p className="muted small">
                Al agotar las horas del plan, el celular no podrá publicar vídeo hasta que inicie el
                siguiente período o mejores tu plan.
              </p>
            </>
          )}
        </section>
      </div>
    </>
  );
}
