import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { useAuth } from "../auth/AuthContext";
import { ErrorNotice } from "../components/ErrorNotice";
import { Loader } from "../components/Loader";
import { Modal } from "../components/Modal";
import { api, getErrorMessage } from "../lib/api";
import { formatDate, formatHours, planSourceLabel } from "../lib/format";
import type { AdminStats, AdminUser, AdminUserList, PlanGrant, PlanPublic } from "../lib/types";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 400;

// Motivos por los que un control queda bloqueado sobre la propia cuenta (los mismos
// que devuelve el backend con 409, para que la UI no llegue nunca a provocarlos).
const SELF_DEACTIVATE_HINT = "No puedes desactivar tu propia cuenta.";
const SELF_DEMOTE_HINT = "No puedes quitarte a ti mismo los permisos de administrador.";
const SELF_DELETE_HINT = "No puedes eliminar tu propia cuenta.";

interface Notice {
  kind: "ok" | "warn" | "error";
  text: string;
}

interface PlanDialog {
  user: AdminUser;
  planCode: string;
  expiresAt: string;
  note: string;
}

interface GrantsDialog {
  user: AdminUser;
  grants: PlanGrant[] | null;
  error: string | null;
}

/** Fecha de hoy en formato `YYYY-MM-DD` (hora local) para el mínimo del input `date`. */
function todayInputValue(): string {
  return toDateInputValue(new Date().toISOString());
}

/** Convierte un ISO del backend al valor de un input `date` en hora local. */
function toDateInputValue(iso: string | null): string {
  if (iso === null) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

/**
 * Convierte el valor del input `date` en el instante que espera el backend.
 * Se toma el final del día elegido (hora local) para que elegir "hoy" siga siendo
 * una fecha futura y el plan valga todo el día. Vacío = sin vencimiento.
 */
function toExpiresAt(value: string): string | null {
  if (value === "") return null;
  const parts = value.split("-").map(Number);
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) return null;
  const [year, month, day] = parts;
  return new Date(year, month - 1, day, 23, 59, 59).toISOString();
}

/** True si la fecha ISO ya quedó atrás (o no es válida en el futuro). */
function isPast(iso: string): boolean {
  const date = new Date(iso);
  return !Number.isNaN(date.getTime()) && date.getTime() <= Date.now();
}

/**
 * La degradación al plan gratuito es perezosa: se aplica la próxima vez que esa
 * cuenta usa la API, así que el listado puede mostrar un vencimiento ya cumplido.
 * Por eso se distingue el pasado del futuro en vez de anunciar siempre «vence el».
 */
function expiryLabel(expiresAt: string | null): string {
  if (expiresAt === null) return "sin vencimiento";
  return isPast(expiresAt)
    ? `venció el ${formatDate(expiresAt)}`
    : `vence el ${formatDate(expiresAt)}`;
}

/**
 * Botón de acción de la tabla. Cuando `hint` está presente el botón va deshabilitado
 * y se envuelve en un `span` con el motivo: los elementos deshabilitados no muestran
 * su propio `title` en varios navegadores.
 */
function RowAction({
  label,
  onClick,
  disabled = false,
  danger = false,
  hint,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  hint?: string;
}): ReactElement {
  const button = (
    <button
      type="button"
      className={danger ? "btn btn-danger btn-sm" : "btn btn-ghost btn-sm"}
      disabled={disabled || hint !== undefined}
      onClick={onClick}
    >
      {label}
    </button>
  );
  if (hint === undefined) return button;
  return (
    <span className="action-hint" title={hint}>
      {button}
    </span>
  );
}

