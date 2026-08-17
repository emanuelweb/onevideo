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
  features: string[];
}

export interface User {
  id: string;
  email: string;
  name: string;
  plan: PlanPublic;
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

export interface Usage {
  period_start: string;
  period_end: string;
  hours_used: number;
  hours_limit: number | null;
  devices_used: number;
  devices_limit: number;
}
