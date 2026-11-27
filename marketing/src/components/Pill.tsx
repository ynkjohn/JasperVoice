import React, { useEffect, useRef } from "react";
import { interpolate, Easing } from "remotion";
import { STATE, PillState, sans } from "../theme";

// Geometry mirrored from overlay.py (PILL_* / BAR_* constants).
const IDLE_SIZE = 44;
const EXPANDED_W = 168;
const EXPANDED_H = 44;
const NUM_BANDS = 5;
const BAR_W = 3;
const BAR_GAP = 2;
const BAR_MAX = 18;
const BAR_MIN = 2;

// Synthesise plausible per-band "FFT" levels so the spectrum looks like real
// speech without needing an audio file. Deterministic per (band, time).
function bandLevel(i: number, t: number): number {
  const p = (i / NUM_BANDS) * Math.PI * 2;
  const env = 0.55 + 0.45 * Math.sin(t * 2.1 + i * 0.7); // syllable envelope
  const fast = Math.sin(t * 17 + p * 3) * 0.5 + 0.5;
  const mid = Math.sin(t * 9.3 + p) * 0.5 + 0.5;
  const lowBoost = 1 - i * 0.08; // lower bands a touch hotter
  return Math.min(1, Math.max(0.05, env * (0.35 + 0.4 * fast + 0.3 * mid) * lowBoost));
}

function barHeight(state: PillState, i: number, t: number): number {
  const p = (i / NUM_BANDS) * Math.PI * 2;
  if (state === "recording") {
    const level = bandLevel(i, t);
    const shimmer = (Math.sin(t * 6 + p) * 0.5 + 0.5) * 0.12;
    const amp = Math.min(1, level + shimmer);
    return BAR_MIN + amp * (BAR_MAX - BAR_MIN);
  }
  if (state === "processing") {
    return BAR_MIN + (Math.sin(t * 1.6 + p) * 0.5 + 0.5) * (BAR_MAX - BAR_MIN) * 0.52;
  }
  if (state === "send") {
    const d = Math.max(0, 1 - t * 3);
    return BAR_MIN + d * (BAR_MAX - BAR_MIN) * (0.7 + Math.abs(Math.sin(p * 2.5)) * 0.3);
  }
  return BAR_MIN;
}

export const Pill: React.FC<{
  state: PillState;
  /** frames since this state's animation began */
  localFrame: number;
  fps: number;
  /** uniform scale applied for cinematic zoom */
  scale?: number;
}> = ({ state, localFrame, fps, scale = 1 }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const colors = STATE[state];
  const expanded = state !== "idle";
  const t = localFrame / fps;

  // Pill expansion (OutBack-ish) over ~0.4s, mirroring EXPAND_DURATION_MS.
  const expandP = interpolate(localFrame, [0, fps * 0.4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.34, 1.56, 0.64, 1),
  });
  const width = expanded ? IDLE_SIZE + (EXPANDED_W - IDLE_SIZE) * expandP : IDLE_SIZE;
  const height = EXPANDED_H;

  const DPR = 3;
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const cy = height / 2;
    const padLeft = 12;
    const dotR = 3.5;
    const dotX = padLeft;

    // status dot
    ctx.fillStyle = colors.dot;
    ctx.beginPath();
    ctx.arc(dotX, cy, dotR, 0, Math.PI * 2);
    ctx.fill();

    // spectrum bars (only meaningful once partly expanded)
    if (expanded) {
      const barsX = dotX + dotR * 2 + 7;
      ctx.fillStyle = colors.dot;
      for (let i = 0; i < NUM_BANDS; i++) {
        const h = barHeight(state, i, t) * (0.3 + 0.7 * expandP);
        const x = barsX + i * (BAR_W + BAR_GAP);
        const y = cy - h / 2;
        const r = 1;
        // rounded rect
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + BAR_W, y, x + BAR_W, y + h, r);
        ctx.arcTo(x + BAR_W, y + h, x, y + h, r);
        ctx.arcTo(x, y + h, x, y, r);
        ctx.arcTo(x, y, x + BAR_W, y, r);
        ctx.fill();
      }
    }
  }, [state, t, width, height, expanded, expandP, colors.dot]);

  return (
    <div
      style={{
        transform: `scale(${scale})`,
        transformOrigin: "center center",
        width,
        height,
        position: "relative",
      }}
    >
      <div
        style={{
          width,
          height,
          borderRadius: height / 2,
          background: colors.fill,
          border: `1px solid ${colors.border}`,
          boxShadow: expanded
            ? `0 0 24px ${colors.dot}33, 0 8px 30px rgba(0,0,0,0.55)`
            : "0 4px 14px rgba(0,0,0,0.5)",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {state === "idle" ? (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              width: 9,
              height: 9,
              borderRadius: 9,
              background: colors.dot,
              transform: "translate(-50%,-50%)",
            }}
          />
        ) : (
          <canvas
            ref={canvasRef}
            width={width * DPR}
            height={height * DPR}
            style={{ width, height, position: "absolute", top: 0, left: 0 }}
          />
        )}
        {expanded && colors.label ? (
          <div
            style={{
              position: "absolute",
              top: 0,
              height,
              left:
                12 + 3.5 * 2 + 7 + NUM_BANDS * (BAR_W + BAR_GAP) + 6,
              display: "flex",
              alignItems: "center",
              color: colors.text,
              fontFamily: sans,
              fontSize: 11,
              opacity: expandP,
              whiteSpace: "nowrap",
            }}
          >
            {colors.label}
          </div>
        ) : null}
      </div>
    </div>
  );
};
