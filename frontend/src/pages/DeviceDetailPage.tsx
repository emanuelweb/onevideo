import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { CopyButton } from "../components/CopyButton";
import { ErrorNotice } from "../components/ErrorNotice";
import { Loader } from "../components/Loader";
import { Modal } from "../components/Modal";
import { PairingCodeView } from "../components/PairingCodeView";
import { ProgressBar } from "../components/ProgressBar";
import { StatusBadge } from "../components/StatusBadge";
import { useConsoleSocket } from "../hooks/useConsoleSocket";
import { api, getErrorMessage } from "../lib/api";
import {
  facingLabel,
  formatBytes,
  formatDate,
  formatGB,
  formatRelative,
  formatTime,
  networkLabel,
} from "../lib/format";
import type {
  CommandType,
  Device,
  Fps,
  PairingCodeInfo,
  Recording,
  RecordingList,
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

/** Fecha/hora local de la grabación; si el nombre no trae fecha, el nombre tal cual. */
function recordingLabel(recording: Recording): string {
  return recording.started_at !== null
    ? `${formatDate(recording.started_at)} · ${formatTime(recording.started_at)}`
    : recording.filename;
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

  // Grabación en la nube
  const [recordingList, setRecordingList] = useState<RecordingList | null>(null);
  const [recordingsError, setRecordingsError] = useState<string | null>(null);
  const [recordingNotice, setRecordingNotice] = useState<string | null>(null);
  const [togglingRecording, setTogglingRecording] = useState(false);
  const [tokenBusyId, setTokenBusyId] = useState<string | null>(null);
  const [playback, setPlayback] = useState<{ recording: Recording; url: string } | null>(null);
  const [recordingToDelete, setRecordingToDelete] = useState<Recording | null>(null);
  const [deletingRecording, setDeletingRecording] = useState(false);

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
  const recordingOn = device?.recording_on === true;

  const loadRecordings = useCallback(() => {
    setRecordingsError(null);
    api
      .recordings(id)
      .then(setRecordingList)
      .catch((error) => setRecordingsError(getErrorMessage(error)));
  }, [id]);

  useEffect(loadRecordings, [loadRecordings]);

  // Mientras se está grabando, la lista se refresca cada 10 s (solo con la pestaña visible).
  useEffect(() => {
    if (!recordingOn) return;
    const refresh = (): void => {
      if (document.visibilityState === "visible") loadRecordings();
    };
    const timer = window.setInterval(refresh, 10_000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [recordingOn, loadRecordings]);

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

  async function handleToggleRecording(): Promise<void> {
    if (device === null || togglingRecording) return;
    const enabled = !device.recording_on;
    setRecordingNotice(null);
    setTogglingRecording(true);
    // Update optimista: se revierte si el servidor rechaza el cambio (p. ej. 403 de cuota).
    setDevice({ ...device, recording_on: enabled });
    try {
      const updated = await api.setRecording(id, enabled);
      setDevice(updated);
      loadRecordings();
    } catch (error) {
      setDevice((current) =>
        current !== null ? { ...current, recording_on: !enabled } : current,
      );
      setRecordingNotice(getErrorMessage(error));
    } finally {
      setTogglingRecording(false);
    }
  }

  async function handleViewRecording(recording: Recording): Promise<void> {
    setRecordingNotice(null);
    setTokenBusyId(recording.id);
    try {
      const token = await api.recordingDownloadToken(id, recording.id);
      setPlayback({ recording, url: token.url });
    } catch (error) {
      setRecordingNotice(getErrorMessage(error));
    } finally {
      setTokenBusyId(null);
    }
  }

  async function handleDownloadRecording(recording: Recording): Promise<void> {
    setRecordingNotice(null);
    setTokenBusyId(recording.id);
    try {
      const token = await api.recordingDownloadToken(id, recording.id);
      window.open(token.url, "_blank", "noopener");
    } catch (error) {
      setRecordingNotice(getErrorMessage(error));
    } finally {
      setTokenBusyId(null);
    }
  }

  async function handleDeleteRecording(): Promise<void> {
    if (recordingToDelete === null) return;
    setRecordingNotice(null);
    setDeletingRecording(true);
    try {
      await api.deleteRecording(id, recordingToDelete.id);
      loadRecordings();
    } catch (error) {
      setRecordingNotice(getErrorMessage(error));
    } finally {
      setDeletingRecording(false);
      setRecordingToDelete(null);
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
  // Más reciente primero: el nombre de archivo empieza con la fecha, así que ordena solo.
  const recordings =
    recordingList !== null
      ? [...recordingList.items].sort((a, b) => b.filename.localeCompare(a.filename))
      : [];

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

          <section className="card">
            <h2 className="section-title">Grabación en la nube</h2>
            {recordingNotice !== null && (
              <div className="notice notice-error" role="alert">
                {recordingNotice}
              </div>
            )}
            <div className="recording-toggle-row">
              <div>
                <span className="control-label">Grabar</span>
                <p className="muted small">
                  {recordingOn
                    ? "Se graba mientras la cámara transmite."
                    : "Activa el interruptor para guardar como MP4 lo que transmita esta cámara."}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={recordingOn}
                aria-label="Grabar"
                className={recordingOn ? "switch switch-on" : "switch"}
                disabled={togglingRecording}
                onClick={() => void handleToggleRecording()}
              >
                <span className="switch-thumb" aria-hidden="true" />
              </button>
            </div>

            {recordingList !== null && (
              <div className="usage-row">
                <div className="usage-head">
                  <span>Almacenamiento</span>
                  <span>
                    {formatGB(recordingList.used_bytes)} de {formatGB(recordingList.limit_bytes)}{" "}
                    usados
                  </span>
                </div>
                <ProgressBar value={recordingList.used_bytes} max={recordingList.limit_bytes} />
              </div>
            )}

            {recordingsError !== null && (
              <ErrorNotice message={recordingsError} onRetry={loadRecordings} />
            )}
            {recordingsError === null && recordingList === null && (
              <Loader text="Cargando grabaciones…" />
            )}
            {recordingList !== null &&
              (recordings.length === 0 ? (
                <p className="muted">
                  Aún no hay grabaciones. Con el interruptor activado, cada transmisión queda
                  guardada aquí.
                </p>
              ) : (
                <ul className="recording-list">
                  {recordings.map((recording) => (
                    <li key={recording.id} className="recording-item">
                      <div className="recording-info">
                        <span className="recording-when">{recordingLabel(recording)}</span>
                        <span className="muted small">{formatBytes(recording.size_bytes)}</span>
                        {recording.in_progress && (
                          <span className="badge badge-recording">Grabando…</span>
                        )}
                      </div>
                      <div className="btn-row">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={tokenBusyId === recording.id}
                          onClick={() => void handleViewRecording(recording)}
                        >
                          Ver
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={tokenBusyId === recording.id}
                          onClick={() => void handleDownloadRecording(recording)}
                        >
                          Descargar
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          disabled={recording.in_progress}
                          title={
                            recording.in_progress
                              ? "Esa grabación está en curso. Detén la grabación antes de eliminarla."
                              : undefined
                          }
                          onClick={() => setRecordingToDelete(recording)}
                        >
                          Eliminar
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              ))}
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

      {playback !== null && (
        <Modal
          title={`Grabación · ${recordingLabel(playback.recording)}`}
          onClose={() => setPlayback(null)}
        >
          <video
            className="recording-video"
            src={playback.url}
            controls
            autoPlay
            playsInline
          />
          <p className="muted small">
            La reproducción usa un enlace temporal (expira en 6 horas). Para conservar el archivo,
            usa «Descargar».
          </p>
        </Modal>
      )}

      {recordingToDelete !== null && (
        <Modal title="Eliminar grabación" onClose={() => setRecordingToDelete(null)}>
          <p>
            ¿Eliminar la grabación del {recordingLabel(recordingToDelete)} (
            {formatBytes(recordingToDelete.size_bytes)})? Esta acción no se puede deshacer.
          </p>
          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-danger"
              disabled={deletingRecording}
              onClick={() => void handleDeleteRecording()}
            >
              {deletingRecording ? "Eliminando…" : "Sí, eliminar"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setRecordingToDelete(null)}
            >
              Cancelar
            </button>
          </div>
        </Modal>
      )}

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
