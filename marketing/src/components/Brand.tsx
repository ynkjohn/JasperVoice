import React from "react";
import { AbsoluteFill, interpolate, spring, Easing, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, mono, sans } from "../theme";
import { Logo } from "./Logo";

export const BrandIntro: React.FC<{ tagline?: string }> = ({
  tagline = "Hold. Speak. Done.",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pop = spring({ frame, fps, config: { damping: 14, mass: 0.8 } });
  const logoScale = interpolate(pop, [0, 1], [0.5, 1]);
  const glow = interpolate(frame, [0, 30], [0, 30], { extrapolateRight: "clamp" });

  const wordIn = interpolate(frame, [12, 34], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const tagIn = interpolate(frame, [22, 46], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const spacing = interpolate(wordIn, [0, 1], [18, 8]);

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 28 }}>
        <div style={{ transform: `scale(${logoScale})` }}>
          <Logo size={160} glow={glow} />
        </div>
        <div
          style={{
            fontFamily: mono,
            fontSize: 64,
            fontWeight: 700,
            color: COLORS.fg,
            letterSpacing: spacing,
            opacity: wordIn,
            transform: `translateY(${(1 - wordIn) * 16}px)`,
          }}
        >
          JASPER<span style={{ color: COLORS.accent }}>VOICE</span>
        </div>
        <div
          style={{
            fontFamily: sans,
            fontSize: 24,
            color: COLORS.fgMuted,
            opacity: tagIn,
            transform: `translateY(${(1 - tagIn) * 12}px)`,
            letterSpacing: 0.5,
          }}
        >
          {tagline}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const BrandOutro: React.FC<{ headline?: string }> = ({
  headline = "Your voice. Your machine. Nothing leaves.",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 16, mass: 0.7 } });
  const logoScale = interpolate(pop, [0, 1], [0.7, 1]);

  const headIn = interpolate(frame, [10, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const pillsIn = interpolate(frame, [24, 46], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const repoIn = interpolate(frame, [38, 58], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const tags = ["Private", "Offline", "GPU-accelerated", "Instant"];

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
        <div style={{ transform: `scale(${logoScale})`, display: "flex", alignItems: "center", gap: 18 }}>
          <Logo size={84} glow={18} />
          <div
            style={{
              fontFamily: mono,
              fontSize: 46,
              fontWeight: 700,
              color: COLORS.fg,
              letterSpacing: 4,
            }}
          >
            JASPER<span style={{ color: COLORS.accent }}>VOICE</span>
          </div>
        </div>
        <div
          style={{
            fontFamily: sans,
            fontSize: 34,
            fontWeight: 600,
            color: COLORS.fg,
            opacity: headIn,
            transform: `translateY(${(1 - headIn) * 14}px)`,
            textAlign: "center",
            maxWidth: 900,
            letterSpacing: -0.5,
          }}
        >
          {headline}
        </div>
        <div style={{ display: "flex", gap: 12, opacity: pillsIn }}>
          {tags.map((t) => (
            <div
              key={t}
              style={{
                fontFamily: mono,
                fontSize: 15,
                color: COLORS.accent,
                border: `1px solid ${COLORS.border}`,
                background: COLORS.bgAlt,
                borderRadius: 999,
                padding: "8px 18px",
                letterSpacing: 1,
              }}
            >
              {t}
            </div>
          ))}
        </div>
        <div
          style={{
            fontFamily: mono,
            fontSize: 18,
            color: COLORS.fgMuted,
            opacity: repoIn,
            marginTop: 6,
          }}
        >
          github.com/ynkjohn/JasperVoice
        </div>
      </div>
    </AbsoluteFill>
  );
};
