/**
 * 1-bit framebuffer with u8g2-style drawing primitives.
 *
 * The simulator renders exactly what a 128×64 SSD1306 OLED would show, pixel for
 * pixel, so the face you design here is the face the ESP32 will display.
 */
export class Framebuffer {
  readonly width: number;
  readonly height: number;
  readonly pixels: Uint8Array;

  constructor(width = 128, height = 64) {
    this.width = width;
    this.height = height;
    this.pixels = new Uint8Array(width * height);
  }

  clear(): void {
    this.pixels.fill(0);
  }

  set(x: number, y: number, color = 1): void {
    x = Math.round(x);
    y = Math.round(y);
    if (x < 0 || y < 0 || x >= this.width || y >= this.height) return;
    this.pixels[y * this.width + x] = color;
  }

  /** Horizontal line starting at (x, y), `len` pixels long (u8g2 drawHLine). */
  hline(x: number, y: number, len: number, color = 1): void {
    for (let i = 0; i < len; i++) this.set(x + i, y, color);
  }

  /** Filled box between two corners (exclusive of the far edge, like esp32-eyes FillRectangle). */
  box(x0: number, y0: number, x1: number, y1: number, color = 1): void {
    const l = Math.round(Math.min(x0, x1));
    const r = Math.round(Math.max(x0, x1));
    const t = Math.round(Math.min(y0, y1));
    const b = Math.round(Math.max(y0, y1));
    for (let y = t; y < b; y++) for (let x = l; x < r; x++) this.set(x, y, color);
  }

  /** Filled triangle (scanline). */
  triangle(x0: number, y0: number, x1: number, y1: number, x2: number, y2: number, color = 1): void {
    const pts = [
      [x0, y0],
      [x1, y1],
      [x2, y2],
    ].sort((a, b) => a[1] - b[1]);
    const [[ax, ay], [bx, by], [cx, cy]] = pts;
    const edge = (ya: number, xa: number, yb: number, xb: number, y: number) =>
      yb === ya ? xa : xa + ((xb - xa) * (y - ya)) / (yb - ya);
    for (let y = Math.round(ay); y <= Math.round(cy); y++) {
      const xl = edge(ay, ax, cy, cx, y);
      const xr = y < by ? edge(ay, ax, by, bx, y) : edge(by, bx, cy, cx, y);
      const from = Math.round(Math.min(xl, xr));
      const to = Math.round(Math.max(xl, xr));
      for (let x = from; x <= to; x++) this.set(x, y, color);
    }
  }

  /** Right triangle used by esp32-eyes for slanted eyelids: (x0,y0) (x1,y1) (x1,y0). */
  rightTriangle(x0: number, y0: number, x1: number, y1: number, color = 1): void {
    this.triangle(x0, y0, x1, y1, x1, y0, color);
  }

  /** Quarter-ellipse fill extending outwards from (x0, y0) — port of esp32-eyes FillEllipseCorner. */
  corner(which: "TL" | "TR" | "BL" | "BR", x0: number, y0: number, r: number, color = 1): void {
    r = Math.round(r);
    if (r < 2) return;
    x0 = Math.round(x0);
    y0 = Math.round(y0);
    const rx2 = r * r;
    const ry2 = r * r;
    const fx2 = 4 * rx2;
    const fy2 = 4 * ry2;
    const line = (x: number, y: number) => {
      if (which === "TR") this.hline(x0, y0 - y, x, color);
      else if (which === "BR") this.hline(x0, y0 + y - 1, x, color);
      else if (which === "TL") this.hline(x0 - x, y0 - y, x, color);
      else this.hline(x0 - x, y0 + y - 1, x, color);
    };
    let x = 0;
    let y = r;
    let s = 2 * ry2 + rx2 * (1 - 2 * r);
    for (; ry2 * x <= rx2 * y; x++) {
      line(x, y);
      if (s >= 0) {
        s += fx2 * (1 - y);
        y--;
      }
      s += ry2 * (4 * x + 6);
    }
    x = r;
    y = 0;
    s = 2 * rx2 + ry2 * (1 - 2 * r);
    for (; rx2 * y <= ry2 * x; y++) {
      line(x, y);
      if (s >= 0) {
        s += fy2 * (1 - x);
        x--;
      }
      s += rx2 * (4 * y + 6);
    }
  }

