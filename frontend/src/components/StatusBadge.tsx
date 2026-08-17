import type { DeviceStatus } from "../lib/types";

const STATUS_LABELS: Record<DeviceStatus, string> = {
  online: "En línea",
  offline: "Desconectado",
  streaming: "Transmitiendo",
};

export function StatusBadge({ status }: { status: DeviceStatus }) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  );
}
