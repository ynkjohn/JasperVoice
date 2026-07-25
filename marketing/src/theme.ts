// JasperVoice design tokens — mirrored 1:1 from src/jaspervoice/theme.py
// so the marketing video uses the real product palette and typography.

import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { loadFont as loadSans } from "@remotion/google-fonts/Inter";

export const mono = loadMono("normal", {
  weights: ["400", "700"],
  subsets: ["latin"],
  ignoreTooManyRequestsWarning: true,
}).fontFamily;
export const sans = loadSans("normal", {
  weights: ["400", "600", "700"],
  subsets: ["latin"],
  ignoreTooManyRequestsWarning: true,
}).fontFamily;

export const COLORS = {
  bg: "#0F0F0F",
  bgAlt: "#1A1A1A",
  bgHover: "#222222",
  border: "#2A2A2A",
  borderStrong: "#3A3A3A",
  fg: "#E8E6E6",
  fgMuted: "#9E9A9A",
  fgDisabled: "#5A5A5A",
  accent: "#D97757",
  accentHover: "#E88766",
  danger: "#D14E5A",
  warning: "#B8893E",
  sidebar: "#0A0A0A",
} as const;

// Overlay pill state colors — from STATE_COLORS in theme.py.
export const STATE = {
  idle: { border: "#333340", fill: "#1c1c22", dot: "#555555", text: "rgba(255,255,255,0.45)", label: "" },
  recording: { border: "#ef4444", fill: "#1c1c22", dot: "#ef4444", text: "#ff6e6e", label: "Listening..." },
  processing: { border: "#f59e0b", fill: "#1c1c22", dot: "#f59e0b", text: "#f59e0b", label: "Processing..." },
  send: { border: "#22c55e", fill: "#1c1c22", dot: "#22c55e", text: "#4ade80", label: "Sent!" },
} as const;

export type PillState = keyof typeof STATE;