  ellipse(cx: number, cy: number, rx: number, ry: number, filled = true, color = 1): void {
    if (rx <= 0 || ry <= 0) return;
    for (let y = -Math.ceil(ry); y <= Math.ceil(ry); y++) {
      for (let x = -Math.ceil(rx); x <= Math.ceil(rx); x++) {
        const d = (x * x) / (rx * rx) + (y * y) / (ry * ry);
        if (filled ? d <= 1.0 : d <= 1.0 && d >= Math.max(0, 1 - 2.2 / Math.min(rx, ry))) {
          this.set(cx + x, cy + y, color);
        }
      }
    }
  }

  line(x0: number, y0: number, x1: number, y1: number, color = 1, thickness = 1): void {
    const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0), 1);
    for (let i = 0; i <= steps; i++) {
      const x = x0 + ((x1 - x0) * i) / steps;
      const y = y0 + ((y1 - y0) * i) / steps;
      if (thickness <= 1) this.set(x, y, color);
      else this.box(x - thickness / 2, y - thickness / 2, x + thickness / 2, y + thickness / 2, color);
    }
  }

  /** Polyline through sampled points of f(t), t∈[0,1] — used for arcs and wavy mouths. */
  curve(points: Array<[number, number]>, color = 1, thickness = 2): void {
    for (let i = 1; i < points.length; i++) {
      const [x0, y0] = points[i - 1];
      const [x1, y1] = points[i];
      this.line(x0, y0, x1, y1, color, thickness);
    }
  }

  heart(cx: number, cy: number, size: number, color = 1): void {
    const r = size / 4;
    this.ellipse(cx - r, cy - r / 2, r + 0.4, r + 0.4, true, color);
    this.ellipse(cx + r, cy - r / 2, r + 0.4, r + 0.4, true, color);
    this.triangle(cx - 2 * r - 0.4, cy - r / 4, cx + 2 * r + 0.4, cy - r / 4, cx, cy + size / 2, color);
  }

  /** Tiny 3×5 pixel font for the few glyphs faces need (Z, ?, !, digits, dots). */
  text(str: string, x: number, y: number, scale = 1, color = 1): void {
    let cursor = x;
    for (const ch of str) {
      const glyph = GLYPHS[ch];
      if (glyph) {
        glyph.forEach((row, gy) => {
          for (let gx = 0; gx < 3; gx++) {
            if (row & (4 >> gx)) this.box(cursor + gx * scale, y + gy * scale, cursor + (gx + 1) * scale, y + (gy + 1) * scale, color);
          }
        });
      }
      cursor += 4 * scale;
    }
  }
}

const GLYPHS: Record<string, number[]> = {
  Z: [7, 1, 2, 4, 7],
  z: [0, 7, 2, 4, 7],
  "?": [6, 1, 2, 0, 2],
  "!": [2, 2, 2, 0, 2],
  ".": [0, 0, 0, 0, 2],
  "0": [7, 5, 5, 5, 7],
  "1": [2, 6, 2, 2, 7],
  "2": [7, 1, 7, 4, 7],
  "3": [7, 1, 3, 1, 7],
  "4": [5, 5, 7, 1, 1],
  "5": [7, 4, 7, 1, 7],
  "6": [7, 4, 7, 5, 7],
  "7": [7, 1, 2, 2, 2],
  "8": [7, 5, 7, 5, 7],
  "9": [7, 5, 7, 1, 7],
  ":": [0, 2, 0, 2, 0],
  "%": [5, 1, 2, 4, 5],
};
