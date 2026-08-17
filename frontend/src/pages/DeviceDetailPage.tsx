import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { CopyButton } from "../components/CopyButton";
import { ErrorNotice } from "../components/ErrorNotice";
import { Loader } from "../components/Loader";
import { Modal } from "../components/Modal";
import { PairingCodeView } from "../components/PairingCodeView";
import { StatusBadge } from "../components/StatusBadge";
import { useConsoleSocket } from "../hooks/useConsoleSocket";
import { api, getErrorMessage } from "../lib/api";
import { facingLabel, formatRelative, networkLabel } from "../lib/format";
import type {
  CommandType,
  Device,
  Fps,
  PairingCodeInfo,
  Resolution,
  StreamInfo,
} from "../lib/types";
import { WhepPlayer } from "../lib/whep";

type PreviewState = "idle" | "connecting" | "connected" | "error";

interface Notice {
  kind: "ok" | "warn" | "error";
  text: string;
}

// Bitrate sugerido por combinación calidad/fps (el dispositivo lo aplica de forma cooperativa)
function recommendedBitrateKbps(resolution: Resolution, fps: Fps): number {
  if (resolution === "1080p") return fps === 60 ? 6000 : 4500;
  return fps === 60 ? 3500 : 2500;
}

export default function DeviceDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [device, setDevice] = useState<Device | null>(null);
  const [streamInfo, setStreamInfo] = useState<StreamInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pendingCommand, setPendingCommand] = useState<CommandType | null>(null);

  const [resolution, setResolution] = useState<Resolution>("720p");
  const [fps, setFps] = useState<Fps>(30);
  const [renameValue, setRenameValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [pairingInfo, setPairingInfo] = useState<PairingCodeInfo | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [rotating, setRotating] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playerRef = useRef<WhepPlayer | null>(null);
  const [previewState, setPreviewState] = useState<PreviewState>("idle");

  const load = useCallback(() => {
    setLoadError(null);
    Promise.all([api.device(id), api.streamInfo(id)])
      .then(([deviceData, stream]) => {
        setDevice(deviceData);
        setStreamInfo(stream);
      })
      .catch((error) => setLoadError(getErrorMessage(error)));
  }, [id]);

  useEffect(load, [load]);

  useConsoleSocket(
    useCallback(
      (updated: Device) => {
        if (updated.id === id) setDevice(updated);
      },
      [id],
    ),
  );

  // Sincroniza los formularios locales solo cuando el dispositivo carga,
  // para no pisar lo que el usuario esté editando con cada push del WS.
  const loadedDeviceId = device?.id;
  useEffect(() => {
    if (device === null) return;
    setResolution(device.settings.resolution);
    setFps(device.settings.fps);
    setRenameValue(device.name);
  }, [loadedDeviceId]);

  const isStreaming = device?.status === "streaming";

  const startPreview = useCallback(() => {
    const video = videoRef.current;
    if (video === null || streamInfo === null) return;
    playerRef.current?.stop();
    const player = new WhepPlayer((state) => {
      if (playerRef.current !== player) return;
      if (state === "connecting") setPreviewState("connecting");
      else if (state === "connected") setPreviewState("connected");
      else setPreviewState("error");
    });
    playerRef.current = player;
    player.play(streamInfo.whep_url, video).catch(() => {
      if (playerRef.current === player) setPreviewState("error");
    });
  }, [streamInfo]);

  useEffect(() => {
    if (!isStreaming || streamInfo === null) {
      playerRef.current?.stop();
      playerRef.current = null;
      setPreviewState("idle");
      return;
    }
    startPreview();
    return () => {
      playerRef.current?.stop();
      playerRef.current = null;
    };
  }, [isStreaming, streamInfo, startPreview]);

  async function runCommand(type: CommandType, payload?: Record<string, unknown>): Promise<void> {
    setNotice(null);
    setPendingCommand(type);
    try {
      const result = await api.sendCommand(id, type, payload);
      setNotice(
        result.delivered
          ? { kind: "ok", text: "Comando enviado al dispositivo." }
          : { kind: "warn", text: "El dispositivo no está conectado: el comando no se entregó." },
      );
    } catch (error) {
      setNotice({ kind: "error", text: getErrorMessage(error) });
    } finally {
      setPendingCommand(null);
    }
  }

  function applyQuality(): void {
    void runCommand("set_quality", {
      resolution,
      fps,
      bitrate_kbps: recommendedBitrateKbps(resolution, fps),
    });
  }

  async function handleRename(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmed = renameValue.trim();
    if (trimmed === "" || device === null || trimmed === device.name) return;
    setSaving(true);
    try {
      const updated = await api.updateDevice(id, { name: trimmed });
      setDevice(updated);
      setNotice({ kind: "ok", text: "Nombre actualizado." });
    } catch (error) {
      setNotice({ kind: "error", text: getErrorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  async function handleRegeneratePairing(): Promise<void> {
    try {
      setPairingInfo(await api.regeneratePairingCode(id));
    } catch (error) {
      setNotice({ kind: "error", text: getErrorMessage(error) });
    }
  }

  async function handleRotateToken(): Promise<void> {
    setRotating(true);
    try {
      const info = await api.rotateViewToken(id);
      setStreamInfo(info);
      setNotice({
        kind: "ok",
        text: "Token rotado. Actualiza la URL en OBS: las URLs anteriores dejaron de funcionar.",
      });
    } catch (error) {
      setNotice({ kind: "error", text: getErrorMessage(error) });
    } finally {
      setRotating(false);
    }
  }

  async function handleDelete(): Promise<void> {
    try {
      await api.deleteDevice(id);
      navigate("/app", { replace: true });
    } catch (error) {
      setNotice({ kind: "error", text: getErrorMessage(error) });
      setConfirmingDelete(false);
    }
  }

  if (loadError !== null) {
    return (
      <>
        <Link to="/app" className="back-link">
          ← Dispositivos
        </Link>
        <ErrorNotice message={loadError} onRetry={load} />
      </>
    );
  }

  if (device === null) {
    return (
      <div className="page-loader">
        <Loader text="Cargando dispositivo…" />
      </div>
    );
  }

  const plan = user?.plan ?? null;
  const allow1080 = plan === null || plan.max_resolution === "1080p";
  const allow60 = plan === null || plan.max_fps >= 60;
  const busy = pendingCommand !== null;
  const telemetry = device.telemetry;

  return (
    <>
      <Link to="/app" className="back-link">
        ← Dispositivos
      </Link>

      <div className="page-header">
        <div>
          <div className="detail-title-row">
            <h1 className="page-title">{device.name}</h1>
            <StatusBadge status={device.status} />
          </div>
          <p className="page-subtitle">
            {device.model ?? "Modelo por definir"} · {device.platform ?? "android"} · Última
            conexión: {formatRelative(device.last_seen_at)}
          </p>
        </div>
      </div>

      <div className="detail-layout">
        <div className="detail-main">
          <section className="card preview-card">
            <h2 className="section-title">Vista previa en vivo</h2>
            <div className="preview-wrap">
              <video ref={videoRef} className="preview-video" autoPlay playsInline muted />
              {!isStreaming && (
                <div className="preview-overlay">
                  <p>El dispositivo no está transmitiendo.</p>
                  <p className="muted small">
                    La vista previa aparecerá automáticamente cuando el celular publique vídeo.
                  </p>
                </div>
              )}
              {isStreaming && previewState === "connecting" && (
                <div className="preview-overlay">
                  <Loader text="Conectando vista previa…" />
                </div>
              )}
              {isStreaming && previewState === "error" && (
                <div className="preview-overlay">
                  <p>Se perdió la conexión con la vista previa.</p>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={startPreview}>
                    Reintentar
                  </button>
                </div>
              )}
            </div>
          </section>

          <section className="card">
            <h2 className="section-title">Controles remotos</h2>
            {notice !== null && (
              <div className={`notice notice-${notice.kind}`} role="status">
                {notice.text}
              </div>
            )}
            <div className="controls-grid">
              <div className="control-group">
                <span className="control-label">Cámara</span>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => void runCommand(device.camera_on ? "camera_off" : "camera_on")}
                >
                  {device.camera_on ? "Apagar cámara" : "Encender cámara"}
                </button>
              </div>
              <div className="control-group">
                <span className="control-label">
                  Lente: {facingLabel(telemetry?.facing ?? device.settings.facing)}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={busy}
                  onClick={() => void runCommand("switch_camera")}
                >
                  Cambiar frontal/trasera
                </button>
              </div>
              <div className="control-group">
                <span className="control-label">Linterna</span>
                <div className="btn-row">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={busy}
                    onClick={() => void runCommand("torch_on")}
                  >
                    Encender
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={busy}
                    onClick={() => void runCommand("torch_off")}
                  >
                    Apagar
                  </button>
                </div>
              </div>
              <div className="control-group">
                <span className="control-label">Stream</span>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={busy}
                  onClick={() => void runCommand("restart_stream")}
                >
                  Reiniciar stream
                </button>
              </div>
            </div>

            <div className="quality-row">
              <div className="control-group">
                <label className="control-label" htmlFor="resolution">
                  Resolución
                </label>
                <select
                  id="resolution"
                  className="select"
                  value={resolution}
                  onChange={(event) =>
                    setResolution(event.target.value === "1080p" ? "1080p" : "720p")
                  }
                >
                  <option value="720p">720p</option>
                  <option value="1080p" disabled={!allow1080}>
                    {allow1080 ? "1080p" : "1080p (mejora tu plan)"}
                  </option>
                </select>
              </div>
              <div className="control-group">
                <label className="control-label" htmlFor="fps">
                  Cuadros por segundo
                </label>
                <select
                  id="fps"
                  className="select"
                  value={fps}
                  onChange={(event) => setFps(Number(event.target.value) === 60 ? 60 : 30)}
                >
                  <option value={30}>30 fps</option>
                  <option value={60} disabled={!allow60}>
                    {allow60 ? "60 fps" : "60 fps (mejora tu plan)"}
                  </option>
                </select>
              </div>
              <div className="control-group">
                <span className="control-label">&nbsp;</span>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={applyQuality}
                >
                  {pendingCommand === "set_quality" ? "Aplicando…" : "Aplicar calidad"}
                </button>
              </div>
            </div>
            <p className="muted small">
              La calidad se aplica de forma cooperativa: el dispositivo ajusta su cámara según los
              límites de tu plan; el servidor no transcodifica.
            </p>
          </section>

          <section className="card">
            <h2 className="section-title">Telemetría</h2>
            {telemetry !== null ? (
              <div className="stat-grid">
                <div className="stat-card">
                  <span className="stat-value">
                    {telemetry.battery !== null ? `${telemetry.battery}%` : "—"}
                  </span>
                  <span className="stat-label">
                    Batería{telemetry.charging === true ? " (cargando)" : ""}
                  </span>
                </div>
                <div className="stat-card">
                  <span className="stat-value">
                    {telemetry.temp_c !== null ? `${telemetry.temp_c} °C` : "—"}
                  </span>
                  <span className="stat-label">Temperatura</span>
                </div>
                <div className="stat-card">
                  <span className="stat-value">{networkLabel(telemetry.network)}</span>
                  <span className="stat-label">Red</span>
                </div>
                <div className="stat-card">
                  <span className="stat-value">
                    {telemetry.bitrate_kbps !== null ? `${telemetry.bitrate_kbps} kbps` : "—"}
                  </span>
                  <span className="stat-label">Bitrate</span>
                </div>
                <div className="stat-card">
                  <span className="stat-value">{telemetry.resolution ?? "—"}</span>
                  <span className="stat-label">Resolución</span>
                </div>
                <div className="stat-card">
                  <span className="stat-value">{facingLabel(telemetry.facing)}</span>
                  <span className="stat-label">Lente</span>
                </div>
              </div>
            ) : (
              <p className="muted">
                Sin telemetría todavía. Se actualiza en tiempo real cuando el celular se conecta.
              </p>
            )}
          </section>
        </div>

        <div className="detail-side">
          <section className="card">
            <h2 className="section-title">Usar en OBS</h2>
            {streamInfo !== null ? (
              <>
                <div className="url-row">
                  <span className="url-label">URL del player (Browser Source)</span>
                  <code className="url-code">{streamInfo.player_url}</code>
                  <CopyButton value={streamInfo.player_url} label="Copiar URL" />
                </div>
                <div className="url-row">
                  <span className="url-label">URL WHEP (avanzado)</span>
                  <code className="url-code">{streamInfo.whep_url}</code>
                  <CopyButton value={streamInfo.whep_url} label="Copiar URL" />
                </div>
                <div className="btn-row">
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={rotating}
                    onClick={() => void handleRotateToken()}
                  >
                    {rotating ? "Rotando…" : "Rotar token de vista"}
                  </button>
                  <Link to="/app/guia-obs" className="btn btn-ghost btn-sm">
                    Ver guía de OBS
                  </Link>
                </div>
                <p className="muted small">
                  Rotar el token invalida las URLs anteriores. Útil si compartiste la URL por error.
                </p>
              </>
            ) : (
              <Loader text="Cargando URLs de streaming…" />
            )}
          </section>

          <section className="card">
            <h2 className="section-title">Dispositivo</h2>
            <form className="rename-row" onSubmit={(event) => void handleRename(event)}>
              <div className="field">
                <label className="label" htmlFor="rename">
                  Nombre
                </label>
                <input
                  id="rename"
                  className="input"
                  type="text"
                  required
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                />
              </div>
              <button type="submit" className="btn btn-ghost btn-sm" disabled={saving}>
                {saving ? "Guardando…" : "Guardar"}
              </button>
            </form>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-block"
              onClick={() => void handleRegeneratePairing()}
            >
              Generar nuevo código de emparejamiento
            </button>
            <p className="muted small">
              Genera un código nuevo si cambiaste de celular. El código anterior queda invalidado.
            </p>
            <div className="danger-zone">
              {confirmingDelete ? (
                <div className="inline-confirm">
                  <p className="small">¿Eliminar este dispositivo? Esta acción no se puede deshacer.</p>
                  <div className="btn-row">
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => void handleDelete()}
                    >
                      Sí, eliminar
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setConfirmingDelete(false)}
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => setConfirmingDelete(true)}
                >
                  Eliminar dispositivo
                </button>
              )}
            </div>
          </section>
        </div>
      </div>

      {pairingInfo !== null && (
        <Modal title="Nuevo código de emparejamiento" onClose={() => setPairingInfo(null)}>
          <PairingCodeView code={pairingInfo.code} expiresAt={pairingInfo.expires_at} />
          <div className="modal-footer">
            <button type="button" className="btn btn-primary" onClick={() => setPairingInfo(null)}>
              Entendido
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
