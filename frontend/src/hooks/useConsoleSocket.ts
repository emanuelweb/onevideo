import { useEffect, useRef, useState } from "react";
import { ConsoleSocket } from "../lib/consoleSocket";
import type { Device } from "../lib/types";

/**
 * Mantiene abierta la conexión al WS de consola mientras el componente viva.
 * Devuelve `true` cuando la conexión en vivo está activa.
 */
export function useConsoleSocket(onDeviceStatus: (device: Device) => void): boolean {
  const callbackRef = useRef(onDeviceStatus);
  callbackRef.current = onDeviceStatus;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const socket = new ConsoleSocket({
      onDeviceStatus: (device) => callbackRef.current(device),
      onConnectionChange: setConnected,
    });
    socket.connect();
    return () => socket.close();
  }, []);

  return connected;
}
