import { Link } from "react-router-dom";

const STREAM_URL: string = import.meta.env.VITE_STREAM_URL || "https://stream.tu-dominio.com";

export default function ObsGuidePage() {
  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Guía: tu celular en OBS</h1>
          <p className="page-subtitle">
            En menos de 5 minutos tendrás la cámara de tu celular como una fuente más de tu escena,
            lista para Kick, Twitch o YouTube.
          </p>
        </div>
      </div>

      <div className="guide-steps">
        <section className="card guide-step">
          <div className="step-number">1</div>
          <div className="step-body">
            <h2 className="section-title">Copia la URL del player</h2>
            <p>
              Entra a <Link to="/app">tus dispositivos</Link>, abre el dispositivo que quieres usar
              y en la sección <strong>Usar en OBS</strong> toca <strong>Copiar URL</strong> junto a
              “URL del player (Browser Source)”. La URL tiene esta forma:
            </p>
            <code className="url-code block">
              {STREAM_URL}/live/&lt;id-del-dispositivo&gt;?token=&lt;token-de-vista&gt;
            </code>
            <p className="muted small">
              El token de vista es privado: cualquiera con la URL puede ver tu cámara. Si lo
              compartiste por error, usa “Rotar token de vista” y copia la URL nueva.
            </p>
          </div>
        </section>

        <section className="card guide-step">
          <div className="step-number">2</div>
          <div className="step-body">
            <h2 className="section-title">Agrega una fuente de navegador en OBS</h2>
            <ol>
              <li>
                En el panel <strong>Fuentes</strong>, haz clic en <strong>+</strong> y elige{" "}
                <strong>Navegador</strong> (Browser Source).
              </li>
              <li>Ponle un nombre, por ejemplo “Cámara celular”.</li>
              <li>
                Pega la URL del player en el campo <strong>URL</strong>.
              </li>
              <li>
                Ancho <strong>1920</strong> y alto <strong>1080</strong> (o 1280 × 720 si tu plan es
                720p).
              </li>
              <li>Acepta con OK: el vídeo aparece en segundos.</li>
            </ol>
            <p className="muted small">
              Tip: desactiva “Apagar la fuente cuando no esté visible” para evitar reconexiones al
              cambiar de escena.
            </p>
          </div>
        </section>

        <section className="card guide-step">
          <div className="step-number">3</div>
          <div className="step-body">
            <h2 className="section-title">Ajusta el lienzo de tu escena</h2>
            <ul>
              <li>
                En OBS ve a <strong>Ajustes → Vídeo</strong> y usa una resolución de lienzo de{" "}
                <strong>1920 × 1080</strong> para streams horizontales.
              </li>
              <li>
                Para recortar la imagen del celular, mantén presionada la tecla{" "}
                <strong>Alt</strong> y arrastra los bordes de la fuente.
              </li>
              <li>
                ¿Contenido vertical (IRL, just chatting con cámara vertical)? Gira el celular y usa
                la fuente centrada con fondos laterales, o un lienzo 1080 × 1920 si transmites solo
                en vertical.
              </li>
            </ul>
          </div>
        </section>

        <section className="card guide-step">
          <div className="step-number">4</div>
          <div className="step-body">
            <h2 className="section-title">Configura tu salida para Kick o Twitch</h2>
            <ul>
              <li>
                <strong>Kick:</strong> acepta hasta 1080p60; un bitrate de salida de 6000 a 8000
                kbps funciona muy bien.
              </li>
              <li>
                <strong>Twitch:</strong> usa hasta 6000 kbps; 1080p60 con codificador por hardware
                (NVENC/AMF) es la opción más estable.
              </li>
              <li>Intervalo de fotogramas clave (keyframe): 2 segundos en ambos casos.</li>
              <li>
                La calidad de la cámara del celular se controla desde OneVideo (resolución y fps
                según tu plan); la calidad del stream final la define OBS.
              </li>
            </ul>
          </div>
        </section>

        <section className="card guide-step">
          <div className="step-number">5</div>
          <div className="step-body">
            <h2 className="section-title">Solución de problemas</h2>
            <ul>
              <li>
                <strong>Pantalla negra:</strong> verifica que el dispositivo aparezca como
                “Transmitiendo” en el panel y que la cámara esté encendida.
              </li>
              <li>
                <strong>La URL dejó de funcionar:</strong> probablemente rotaste el token de vista.
                Copia la URL nueva desde la página del dispositivo y actualízala en OBS.
              </li>
              <li>
                <strong>Vídeo entrecortado:</strong> revisa la red del celular (ideal Wi-Fi 5 GHz o
                5G) y baja la calidad a 720p30 desde los controles remotos.
              </li>
              <li>
                <strong>Latencia:</strong> OneVideo usa WebRTC, con retraso típico menor a un
                segundo; no necesitas ajustar nada.
              </li>
            </ul>
          </div>
        </section>
      </div>
    </>
  );
}
