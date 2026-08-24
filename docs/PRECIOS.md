# OneVideo — Estructura de precios

> Los planes, límites y precios canónicos viven en [CONTRACT.md](./CONTRACT.md) §6 (seed de
> la tabla `plans`). Este documento explica el porqué y la economía detrás.

## 1. Planes

| Plan | Precio | Dispositivos | Calidad máx. | Horas/mes | Grabación en la nube | Pensado para |
|---|---|---|---|---|---|---|
| **Gratis** (`free`) | USD 0 | 1 | 720p / 30 fps | 15 | 1 GB | probar el producto de verdad, no una demo |
| **Creador** (`creator`) | USD 4.99/mes | 1 | 1080p / 30 fps | 60 | 5 GB | quien streamea 3–4 veces por semana |
| **Pro** (`pro`) | USD 9.99/mes | 2 | 1080p / 60 fps | 150 | 20 GB | streamer regular con segunda cámara |
| **Estudio** (`studio`) | USD 19.99/mes | 4 | 1080p / 60 fps | Ilimitadas (uso justo) | 40 GB | multicámara, IRL intensivo, dúos |

- **Anual: −20 %** (Creador 47.90, Pro 95.90, Estudio 191.90 USD/año). El descuento anual
  no es solo retención: cobrar una vez al año reduce el peso de las comisiones fijas de
  pasarela (§6) y el churn involuntario por tarjetas rechazadas, que en LATAM es alto.
- "Uso justo" en Estudio: sin medidor visible, con techo interno de abuso (p. ej. re-stream
  24/7 automatizado) documentado en términos. Si un usuario legítimo lo roza, es señal de
  que necesitamos un plan superior, no de cortarle el servicio.
- **Grabación en la nube**: cuota de almacenamiento **por usuario** (no por dispositivo),
  medida sobre los MP4 guardados; al llegar al límite se apaga la grabación (el usuario
  elimina grabaciones o mejora de plan). Costo: las grabaciones viven en el **disco NVMe
  local del VPS (~100 GB compartidos con el resto del sistema)**, así que la suma de cuotas
  vendidas hay que vigilarla — con los topes actuales, ~10 usuarios Pro consumiendo todo ya
  serían 200 GB teóricos. Mitiga que el uso real suele ser una fracción de la cuota, pero si
  la adopción crece, el paso siguiente es offload a objeto (S3/R2, ~USD 0.015/GB-mes) sin
  cambiar el contrato de la API.

## 2. Por qué tiene sentido en LATAM

La alternativa física a OneVideo para tener una segunda cámara decente en OBS:

| Componente | Costo típico (importado a LATAM) |
|---|---|
| Capturadora HDMI (Elgato o similar) | USD 100–180 |
| Cámara/webcam con calidad comparable a un celular moderno | USD 80–250 |
| Cables, soporte, a veces monitor extra | USD 30–100 |
| **Total, pagado de una vez, con impuestos de importación** | **USD 250–500+** |

Contra eso, OneVideo propone: **el celular que ya tenés en el bolsillo + USD 4.99/mes**.
El celular de gama media de 2022 en adelante tiene mejor sensor que casi cualquier webcam
sub-USD-150. En países con aranceles altos y salarios en moneda local, la diferencia entre
"USD 300 de una vez" y "USD 5 al mes cancelable" no es cosmética: es la diferencia entre
tener segunda cámara o no tenerla.

Precio en USD como referencia, cobrado en moneda local vía MercadoPago donde aplique (§6),
que es como el público de Kick/Twitch en LATAM ya paga sus suscripciones.

## 3. Economía unitaria

### 3.1 La matemática del ancho de banda
El servidor no transcodifica: cada stream entra una vez y sale una vez (el OBS del dueño).
El costo marginal dominante es ancho de banda del VPS, no CPU.

- Stream de 4 Mbps (1080p/30 razonable) ⇒ `4 Mbps ÷ 8 × 3600 s` ≈ **1.8 GB/h de subida**
  al VPS, más ≈ **1.8 GB/h de bajada** hacia el OBS del usuario ⇒ **~3.6 GB/h por stream
  activo** (un lector; el preview del dashboard abierto suma otro lector mientras dure).
- VPS tipo Hostinger KVM: **~8 TB/mes** de transferencia incluida ⇒
  `8 000 GB ÷ 3.6 GB/h` ≈ **~2 200 horas-stream/mes por nodo**.
- Costo del VPS: **USD 10–20/mes** ⇒ costo por hora-stream ≈ **USD 0.005–0.009**
  (medio centavo la hora). A 720p/2 Mbps es la mitad.

