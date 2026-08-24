const dateFormatter = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const timeFormatter = new Intl.DateTimeFormat("es", {
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(iso: string): string {
  return dateFormatter.format(new Date(iso));
}

export function formatTime(iso: string): string {
  return timeFormatter.format(new Date(iso));
}

export function formatRelative(iso: string | null): string {
  if (iso === null) return "nunca";
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 0) return "ahora";
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "hace instantes";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "hace 1 hora" : `hace ${hours} horas`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "hace 1 día" : `hace ${days} días`;
}

export function formatHours(hours: number): string {
  let whole = Math.floor(hours);
  let minutes = Math.round((hours - whole) * 60);
  if (minutes === 60) {
    whole += 1;
    minutes = 0;
  }
  return minutes === 0 ? `${whole} h` : `${whole} h ${minutes} min`;
}

/** Bytes → gigabytes con 1 decimal, p. ej. "1.5 GB". */
export function formatGB(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

/** Tamaño de archivo legible: elige la unidad según la magnitud. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return formatGB(bytes);
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export function formatPrice(value: number | string): string {
  const amount = Number(value);
  return amount === 0 ? "Gratis" : `US$ ${amount.toFixed(2)}`;
}

export function facingLabel(facing: string | null | undefined): string {
  if (facing === "front") return "Frontal";
  if (facing === "back" || facing === "rear") return "Trasera";
  return facing != null && facing !== "" ? facing : "—";
}

/** Origen del plan activo: 'signup' | 'admin' | 'stripe' | 'mercadopago'. */
export function planSourceLabel(source: string | null | undefined): string {
  if (source == null || source === "") return "—";
  const labels: Record<string, string> = {
    signup: "Registro",
    admin: "Asignado por administración",
    stripe: "Stripe",
    mercadopago: "MercadoPago",
  };
  return labels[source.toLowerCase()] ?? source;
}

export function networkLabel(network: string | null | undefined): string {
  if (network == null || network === "") return "—";
  const labels: Record<string, string> = {
    wifi: "Wi-Fi",
    cellular: "Datos móviles",
    "3g": "3G",
    "4g": "4G",
    "5g": "5G",
    ethernet: "Ethernet",
  };
  return labels[network.toLowerCase()] ?? network;
}
