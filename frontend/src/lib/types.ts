// Tipos espejados del contrato técnico (docs/CONTRACT.md §4)

export type DeviceStatus = "online" | "offline" | "streaming";
export type Resolution = "720p" | "1080p";
export type Fps = 30 | 60;

export interface PlanPublic {
  code: string;
  name: string;
  price_usd_month: number | string;
  max_devices: number;
  max_resolution: string;
  max_fps: number;
  monthly_hours: number | null;
  max_recording_gb: number;
  features: string[];
}

export interface User {
  id: string;
  email: string;
  name: string;
  plan: PlanPublic;
  is_superadmin: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

// El backend (backend/app/schemas/device.py) acepta telemetría parcial:
// todos los campos pueden llegar como null. La UI debe renderizar con fallback.
export interface DeviceTelemetry {
  battery: number | null;
  temp_c: number | null;
  charging: boolean | null;
  network: string | null;
  bitrate_kbps: number | null;
  resolution: string | null;
  facing: string | null;
}

export interface DeviceSettings {
  resolution: Resolution;
  fps: Fps;
  bitrate_kbps: number;
  facing: string;
}

export interface Device {
  id: string;
  name: string;
  platform: string | null;
  model: string | null;
  status: DeviceStatus;
  camera_on: boolean;
  recording_on: boolean;
  last_seen_at: string | null;
  created_at: string;
  telemetry: DeviceTelemetry | null;
  settings: DeviceSettings;
}

export interface DeviceWithPairing extends Device {
  pairing_code: string;
  pairing_expires_at: string;
}

export interface PairingCodeInfo {
  code: string;
  expires_at: string;
}

export interface StreamInfo {
  whip_url: string;
  whep_url: string;
  player_url: string;
  view_token: string;
}

export type CommandType =
  | "camera_on"
  | "camera_off"
  | "switch_camera"
  | "set_quality"
  | "torch_on"
  | "torch_off"
  | "restart_stream";

export interface CommandResult {
  delivered: boolean;
  command_id: string;
}

// ---------- Grabación en la nube (docs/CONTRACT.md, sección Grabaciones) ----------

export interface Recording {
  /** filename en base64url sin padding; se usa como `rid` en las rutas. */
  id: string;
  filename: string;
  started_at: string | null;
  size_bytes: number;
  in_progress: boolean;
}

export interface RecordingList {
  items: Recording[];
  /** Bytes usados por TODAS las grabaciones del usuario (límite por plan, no por device). */
  used_bytes: number;
  limit_bytes: number;
}

export interface DownloadToken {
  url: string;
  expires_at: string;
}

export interface Usage {
  period_start: string;
  period_end: string;
  hours_used: number;
  hours_limit: number | null;
  devices_used: number;
  devices_limit: number;
}

// ---------- Administración (docs/CONTRACT.md §4, backend/app/schemas/admin.py) ----------

/** Quién otorgó el plan activo. Hoy lo escribe el admin; mañana una pasarela de pago. */
export type PlanSource = "signup" | "admin" | "stripe" | "mercadopago";

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  is_superadmin: boolean;
  created_at: string;
  plan: PlanPublic;
  plan_source: PlanSource;
  plan_expires_at: string | null;
  devices_count: number;
  hours_used_month: number;
}

export interface AdminUserList {
  total: number;
  items: AdminUser[];
}

export interface AdminPlanCount {
  plan_code: string;
  plan_name: string;
  count: number;
}

export interface AdminStats {
  users_total: number;
  users_active: number;
  devices_total: number;
  devices_streaming: number;
  hours_this_month: number;
  users_by_plan: AdminPlanCount[];
}

export interface PlanGrant {
  id: number;
  plan_code: string;
  plan_name: string;
  source: PlanSource;
  granted_by_email: string | null;
  expires_at: string | null;
  note: string | null;
  created_at: string;
}

export interface AdminPlanAssign {
  plan_code: string;
  /** null o ausente = plan sin vencimiento. */
  expires_at?: string | null;
  note?: string | null;
}

export interface AdminUserUpdate {
  is_active?: boolean;
  is_superadmin?: boolean;
}
