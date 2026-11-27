import React from "react";
import { interpolate, Easing } from "remotion";
import { COLORS, mono, sans } from "../theme";

// A kinetic lower-third caption: a mono kicker + a large sans headline that
// rises and fades. `local` is frames since the caption appeared.
export const Caption: React.FC<{
  kicker?: string;
  title: string;
  local: number;
  fps: number;
  hold: number; // frames visible before fading out
  align?: "center" | "left";
  y?: number;
}> = ({ kicker, title, local, fps, hold, align = "center", y = 0 }) => {
  const inP = interpolate(local, [0, fps * 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const outP = interpolate(local, [hold, hold + fps * 0.4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = inP * (1 - outP);
  const ty = (1 - inP) * 26 + outP * -14 + y;

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${ty}px)`,
        textAlign: align,
        display: "flex",
        flexDirection: "column",
        alignItems: align === "center" ? "center" : "flex-start",
        gap: 12,
      }}
    >
      {kicker ? (
        <span
          style={{
            fontFamily: mono,
            fontSize: 16,
            letterSpacing: 4,
            textTransform: "uppercase",
            color: COLORS.accent,
            fontWeight: 700,
          }}
        >
          {kicker}
        </span>
      ) : null}
      <span
        style={{
          fontFamily: sans,
          fontSize: 60,
          fontWeight: 700,
          color: COLORS.fg,
          letterSpacing: -1,
          lineHeight: 1.05,
        }}
      >
        {title}
      </span>
    </div>
  );
};
