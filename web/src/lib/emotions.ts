export type EmotionId = "neutral" | "happy" | "sad" | "angry" | "surprised";

export interface FaceParams {
  browRaise: number;
  browTilt: number;
  eyeOpen: number;
  mouthCurve: number;
  mouthOpen: number;
  mouthWidth: number;
}

export const NEUTRAL_FACE: FaceParams = {
  browRaise: 0,
  browTilt: 0,
  eyeOpen: 0,
  mouthCurve: 0,
  mouthOpen: 0,
  mouthWidth: 0,
};

export interface Emotion {
  id: EmotionId;
  label: string;
  /** Short description of what the expression branch changes. */
  cue: string;
  colorClass: string;
  bgClass: string;
  borderClass: string;
  face: FaceParams;
}

export const EMOTIONS: Emotion[] = [
  {
    id: "neutral",
    label: "Neutral",
    cue: "Relaxed brows, resting mouth",
    colorClass: "text-emo-neutral",
    bgClass: "bg-emo-neutral",
    borderClass: "border-emo-neutral",
    face: NEUTRAL_FACE,
  },
  {
    id: "happy",
    label: "Happy",
    cue: "Lifted cheeks, soft squint, raised corners",
    colorClass: "text-emo-happy",
    bgClass: "bg-emo-happy",
    borderClass: "border-emo-happy",
    face: { browRaise: 0.15, browTilt: 0, eyeOpen: -0.3, mouthCurve: 1, mouthOpen: 0.15, mouthWidth: 0.15 },
  },
  {
    id: "sad",
    label: "Sad",
    cue: "Inner brows up, corners drawn down",
    colorClass: "text-emo-sad",
    bgClass: "bg-emo-sad",
    borderClass: "border-emo-sad",
    face: { browRaise: 0.1, browTilt: 1, eyeOpen: -0.25, mouthCurve: -0.8, mouthOpen: 0, mouthWidth: -0.05 },
  },
  {
    id: "angry",
    label: "Angry",
    cue: "Brows pulled low and together, firm mouth",
    colorClass: "text-emo-angry",
    bgClass: "bg-emo-angry",
    borderClass: "border-emo-angry",
    face: { browRaise: -0.6, browTilt: -1, eyeOpen: -0.05, mouthCurve: -0.35, mouthOpen: 0.05, mouthWidth: -0.15 },
  },
  {
    id: "surprised",
    label: "Surprised",
    cue: "Brows high, eyes wide, jaw released",
    colorClass: "text-emo-surprised",
    bgClass: "bg-emo-surprised",
    borderClass: "border-emo-surprised",
    face: { browRaise: 1, browTilt: 0.1, eyeOpen: 0.7, mouthCurve: 0, mouthOpen: 0.75, mouthWidth: -0.35 },
  },
];

export const emotionById = (id: EmotionId): Emotion => EMOTIONS.find((e) => e.id === id) ?? EMOTIONS[0]!;

/** Blend from neutral toward an emotion by intensity (0–100). */
export function faceFor(id: EmotionId, intensity: number, extra?: Partial<FaceParams>): FaceParams {
  const k = Math.max(0, Math.min(100, intensity)) / 100;
  const t = emotionById(id).face;
  const out = {} as FaceParams;
  (Object.keys(NEUTRAL_FACE) as (keyof FaceParams)[]).forEach((key) => {
    out[key] = t[key] * k + (extra?.[key] ?? 0);
  });
  return out;
}
