import { consoleWsUrl, getToken } from "./api";
import type { Device } from "./types";

interface ConsoleSocketHandlers {
  onDeviceStatus: (device: Device) => void;
  onConnectionChange?: (connected: boolean) => void;
}

interface ConsoleMessage {
  type?: string;
  payload?: { device?: Device };
}

const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;

/**
 * Cliente del canal de consola (§5): recibe `device_status` en tiempo real
 * y se reconecta con retroceso exponencial si la conexión se pierde.
 */
export class ConsoleSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private reconnectTimer: number | null = null;
  private closed = false;

  constructor(private readonly handlers: ConsoleSocketHandlers) {}

  connect(): void {
    if (this.closed) return;
    const token = getToken();
    if (token === null) return;

    const ws = new WebSocket(consoleWsUrl(token));
    this.ws = ws;

    ws.onopen = () => {
      this.attempts = 0;
      this.handlers.onConnectionChange?.(true);
    };

    ws.onmessage = (event) => {
      let message: ConsoleMessage;
      try {
        message = JSON.parse(event.data as string) as ConsoleMessage;
      } catch {
        return;
      }
      if (message.type === "device_status" && message.payload?.device) {
        this.handlers.onDeviceStatus(message.payload.device);
      }
    };

    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      this.handlers.onConnectionChange?.(false);
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  close(): void {
    this.closed = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  private scheduleReconnect(): void {
    if (this.closed || this.reconnectTimer !== null) return;
    const delay =
      Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** this.attempts) + Math.random() * 500;
    this.attempts += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }
}
