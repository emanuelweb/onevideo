import type {
  AdminPlanAssign,
  AdminStats,
  AdminUser,
  AdminUserList,
  AdminUserUpdate,
  AuthResponse,
  CommandResult,
  CommandType,
  Device,
  DeviceSettings,
  DeviceWithPairing,
  PairingCodeInfo,
  PlanGrant,
  PlanPublic,
  StreamInfo,
  Usage,
  User,
} from "./types";

const API_URL: string = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
const API_BASE = `${API_URL}/api/v1`;
const TOKEN_STORAGE_KEY = "onevideo.token";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Ocurrió un error inesperado. Intenta de nuevo.";
}

/** URL del WebSocket de consola derivada de VITE_API_URL (§5 del contrato). */
export function consoleWsUrl(token: string): string {
  const url = new URL(API_URL !== "" ? API_URL : window.location.origin);
  url.protocol = url.protocol === "http:" ? "ws:" : "wss:";
  url.pathname = "/api/v1/console/ws";
  url.search = `token=${encodeURIComponent(token)}`;
  return url.toString();
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = auth ? getToken() : null;
  if (token !== null) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.");
  }

  if (response.status === 401 && token !== null) {
    clearToken();
    window.location.assign("/login");
    throw new ApiError(401, "Tu sesión expiró. Inicia sesión de nuevo.");
  }

  if (!response.ok) {
    let detail = "Ocurrió un error inesperado. Intenta de nuevo.";
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string" && data.detail !== "") detail = data.detail;
    } catch {
      // respuesta sin cuerpo JSON: se conserva el mensaje genérico
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as unknown as T;
  return (await response.json()) as T;
}

/** Arma el query string omitiendo los parámetros vacíos. */
function buildQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    query.set(key, String(value));
  }
  const serialized = query.toString();
  return serialized === "" ? "" : `?${serialized}`;
}

export const api = {
  // Auth
  register: (data: { email: string; password: string; name: string }) =>
    request<AuthResponse>("/auth/register", { method: "POST", body: data, auth: false }),
  login: (data: { email: string; password: string }) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: data, auth: false }),
  me: () => request<User>("/auth/me"),

  // Planes y uso
  plans: () => request<PlanPublic[]>("/plans", { auth: false }),
  usage: () => request<Usage>("/usage"),

  // Dispositivos
  devices: () => request<Device[]>("/devices"),
  createDevice: (name: string) =>
    request<DeviceWithPairing>("/devices", { method: "POST", body: { name } }),
  device: (id: string) => request<Device>(`/devices/${id}`),
  updateDevice: (id: string, data: { name?: string; settings?: Partial<DeviceSettings> }) =>
    request<Device>(`/devices/${id}`, { method: "PATCH", body: data }),
  deleteDevice: (id: string) => request<void>(`/devices/${id}`, { method: "DELETE" }),
  regeneratePairingCode: (id: string) =>
    request<PairingCodeInfo>(`/devices/${id}/pairing-code`, { method: "POST" }),
  sendCommand: (id: string, type: CommandType, payload?: Record<string, unknown>) =>
    request<CommandResult>(`/devices/${id}/commands`, {
      method: "POST",
      body: payload !== undefined ? { type, payload } : { type },
    }),
  streamInfo: (id: string) => request<StreamInfo>(`/devices/${id}/stream`),
  rotateViewToken: (id: string) =>
    request<StreamInfo>(`/devices/${id}/view-token/rotate`, { method: "POST" }),

  // Administración (requiere is_superadmin)
  adminStats: () => request<AdminStats>("/admin/stats"),
  adminUsers: (params: { search?: string; limit?: number; offset?: number } = {}) =>
    request<AdminUserList>(`/admin/users${buildQuery({ ...params })}`),
  adminUser: (id: string) => request<AdminUser>(`/admin/users/${id}`),
  adminAssignPlan: (id: string, data: AdminPlanAssign) =>
    request<AdminUser>(`/admin/users/${id}/plan`, { method: "POST", body: data }),
  adminUpdateUser: (id: string, data: AdminUserUpdate) =>
    request<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: data }),
  adminDeleteUser: (id: string) => request<void>(`/admin/users/${id}`, { method: "DELETE" }),
  adminUserGrants: (id: string) => request<PlanGrant[]>(`/admin/users/${id}/grants`),
};
