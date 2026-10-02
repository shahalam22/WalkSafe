// The rear camera, and the two copies of each frame the page needs: a small
// greyscale one for the checks on the phone and a 518 px JPEG for the server.

// Every frame time and every comparison with it uses this one clock (FR-17).
export const clockMs = () => performance.timeOrigin + performance.now();

export async function openCamera(video) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
  });
  video.srcObject = stream;
  await video.play();
  return stream;
}

export function closeCamera(stream) {
  stream?.getTracks().forEach((t) => t.stop());
}

export class FrameGrabber {
  constructor(video, cfg) {
    this.video = video;
    this.cfg = cfg;
    this.small = new OffscreenCanvas(cfg.analysis_width, cfg.analysis_height);
    this.smallCtx = this.small.getContext("2d", { willReadFrequently: true });
    this.upload = new OffscreenCanvas(cfg.upload_width, 1);
    this.uploadCtx = this.upload.getContext("2d");
  }

  ready() {
    return this.video.readyState >= 2 && this.video.videoWidth > 0;
  }

  gray() {
    const { analysis_width: w, analysis_height: h } = this.cfg;
    const ts = clockMs();
    this.smallCtx.drawImage(this.video, 0, 0, w, h);
    const rgba = this.smallCtx.getImageData(0, 0, w, h).data;
    const data = new Uint8Array(w * h);
    for (let i = 0; i < data.length; i++) {
      data[i] = (rgba[4 * i] * 77 + rgba[4 * i + 1] * 150 + rgba[4 * i + 2] * 29) >> 8;
    }
    return { data, width: w, height: h, ts };
  }

  async jpeg() {
    const { videoWidth: vw, videoHeight: vh } = this.video;
    const w = this.cfg.upload_width;
    const h = Math.round((vh * w) / vw);
    if (this.upload.height !== h) this.upload.height = h;
    const ts = clockMs();
    this.uploadCtx.drawImage(this.video, 0, 0, w, h);      // never mirrored
    const blob = await this.upload.convertToBlob({ type: "image/jpeg", quality: this.cfg.jpeg_quality });
    return { blob, ts };
  }
}