### 3.2 Márgenes por plan (VPS a USD 15/mes, ~USD 0.007/hora-stream)

| Plan | Ingreso/mes | Horas | Costo infra si consume TODO | Margen bruto |
|---|---|---|---|---|
| Gratis | 0 | 15 | ~USD 0.10 | costo de adquisición: 10 centavos por usuario/mes |
| Creador | 4.99 | 60 | ~USD 0.41 | ~92 % |
| Pro | 9.99 | 150 | ~USD 1.02 | ~90 % |
| Estudio | 19.99 | uso justo (~250 h p95) | ~USD 1.71 | ~91 % |

Y esto asume consumo del 100 % del límite; en la práctica el uso medio será bastante menor.
Las comisiones de pasarela (§6) restan 4–10 puntos en los planes baratos; aun así el margen
queda holgadamente por encima del 80 %. Con ~35–40 usuarios pagos promedio un solo nodo se
paga solo muchas veces.

Riesgo real a vigilar: la **concurrencia**, no las horas del mes. 2 200 horas-stream caben
en un nodo solo si no ocurren todas a la vez; el pico de streamers LATAM es 19:00–01:00.
Un nodo de 1 Gbps sostiene ~100–150 streams simultáneos a 4+4 Mbps antes de saturar el
puerto. Cuando el pico se acerque, se agrega nodo (ver ARQUITECTURA.md §6) — el margen
del plan pago financia ~600 horas de infra por usuario, sobra espacio.

### 3.3 Por qué el límite es de horas y no de dispositivos
- **Las horas son el costo**: cada hora transmitida es ancho de banda que pagamos. Los
  dispositivos emparejados e inactivos cuestan ~cero (una fila en Postgres y un WS
  ocasional). Cobrar por lo que cuesta alinea el precio con la infraestructura y hace el
  negocio predecible.
- **Las horas segmentan mejor**: un hobbista y un streamer diario pueden tener ambos un
  solo celular; lo que los distingue es cuánto transmiten. El límite de dispositivos
  existe (1/1/2/4) pero como diferenciador de casos de uso (multicámara), no como palanca
  de cobro.
- **Es honesto y verificable**: el usuario ve `hours_used / hours_limit` en `/usage` y en
  el dashboard. Nada de "fair use" opaco en los planes pagos con tope.
- El enforcement ya está en el contrato: el auth hook de publish rechaza (401) cuando el
  plan agotó horas, y la app lo comunica ("Alcanzaste tus horas del mes — mejorá tu plan").

## 4. Pasarelas de pago (fase 3)

| Pasarela | Rol | Nota |
|---|---|---|
| **MercadoPago** | Principal en AR/MX/CL/UY/CO/PE/BR | moneda local, dinero en cuenta MP y tarjetas locales sin tarjeta internacional; comisión ~4–6 % |
| **Stripe** | Internacional + BR/MX nativo | suscripciones sólidas, tarjetas internacionales; ~3.6 % + fijo |
| **Criptomonedas** (USDT/USDC vía procesador tipo BTCPay/Coinbase Commerce) | Opcional | relevante en AR/VE por restricciones cambiarias; sin contracargos |

Regla de diseño para fase 3: el backend trata "suscripción activa" como un dato propio
(`plan_id` + fecha de expiración) alimentado por webhooks de cada pasarela — nunca acoplar
la lógica de límites a una pasarela específica.

En los planes de USD 4.99 la comisión fija pesa (Stripe: ~USD 0.48 ⇒ ~10 %): razón extra
para empujar el plan anual y MercadoPago (comisión porcentual sin fijo alto en varios
países).

## 5. Estrategia de lanzamiento

1. **Beta gratuita con cupo** (fase 1–2): N invitaciones (p. ej. 200) con plan Pro gratis
   mientras dure la beta. Objetivo: probar OEMs reales y estabilidad de sesiones largas,
   no ingresos. El cupo protege el ancho de banda del nodo único.
2. **Precio de fundador** (lanzamiento de fase 3): −30 % de por vida para quienes paguen
   en las primeras semanas (Creador ~3.49, Pro ~6.99). Recompensa a los beta testers,
   crea urgencia y fija una base de ingresos recurrentes temprana. El margen lo permite
   de sobra (§3.2).
3. **Precio pleno** después, sin tocar jamás el precio de los fundadores.
4. El plan Gratis queda para siempre: 15 h reales a 720p es suficiente para engancharse y
   cuesta ~USD 0.10/mes por usuario. Es el marketing más barato que vamos a comprar.
