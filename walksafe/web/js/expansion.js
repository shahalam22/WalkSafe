// The expansion check (FR-16, NFR-1, NFR-3): is something closing in?
//
// Something approaching grows in the image. On the small greyscale copy, blocks
// on a grid are matched between consecutive frames. The mean motion is removed,
// which takes out the user's sideways motion and rotation, and what is left in
// the centre is fitted as a uniform expansion u = a (x - x0), v = a (y - y0).
// The expansion rate a per frame gives the time to contact, frame interval / a,
// without knowing how far away anything is. No model, no network.

export class ExpansionCheck {
  constructor(cfg) {
    this.cfg = cfg;
    this.prev = null;
    this.prevTs = 0;
    this.below = 0;
    this.above = 0;
    this.stopping = false;
  }

  // Returns { ttc, points, available, stop }. available is false when there is
  // too little texture to measure (a covered camera, a blank wall, darkness).
  update(gray, width, height, ts) {
    const { prev, prevTs } = this;
    this.prev = gray;
    this.prevTs = ts;
    if (!prev || ts - prevTs > this.cfg.expansion_max_gap_ms || ts <= prevTs) {
      return { ttc: null, points: 0, available: true, stop: this.stopping };
    }
    const flow = blockFlow(prev, gray, width, height, this.cfg);
    const inside = flow.filter((p) => inRegion(p, width, height, this.cfg));
    if (inside.length < this.cfg.expansion_min_points) {
      this.below = 0;
      return { ttc: null, points: inside.length, available: false, stop: this.stopping };
    }
    const ttc = timeToContact(inside, (ts - prevTs) / 1000);
    this.track(ttc);
    return { ttc, points: inside.length, available: true, stop: this.stopping };
  }

  track(ttc) {
    const { cfg } = this;
    if (ttc < cfg.ttc_stop_s) { this.below++; this.above = 0; }
    else if (ttc > cfg.ttc_clear_s) { this.above++; this.below = 0; }
    if (!this.stopping && this.below >= cfg.stop_frames) this.stopping = true;
    if (this.stopping && this.above >= cfg.clear_frames) this.stopping = false;
  }
}

export function timeToContact(points, dt) {
  const n = points.length;
  let mx = 0, my = 0, mu = 0, mv = 0;
  for (const p of points) { mx += p.x; my += p.y; mu += p.u; mv += p.v; }
  mx /= n; my /= n; mu /= n; mv /= n;
  let num = 0, den = 0;
  for (const p of points) {
    const dx = p.x - mx, dy = p.y - my;
    num += (p.u - mu) * dx + (p.v - mv) * dy;
    den += dx * dx + dy * dy;
  }
  const rate = num / den;           // fractional growth per frame
  return rate > 0 ? dt / rate : Infinity;
}

function inRegion(p, width, height, cfg) {
  return p.x >= width * cfg.expansion_region_left && p.x <= width * cfg.expansion_region_right
      && p.y >= height * cfg.expansion_region_top && p.y <= height * cfg.expansion_region_bottom;
}

// Motion of textured blocks on a grid, by sum of absolute differences, with a
// parabola through the neighbouring scores for sub-pixel precision.
export function blockFlow(prev, curr, width, height, cfg) {
  const b = cfg.expansion_block_px, r = cfg.expansion_search_px, margin = b + r + 1;
  const points = [];
  for (let y = margin; y < height - margin; y += cfg.expansion_grid_px) {
    for (let x = margin; x < width - margin; x += cfg.expansion_grid_px) {
      if (blockVariance(prev, width, x, y, b) < cfg.expansion_min_texture) continue;
      let best = Infinity, bu = 0, bv = 0;
      const sad = new Float64Array((2 * r + 1) ** 2);
      for (let v = -r; v <= r; v++) {
        for (let u = -r; u <= r; u++) {
          const s = blockSad(prev, curr, width, x, y, u, v, b);
          sad[(v + r) * (2 * r + 1) + (u + r)] = s;
          if (s < best) { best = s; bu = u; bv = v; }
        }
      }
      if (Math.abs(bu) === r || Math.abs(bv) === r) continue;    // may lie outside the search
      const at = (u, v) => sad[(v + r) * (2 * r + 1) + (u + r)];
      points.push({
        x, y,
        u: bu + subpixel(at(bu - 1, bv), best, at(bu + 1, bv)),
        v: bv + subpixel(at(bu, bv - 1), best, at(bu, bv + 1)),
      });
    }
  }
  return points;
}

function subpixel(left, centre, right) {
  const d = left - 2 * centre + right;
  return d > 0 ? (left - right) / (2 * d) : 0;
}

function blockSad(prev, curr, width, x, y, u, v, b) {
  let s = 0;
  for (let dy = -b; dy <= b; dy++) {
    const rowP = (y + dy) * width + x;
    const rowC = (y + dy + v) * width + x + u;
    for (let dx = -b; dx <= b; dx++) s += Math.abs(prev[rowP + dx] - curr[rowC + dx]);
  }
  return s;
}

function blockVariance(gray, width, x, y, b) {
  let sum = 0, sq = 0, n = 0;
  for (let dy = -b; dy <= b; dy++) {
    for (let dx = -b; dx <= b; dx++) {
      const g = gray[(y + dy) * width + x + dx];
      sum += g; sq += g * g; n++;
    }
  }
  return sq / n - (sum / n) ** 2;
}
