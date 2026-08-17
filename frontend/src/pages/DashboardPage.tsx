import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice } from "../components/ErrorNotice";
import { Loader } from "../components/Loader";
import { Modal } from "../components/Modal";
import { PairingCodeView } from "../components/PairingCodeView";
import { StatusBadge } from "../components/StatusBadge";
import { useConsoleSocket } from "../hooks/useConsoleSocket";
import { api, getErrorMessage } from "../lib/api";
import { formatRelative, networkLabel } from "../lib/format";
import type { Device, DeviceWithPairing } from "../lib/types";

export default function DashboardPage() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [pairing, setPairing] = useState<DeviceWithPairing | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .devices()
      .then(setDevices)
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  useEffect(load, [load]);

  const wsConnected = useConsoleSocket(
    useCallback((device: Device) => {
      setDevices((current) => {
        if (current === null) return current;
        const index = current.findIndex((item) => item.id === device.id);
        if (index === -1) return [...current, device];
        const next = [...current];
        next[index] = device;
        return next;
      });
    }, []),
  );

  async function handleCreate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const name = newName.trim();
    if (name === "") return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createDevice(name);
      setDevices((current) => (current === null ? [created] : [...current, created]));
      setPairing(created);
      setShowCreate(false);
      setNewName("");
    } catch (err) {
      setCreateError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Tus dispositivos</h1>
          <p className="page-subtitle">
            Cada celular emparejado aparece aquí con su estado en tiempo real.
          </p>
        </div>
        <div className="page-actions">
          <span className={wsConnected ? "live-indicator" : "live-indicator offline"}>
            <span className="live-dot" aria-hidden="true" />
            {wsConnected ? "En vivo" : "Reconectando…"}
          </span>
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
            Crear dispositivo
          </button>
        </div>
      </div>

      {error !== null && <ErrorNotice message={error} onRetry={load} />}
      {error === null && devices === null && <Loader text="Cargando dispositivos…" />}

      {devices !== null && devices.length === 0 && (
        <div className="empty-state card">
          <h2>Aún no tienes dispositivos</h2>
          <p className="muted">
            Crea tu primer dispositivo y empareja tu celular Android con un código para empezar a
            transmitir a OBS en minutos.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
            Crear mi primer dispositivo
          </button>
        </div>
      )}

      {devices !== null && devices.length > 0 && (
        <div className="device-grid">
          {devices.map((device) => (
            <Link
              key={device.id}
              to={`/app/dispositivos/${device.id}`}
              className="device-card card"
            >
              <div className="device-card-top">
                <h2 className="device-name">{device.name}</h2>
                <StatusBadge status={device.status} />
              </div>
              <p className="device-meta">
                {device.model ?? "Modelo por definir"} · {device.platform ?? "android"}
              </p>
              <div className="device-stats">
                {device.telemetry !== null ? (
                  <>
                    <span className="device-stat">
                      Batería{" "}
                      {device.telemetry.battery !== null ? `${device.telemetry.battery}%` : "—"}
                    </span>
                    <span className="device-stat">{networkLabel(device.telemetry.network)}</span>
                    <span className="device-stat">
                      Cámara {device.camera_on ? "encendida" : "apagada"}
                    </span>
                  </>
                ) : (
                  <span className="device-stat muted">Sin telemetría todavía</span>
                )}
              </div>
              <p className="device-last-seen muted">
                Última conexión: {formatRelative(device.last_seen_at)}
              </p>
            </Link>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal title="Crear dispositivo" onClose={() => setShowCreate(false)}>
          <form onSubmit={(event) => void handleCreate(event)}>
            <div className="field">
              <label className="label" htmlFor="device-name">
                Nombre del dispositivo
              </label>
              <input
                id="device-name"
                className="input"
                type="text"
                placeholder="Ej.: Cámara principal"
                required
                autoFocus
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
            </div>
            {createError !== null && (
              <p className="form-error" role="alert">
                {createError}
              </p>
            )}
            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setShowCreate(false)}
              >
                Cancelar
              </button>
              <button type="submit" className="btn btn-primary" disabled={creating}>
                {creating ? "Creando…" : "Crear y obtener código"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {pairing !== null && (
        <Modal title={`Emparejar “${pairing.name}”`} onClose={() => setPairing(null)}>
          <PairingCodeView code={pairing.pairing_code} expiresAt={pairing.pairing_expires_at} />
          <ol className="pairing-steps">
            <li>Instala y abre la app OneVideo en tu celular Android.</li>
            <li>Toca “Emparejar con código” e ingresa el código de arriba.</li>
            <li>El dispositivo aparecerá como “En línea” en este panel.</li>
          </ol>
          <div className="modal-footer">
            <button type="button" className="btn btn-ghost" onClick={() => setPairing(null)}>
              Cerrar
            </button>
            <Link
              to={`/app/dispositivos/${pairing.id}`}
              className="btn btn-primary"
              onClick={() => setPairing(null)}
            >
              Abrir dispositivo
            </Link>
          </div>
        </Modal>
      )}
    </>
  );
}