export default function AdminPage() {
  const { user: currentUser } = useAuth();

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);

  const [plans, setPlans] = useState<PlanPublic[]>([]);
  const [plansError, setPlansError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [offset, setOffset] = useState(0);

  const [result, setResult] = useState<AdminUserList | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(false);

  const [notice, setNotice] = useState<Notice | null>(null);
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);

  const [planDialog, setPlanDialog] = useState<PlanDialog | null>(null);
  const [planDialogError, setPlanDialogError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);

  const [deleteDialog, setDeleteDialog] = useState<AdminUser | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [grantsDialog, setGrantsDialog] = useState<GrantsDialog | null>(null);

  // Descarta respuestas de búsquedas viejas que llegan fuera de orden.
  const requestIdRef = useRef(0);

  const loadStats = useCallback(() => {
    setStatsError(null);
    api
      .adminStats()
      .then(setStats)
      .catch((error) => setStatsError(getErrorMessage(error)));
  }, []);

  const loadUsers = useCallback(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setListError(null);
    setLoadingUsers(true);
    api
      .adminUsers({ search: appliedSearch, limit: PAGE_SIZE, offset })
      .then((data) => {
        if (requestIdRef.current === requestId) setResult(data);
      })
      .catch((error) => {
        if (requestIdRef.current === requestId) setListError(getErrorMessage(error));
      })
      .finally(() => {
        if (requestIdRef.current === requestId) setLoadingUsers(false);
      });
  }, [appliedSearch, offset]);

  useEffect(loadStats, [loadStats]);
  useEffect(loadUsers, [loadUsers]);

  useEffect(() => {
    setPlansError(null);
    api
      .plans()
      .then(setPlans)
      .catch((error) => setPlansError(getErrorMessage(error)));
  }, []);

  // Buscador con debounce: cada tecla reinicia el temporizador y vuelve a la primera página.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setAppliedSearch(search.trim());
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  function replaceUser(updated: AdminUser): void {
    setResult((current) =>
      current === null
        ? current
        : {
            ...current,
            items: current.items.map((item) => (item.id === updated.id ? updated : item)),
          },
    );
  }

  async function handleToggleActive(target: AdminUser): Promise<void> {
    setNotice(null);
    setPendingUserId(target.id);
    try {
      const updated = await api.adminUpdateUser(target.id, { is_active: !target.is_active });
      replaceUser(updated);
      setNotice({
        kind: "ok",
        text: updated.is_active
          ? `Se activó la cuenta de ${updated.email}.`
          : `Se desactivó la cuenta de ${updated.email}.`,
      });
      loadStats();
    } catch (error) {
      setNotice({ kind: "error", text: getErrorMessage(error) });
    } finally {
      setPendingUserId(null);
    }
  }

  async function handleToggleSuperadmin(target: AdminUser): Promise<void> {
    setNotice(null);
    setPendingUserId(target.id);
    try {
      const updated = await api.adminUpdateUser(target.id, {
        is_superadmin: !target.is_superadmin,
      });
      replaceUser(updated);
      setNotice({
        kind: "ok",
        text: updated.is_superadmin
          ? `${updated.email} ahora es administrador.`
          : `${updated.email} ya no es administrador.`,
      });
    } catch (error) {
      setNotice({ kind: "error", text: getErrorMessage(error) });
    } finally {
      setPendingUserId(null);
    }
  }

  function openPlanDialog(target: AdminUser, planCode: string): void {
    setPlanDialogError(null);
    // Solo se precarga un vencimiento que todavía sea futuro: uno pasado violaría el
    // `min` del input y el navegador bloquearía el envío con su mensaje nativo.
    const stored = target.plan_expires_at;
    const keepStored = stored !== null && !isPast(stored);
    setPlanDialog({
      user: target,
      planCode,
      expiresAt: keepStored ? toDateInputValue(stored) : "",
      note: "",
    });
  }

  async function handleAssignPlan(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (planDialog === null) return;
    const note = planDialog.note.trim();
    setAssigning(true);
    setPlanDialogError(null);
    try {
      const updated = await api.adminAssignPlan(planDialog.user.id, {
        plan_code: planDialog.planCode,
        expires_at: toExpiresAt(planDialog.expiresAt),
        note: note === "" ? null : note,
      });
      replaceUser(updated);
      setPlanDialog(null);
      setNotice({
        kind: "ok",
        text: `Plan ${updated.plan.name} asignado a ${updated.email} (${expiryLabel(
          updated.plan_expires_at,
        )}).`,
      });
      loadStats();
    } catch (error) {
      setPlanDialogError(getErrorMessage(error));
    } finally {
      setAssigning(false);
    }
  }

  function openDeleteDialog(target: AdminUser): void {
    setDeleteConfirm("");
    setDeleteError(null);
    setDeleteDialog(target);
  }

  async function handleDelete(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (deleteDialog === null) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.adminDeleteUser(deleteDialog.id);
      const wasLastOfPage = result !== null && result.items.length === 1 && offset > 0;
      setDeleteDialog(null);
      setNotice({ kind: "ok", text: `Se eliminó la cuenta de ${deleteDialog.email}.` });
      // Si la página quedó vacía se retrocede una; si no, se recarga la actual.
      if (wasLastOfPage) setOffset(Math.max(0, offset - PAGE_SIZE));
      else loadUsers();
      loadStats();
    } catch (error) {
      setDeleteError(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  }

  function openGrantsDialog(target: AdminUser): void {
    setGrantsDialog({ user: target, grants: null, error: null });
    api
      .adminUserGrants(target.id)
      .then((grants) => {
        setGrantsDialog((current) =>
          current !== null && current.user.id === target.id ? { ...current, grants } : current,
        );
      })
      .catch((error) => {
        setGrantsDialog((current) =>
          current !== null && current.user.id === target.id
            ? { ...current, error: getErrorMessage(error) }
            : current,
        );
      });
  }

  const total = result?.total ?? 0;
  const pageCount = result?.items.length ?? 0;
  const rangeFrom = pageCount === 0 ? 0 : offset + 1;
  const rangeTo = offset + pageCount;
  const canGoPrev = offset > 0;
  const canGoNext = offset + pageCount < total;
  const planDialogPlan = plans.find((plan) => plan.code === planDialog?.planCode) ?? null;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Administración</h1>
          <p className="page-subtitle">
            Usuarios, planes asignados a mano y estado general del servicio.
          </p>
        </div>
      </div>

      {notice !== null && (
        <div className={`notice notice-${notice.kind}`} role="status">
          {notice.text}
        </div>
      )}

      <section className="card admin-section">
        <h2 className="section-title">Resumen</h2>
        {statsError !== null && <ErrorNotice message={statsError} onRetry={loadStats} />}
        {statsError === null && stats === null && <Loader text="Cargando estadísticas…" />}
        {stats !== null && (
          <>
            <div className="stat-grid">
              <div className="stat-card">
                <span className="stat-value">{stats.users_total}</span>
                <span className="stat-label">Usuarios registrados</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{stats.users_active}</span>
                <span className="stat-label">Cuentas activas</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{stats.devices_total}</span>
                <span className="stat-label">Dispositivos</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{stats.devices_streaming}</span>
                <span className="stat-label">Transmitiendo ahora</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{formatHours(stats.hours_this_month)}</span>
                <span className="stat-label">Horas del mes</span>
              </div>
            </div>
            {stats.users_by_plan.length > 0 && (
              <>
                <p className="muted small admin-chips-title">Usuarios por plan</p>
                <div className="chip-row">
                  {stats.users_by_plan.map((entry) => (
                    <span key={entry.plan_code} className="chip">
                      {entry.plan_name} <strong className="chip-count">{entry.count}</strong>
                    </span>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </section>

      <section className="card admin-section">
        <h2 className="section-title">Usuarios</h2>

        <div className="admin-toolbar">
          <input
            className="input admin-search"
            type="search"
            value={search}
            placeholder="Buscar por correo o nombre…"
            aria-label="Buscar por correo o nombre"
            onChange={(event) => setSearch(event.target.value)}
          />
          <span className="pagination-info">
            {loadingUsers
              ? "Buscando…"
              : total === 0
                ? "Sin resultados"
                : `Mostrando ${rangeFrom}–${rangeTo} de ${total}`}
          </span>
        </div>

        {plansError !== null && (
          <div className="notice notice-warn" role="status">
            No se pudieron cargar los planes: {plansError} La asignación de planes queda
            deshabilitada hasta recargar la página.
          </div>
        )}

        {listError !== null && <ErrorNotice message={listError} onRetry={loadUsers} />}
        {listError === null && result === null && <Loader text="Cargando usuarios…" />}

        {listError === null && result !== null && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Correo</th>
                    <th scope="col">Nombre</th>
                    <th scope="col">Plan</th>
                    <th scope="col">Dispositivos</th>
                    <th scope="col">Horas del mes</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.length === 0 && (
                    <tr>
                      <td className="table-empty" colSpan={7}>
                        {appliedSearch === ""
                          ? "Todavía no hay usuarios registrados."
                          : `Ningún usuario coincide con “${appliedSearch}”.`}
                      </td>
                    </tr>
                  )}
                  {result.items.map((item) => {
                    const isSelf = currentUser !== null && item.id === currentUser.id;
                    const busy = pendingUserId === item.id;
                    return (
                      <tr key={item.id}>
                        <td>
                          <div className="email-cell">
                            <span className="cell-strong">{item.email}</span>
                            {item.is_superadmin && <span className="badge badge-admin">Admin</span>}
                            {isSelf && <span className="badge badge-self">Tú</span>}
                          </div>
                          <span className="cell-note">
                            Registro: {formatDate(item.created_at)}
                          </span>
                        </td>
                        <td>{item.name}</td>
                        <td>
                          <div className="plan-cell">
                            <span className="cell-strong">{item.plan.name}</span>
                            <span
                              className={
                                item.plan_expires_at !== null && isPast(item.plan_expires_at)
                                  ? "cell-note cell-note-warn"
                                  : "cell-note"
                              }
                            >
                              {planSourceLabel(item.plan_source)} ·{" "}
                              {expiryLabel(item.plan_expires_at)}
                            </span>
                            <select
                              className="select select-sm"
                              value=""
                              disabled={plans.length === 0 || busy}
                              aria-label={`Asignar plan a ${item.email}`}
                              onChange={(event) => {
                                const code = event.target.value;
                                if (code !== "") openPlanDialog(item, code);
                              }}
                            >
                              <option value="">Asignar plan…</option>
                              {plans.map((plan) => (
                                <option key={plan.code} value={plan.code}>
                                  {plan.name}
                                </option>
                              ))}
                            </select>
                          </div>
                        </td>
                        <td className="cell-nowrap">{item.devices_count}</td>
                        <td className="cell-nowrap">{formatHours(item.hours_used_month)}</td>
                        <td>
                          <span
                            className={
                              item.is_active
                                ? "status-badge state-active"
                                : "status-badge state-inactive"
                            }
                          >
                            <span className="status-dot" aria-hidden="true" />
                            {item.is_active ? "Activa" : "Inactiva"}
                          </span>
                        </td>
                        <td>
                          <div className="row-actions">
                            <RowAction
                              label="Historial"
                              disabled={busy}
                              onClick={() => openGrantsDialog(item)}
                            />
                            <RowAction
                              label={item.is_active ? "Desactivar" : "Activar"}
                              disabled={busy}
                              hint={isSelf && item.is_active ? SELF_DEACTIVATE_HINT : undefined}
                              onClick={() => void handleToggleActive(item)}
                            />
                            <RowAction
                              label={item.is_superadmin ? "Quitar admin" : "Dar admin"}
                              disabled={busy}
                              hint={isSelf ? SELF_DEMOTE_HINT : undefined}
                              onClick={() => void handleToggleSuperadmin(item)}
                            />
                            <RowAction
                              label="Eliminar"
                              danger
                              disabled={busy}
                              hint={isSelf ? SELF_DELETE_HINT : undefined}
                              onClick={() => openDeleteDialog(item)}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="pagination">
              <span className="pagination-info">
                {total === 0 ? "Sin resultados" : `Mostrando ${rangeFrom}–${rangeTo} de ${total}`}
              </span>
              <div className="btn-row">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={!canGoPrev || loadingUsers}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Anterior
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={!canGoNext || loadingUsers}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Siguiente
                </button>
              </div>
            </div>
          </>
        )}

        <p className="admin-legend">
          Los controles sobre tu propia cuenta están deshabilitados a propósito: evitan que te
          quedes fuera del panel de administración.
        </p>
      </section>

      {planDialog !== null && (
        <Modal
          title={`Asignar plan a ${planDialog.user.email}`}
          onClose={() => setPlanDialog(null)}
        >
          <form onSubmit={(event) => void handleAssignPlan(event)}>
            <div className="field">
              <label className="label" htmlFor="assign-plan">
                Plan
              </label>
              <select
                id="assign-plan"
                className="select"
                value={planDialog.planCode}
                onChange={(event) =>
                  setPlanDialog({ ...planDialog, planCode: event.target.value })
                }
              >
                {plans.map((plan) => (
                  <option key={plan.code} value={plan.code}>
                    {plan.name}
                  </option>
                ))}
              </select>
              {planDialogPlan !== null && (
                <p className="field-hint">
                  {planDialogPlan.max_devices === 1
                    ? "1 dispositivo"
                    : `${planDialogPlan.max_devices} dispositivos`}{" "}
                  · hasta {planDialogPlan.max_resolution} · {planDialogPlan.max_fps} fps ·{" "}
                  {planDialogPlan.monthly_hours === null
                    ? "horas ilimitadas (uso justo)"
                    : `${planDialogPlan.monthly_hours} horas al mes`}
                </p>
              )}
            </div>

            <div className="field">
              <label className="label" htmlFor="assign-expires">
                Vencimiento (opcional)
              </label>
              <input
                id="assign-expires"
                className="input"
                type="date"
                min={todayInputValue()}
                value={planDialog.expiresAt}
                onChange={(event) =>
                  setPlanDialog({ ...planDialog, expiresAt: event.target.value })
                }
              />
              <p className="field-hint">
                Déjalo vacío para un plan sin vencimiento. Al vencer, la cuenta baja
                automáticamente al plan gratuito.
              </p>
            </div>

            <div className="field">
              <label className="label" htmlFor="assign-note">
                Nota (opcional)
              </label>
              <input
                id="assign-note"
                className="input"
                type="text"
                maxLength={500}
                placeholder="Ej.: cortesía por soporte"
                value={planDialog.note}
                onChange={(event) => setPlanDialog({ ...planDialog, note: event.target.value })}
              />
              <p className="field-hint">Queda registrada en el historial de asignaciones.</p>
            </div>

            {planDialogError !== null && (
              <p className="form-error" role="alert">
                {planDialogError}
              </p>
            )}

            <div className="modal-footer">
              <button type="button" className="btn btn-ghost" onClick={() => setPlanDialog(null)}>
                Cancelar
              </button>
              <button type="submit" className="btn btn-primary" disabled={assigning}>
                {assigning ? "Asignando…" : "Asignar"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleteDialog !== null && (
        <Modal title="Eliminar cuenta" onClose={() => setDeleteDialog(null)}>
          <form onSubmit={(event) => void handleDelete(event)}>
            <p className="danger-text">
              Esta acción elimina la cuenta de <strong>{deleteDialog.email}</strong> junto con sus
              dispositivos y su historial. No se puede deshacer.
            </p>
            <div className="field">
              <label className="label" htmlFor="delete-confirm">
                Escribe el correo para confirmar
              </label>
              <input
                id="delete-confirm"
                className="input"
                type="text"
                autoComplete="off"
                autoFocus
                placeholder={deleteDialog.email}
                value={deleteConfirm}
                onChange={(event) => setDeleteConfirm(event.target.value)}
              />
            </div>
            {deleteError !== null && (
              <p className="form-error" role="alert">
                {deleteError}
              </p>
            )}
            <div className="modal-footer">
              <button type="button" className="btn btn-ghost" onClick={() => setDeleteDialog(null)}>
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn-danger"
                disabled={
                  deleting ||
                  deleteConfirm.trim().toLowerCase() !== deleteDialog.email.toLowerCase()
                }
              >
                {deleting ? "Eliminando…" : "Eliminar cuenta"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {grantsDialog !== null && (
        <Modal
          title={`Historial de ${grantsDialog.user.email}`}
          onClose={() => setGrantsDialog(null)}
        >
          {grantsDialog.error !== null && <ErrorNotice message={grantsDialog.error} />}
          {grantsDialog.error === null && grantsDialog.grants === null && (
            <Loader text="Cargando historial…" />
          )}
          {grantsDialog.grants !== null && grantsDialog.grants.length === 0 && (
            <p className="muted">
              Esta cuenta todavía no tiene asignaciones de plan registradas: conserva el plan con
              el que se registró.
            </p>
          )}
          {grantsDialog.grants !== null && grantsDialog.grants.length > 0 && (
            <ul className="grant-list">
              {grantsDialog.grants.map((grant) => (
                <li key={grant.id} className="grant-item">
                  <div className="grant-head">
                    <span>{grant.plan_name}</span>
                    <span className="cell-note">{formatDate(grant.created_at)}</span>
                  </div>
                  <p className="grant-meta">
                    {planSourceLabel(grant.source)}
                    {grant.granted_by_email !== null ? ` · por ${grant.granted_by_email}` : ""} ·{" "}
                    {expiryLabel(grant.expires_at)}
                  </p>
                  {grant.note !== null && <p className="grant-note">“{grant.note}”</p>}
                </li>
              ))}
            </ul>
          )}
          <div className="modal-footer">
            <button type="button" className="btn btn-ghost" onClick={() => setGrantsDialog(null)}>
              Cerrar
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
