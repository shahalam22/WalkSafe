// Is a frame usable (FR-1)? Same checks as walksafe/interpretation/quality.py,
// run on the small greyscale copy the phone already makes.

export function brightness(gray) {
  let sum = 0;
  for (const v of gray) sum += v;
  return sum / gray.length;
}

// Variance of the 4-neighbour Laplacian, as cv2.Laplacian computes it.
export function sharpness(gray, width, height) {
  let sum = 0, sq = 0, n = 0;
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const i = y * width + x;
      const lap = gray[i - width] + gray[i + width] + gray[i - 1] + gray[i + 1] - 4 * gray[i];
      sum += lap; sq += lap * lap; n++;
    }
  }
  const mean = sum / n;
  return sq / n - mean * mean;
}

export function checkFrame(gray, width, height, cfg) {
  const b = brightness(gray);
  let cause = "";
  if (b < cfg.dark_max) cause = "dark";
  else if (b > cfg.bright_min) cause = "bright";
  else if (sharpness(gray, width, height) < cfg.blur_min) cause = "blur";
  return { ok: cause === "", cause, brightness: b };
}
