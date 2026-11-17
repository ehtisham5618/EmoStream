import type { FaceParams } from "./emotions";

/** Frontal 68-ish landmark layout in a 512×512 canvas, driven by expression params. */
export type Pt = [number, number];

const CX = 256;
/** Round so server and browser render identical SVG attributes. */
export const round = (n: number) => Math.round(n * 100) / 100;

function mirror(pts: Pt[]): Pt[] {
  return pts.map(([x, y]) => [2 * CX - x, y]);
}

export function faceLandmarks(p: FaceParams) {
  const jawDrop = Math.max(0, p.mouthOpen) * 14;

  const jaw: Pt[] = [];
  for (let i = 0; i <= 16; i++) {
    const th = Math.PI - (Math.PI * i) / 16;
    const s = Math.sin(th);
    const c = Math.cos(th);
    const narrow = 1 - 0.3 * Math.max(0, s - 0.3) / 0.7;
    jaw.push([CX + 118 * c * narrow, 214 + 194 * s + jawDrop * s * s]);
  }

  const brow = (t: number): Pt => {
    const x = 172 + 64 * t;
    const y = 182 - p.browRaise * 18 - Math.sin(Math.PI * (0.15 + t * 0.85)) * 9 - p.browTilt * 16 * t * t;
    return [x, y];
  };
  const browL: Pt[] = [0, 0.25, 0.5, 0.75, 1].map(brow);
  const browR = mirror(browL);

  const eye = (ex: number): { upper: Pt[]; lower: Pt[]; pupil: Pt } => {
    const w = 46;
    const h = 10 * (1 + p.eyeOpen * 0.9);
    const ey = 218;
    const upper: Pt[] = [0, 0.2, 0.5, 0.8, 1].map((t) => [ex - w / 2 + w * t, ey - h * Math.sin(Math.PI * t)]);
    const lower: Pt[] = [0, 0.3, 0.7, 1].map((t) => [ex - w / 2 + w * t, ey + h * 0.7 * Math.sin(Math.PI * t)]);
    return { upper, lower, pupil: [ex, ey - h * 0.1] };
  };
  const eyeL = eye(206);
  const eyeR = eye(306);

  const noseBridge: Pt[] = [196, 218, 240, 262].map((y) => [CX, y]);
  const noseBase: Pt[] = [
    [236, 282],
    [246, 288],
    [CX, 291],
    [266, 288],
    [276, 282],
  ];

  const mcy = 336;
  const mw = 76 * (1 + p.mouthWidth * 0.55);
  const curve = p.mouthCurve * 14;
  const open = Math.max(0, p.mouthOpen) * 28;
  const ts = [0, 1 / 6, 2 / 6, 0.5, 4 / 6, 5 / 6, 1];
  const base = (t: number) => mcy - curve * (1 - Math.sin(Math.PI * t)) - curve * 0.25;
  const outerUpper: Pt[] = ts.map((t) => {
    const s = Math.sin(Math.PI * t);
    const bow = t > 0.4 && t < 0.6 ? 2.5 : 0;
    return [CX - mw / 2 + mw * t, base(t) - 9 * s - open * 0.18 * s + bow];
  });
  const outerLower: Pt[] = ts.map((t) => {
    const s = Math.sin(Math.PI * t);
    return [CX - mw / 2 + mw * t, base(t) + (11 + open) * s];
  });
  const iw = mw * 0.78;
  const its = [0, 0.25, 0.5, 0.75, 1];
  const innerUpper: Pt[] = its.map((t) => {
    const s = Math.sin(Math.PI * t);
    return [CX - iw / 2 + iw * t, base(0.11 + t * 0.78) - (1.5 + open * 0.12) * s];
  });
  const innerLower: Pt[] = its.map((t) => {
    const s = Math.sin(Math.PI * t);
    return [CX - iw / 2 + iw * t, base(0.11 + t * 0.78) + (1.5 + open * 0.82) * s];
  });

  const R = (pts: Pt[]): Pt[] => pts.map(([x, y]) => [round(x), round(y)]);
  const E = (e: { upper: Pt[]; lower: Pt[]; pupil: Pt }) => ({ upper: R(e.upper), lower: R(e.lower), pupil: [round(e.pupil[0]), round(e.pupil[1])] as Pt });
  return {
    jaw: R(jaw),
    browL: R(browL),
    browR: R(browR),
    eyeL: E(eyeL),
    eyeR: E(eyeR),
    noseBridge: R(noseBridge),
    noseBase: R(noseBase),
    outerUpper: R(outerUpper),
    outerLower: R(outerLower),
    innerUpper: R(innerUpper),
    innerLower: R(innerLower),
  };
}

export const toPath = (pts: Pt[], close = false) =>
  pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ") + (close ? " Z" : "");

/** Smooth path through points (Catmull-Rom → Bézier). */
export function smoothPath(pts: Pt[]) {
  if (pts.length < 2) return "";
  const first = pts[0]!;
  let d = `M${first[0].toFixed(1)} ${first[1].toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p1 = pts[i]!;
    const p2 = pts[i + 1]!;
    const p0 = pts[i - 1] ?? p1;
    const p3 = pts[i + 2] ?? p2;
    const c1: Pt = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: Pt = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d;
}

/** Deterministic pseudo-random speech envelope used by illustrations only. */
export function speechEnvelope(t: number) {
  const syll = Math.max(0, Math.sin(t * 9.1) * 0.6 + Math.sin(t * 5.3 + 1.2) * 0.35 + Math.sin(t * 13.7) * 0.2);
  const phrase = 0.5 + 0.5 * Math.sin(t * 0.9);
  return Math.min(1, syll * (0.35 + phrase * 0.75));
}

export function seededBars(n: number, seed = 7) {
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  return Array.from({ length: n }, (_, i) => {
    const env = speechEnvelope(i * 0.11 + seed);
    return round(Math.max(0.06, Math.min(1, env * 0.85 + rnd() * 0.25)));
  });
}
