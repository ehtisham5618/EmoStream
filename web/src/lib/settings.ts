import { createStore, useStore } from "./store";
import type { EmotionId } from "./emotions";

export type ThemePref = "light" | "dark" | "system";

export interface Settings {
  theme: ThemePref;
  defaultEmotion: EmotionId;
  defaultIntensity: number;
  showCropGuides: boolean;
  showFrameInfo: boolean;
  showTelemetry: boolean;
  /** Base URL of a running EmoStream engine, e.g. http://localhost:8000. Empty = not connected. */
  engineUrl: string;
  micDeviceId: string;
  requireConsent: true;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: "light",
  defaultEmotion: "neutral",
  defaultIntensity: 60,
  showCropGuides: true,
  showFrameInfo: true,
  showTelemetry: true,
  engineUrl: "",
  micDeviceId: "",
  requireConsent: true,
};

const KEY = "emostream.settings.v1";

function load(): Settings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw
      ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw), requireConsent: true }
      : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export const settingsStore = createStore<Settings>(load());

settingsStore.subscribe(() => {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(settingsStore.get()));
  } catch {
    /* storage unavailable */
  }
});

export function useSettings<S>(selector: (s: Settings) => S): S {
  return useStore(settingsStore, selector, DEFAULT_SETTINGS);
}

export const updateSettings = (patch: Partial<Settings>) => settingsStore.set(patch);
export const resetSettings = () => settingsStore.set(DEFAULT_SETTINGS);
