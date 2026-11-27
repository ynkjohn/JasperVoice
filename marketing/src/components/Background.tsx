import React, { useEffect, useRef } from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS } from "../theme";

// Canvas-rendered backdrop: deep-black base, a slowly drifting dot grid, and a
// soft accent aurora. Deterministic per frame so it renders identically.
export const Background: React.FC<{ accent?: number }> = ({ accent = 0.5 }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const t = frame / fps;

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, width, height);

    // accent aurora (two drifting radial glows)
    const glow = (cx: number, cy: number, r: number, color: string, a: number) => {
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0, color);
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = a * accent;
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, width, height);
      ctx.globalAlpha = 1;
    };
    glow(
      width * (0.25 + 0.05 * Math.sin(t * 0.4)),
      height * (0.2 + 0.04 * Math.cos(t * 0.3)),
      width * 0.5,
      "rgba(217,119,87,0.16)",
      1,
    );
    glow(
      width * (0.8 + 0.04 * Math.cos(t * 0.5)),
      height * (0.85 + 0.03 * Math.sin(t * 0.45)),
      width * 0.45,
      "rgba(217,119,87,0.10)",
      1,
    );

    // dot grid
    const gap = 46;
    const off = (t * 8) % gap;
    ctx.fillStyle = "rgba(255,255,255,0.035)";
    for (let y = -gap + off; y < height + gap; y += gap) {
      for (let x = -gap + off; x < width + gap; x += gap) {
        ctx.beginPath();
        ctx.arc(x, y, 1.1, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // top + bottom vignette
    const vg = ctx.createLinearGradient(0, 0, 0, height);
    vg.addColorStop(0, "rgba(0,0,0,0.5)");
    vg.addColorStop(0.5, "rgba(0,0,0,0)");
    vg.addColorStop(1, "rgba(0,0,0,0.6)");
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, width, height);
  }, [t, width, height, accent]);

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      <canvas ref={ref} width={width} height={height} style={{ width, height }} />
    </AbsoluteFill>
  );
};
