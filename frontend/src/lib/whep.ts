export type WhepState = "connecting" | "connected" | "disconnected" | "failed";

/**
 * Cliente WHEP mínimo: RTCPeerConnection de solo recepción negociada con un
 * POST del offer SDP; el answer llega en el cuerpo de la respuesta (MediaMTX).
 */
export class WhepPlayer {
  private pc: RTCPeerConnection | null = null;

  constructor(private readonly onStateChange?: (state: WhepState) => void) {}

  async play(whepUrl: string, video: HTMLVideoElement): Promise<void> {
    this.stop();
    const pc = new RTCPeerConnection();
    this.pc = pc;
    this.onStateChange?.("connecting");

    const stream = new MediaStream();
    video.srcObject = stream;
    pc.ontrack = (event) => stream.addTrack(event.track);

    pc.onconnectionstatechange = () => {
      if (this.pc !== pc) return;
      switch (pc.connectionState) {
        case "connected":
          this.onStateChange?.("connected");
          break;
        case "failed":
          this.onStateChange?.("failed");
          break;
        case "disconnected":
        case "closed":
          this.onStateChange?.("disconnected");
          break;
      }
    };

    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    await pc.setLocalDescription(await pc.createOffer());
    await waitForIceGathering(pc, 1500);
    if (this.pc !== pc) return; // se detuvo mientras negociaba

    let response: Response;
    try {
      response = await fetch(whepUrl, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: pc.localDescription?.sdp ?? "",
      });
    } catch {
      this.onStateChange?.("failed");
      throw new Error("No se pudo contactar al servidor de streaming.");
    }
    if (!response.ok) {
      this.onStateChange?.("failed");
      throw new Error(`El servidor de streaming respondió ${response.status}.`);
    }

    const answer = await response.text();
    if (this.pc !== pc) return;
    await pc.setRemoteDescription({ type: "answer", sdp: answer });
  }

  stop(): void {
    if (this.pc !== null) {
      this.pc.close();
      this.pc = null;
    }
  }
}

function waitForIceGathering(pc: RTCPeerConnection, timeoutMs: number): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const finish = (): void => {
      window.clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    const check = (): void => {
      if (pc.iceGatheringState === "complete") finish();
    };
    const timer = window.setTimeout(finish, timeoutMs);
    pc.addEventListener("icegatheringstatechange", check);
  });
}
