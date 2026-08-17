import { formatTime } from "../lib/format";

export function PairingCodeView({ code, expiresAt }: { code: string; expiresAt: string }) {
  return (
    <div className="pairing-block">
      <p className="pairing-hint">Ingresa este código en la app OneVideo de tu celular Android:</p>
      <div className="pairing-code" aria-label={`Código de emparejamiento ${code}`}>
        {code.split("").map((char, index) => (
          <span key={index} className="pairing-char">
            {char}
          </span>
        ))}
      </div>
      <p className="pairing-expiry">Válido hasta las {formatTime(expiresAt)} · un solo uso</p>
    </div>
  );
}
