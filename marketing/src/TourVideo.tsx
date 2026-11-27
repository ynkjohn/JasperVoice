import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Background } from "./components/Background";
import { BrandIntro, BrandOutro } from "./components/Brand";
import { AppWindow } from "./components/AppWindow";
import { Caption } from "./components/Caption";
import { COLORS } from "./theme";

const SEGMENTS = [
  { start: 84, page: "Overview", kicker: "Workspace", title: "Your whole pipeline, at a glance." },
  { start: 222, page: "History", kicker: "History", title: "Every take — searchable, exportable." },
  { start: 360, page: "Model & Engine", kicker: "Engine", title: "Whisper tiny → large-v3, on your GPU." },
  { start: 498, page: "Audio & Mic", kicker: "Audio", title: "Live mic check, noise gate, feedback." },
  { start: 636, page: "AI Polish", kicker: "AI Polish", title: "Optional refine. Audio never leaves." },
];
const TOUR_END = 766;
const OUTRO_IN = 766;
const XF = 16;

export const TourVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const introOp = interpolate(frame, [0, 1, 64, 84], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const tourOp = interpolate(
    frame,
    [SEGMENTS[0].start - 12, SEGMENTS[0].start + 6, TOUR_END, TOUR_END + 22],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const outroOp = interpolate(frame, [OUTRO_IN, OUTRO_IN + 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // which segment
  let i = 0;
  for (let k = 0; k < SEGMENTS.length; k++) {
    if (frame >= SEGMENTS[k].start) i = k;
  }
  const cur = SEGMENTS[i];
  const prev = SEGMENTS[i - 1];
  const localCur = frame - cur.start;
  const inXfade = i > 0 && localCur < XF;
  const topOpacity = inXfade ? interpolate(localCur, [0, XF], [0, 1]) : 1;

  // window reveal + gentle ken-burns drift (the window is 1280×800; scale to fit)
  const reveal = spring({
    frame: frame - (SEGMENTS[0].start - 10),
    fps,
    config: { damping: 18, mass: 0.9 },
  });
  const fit = 0.92; // fit 1280-wide window into 1920 with margins
  const baseScale = interpolate(reveal, [0, 1], [0.86, fit]);
  const kb = interpolate(localCur, [0, 138], [1.0, 1.035], { extrapolateRight: "clamp" });
  const drift = Math.sin(frame / 95) * 7;
  const windowTransform = `scale(${baseScale * kb}) translateY(${drift}px)`;

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      <Background accent={frame > OUTRO_IN || frame < 84 ? 0.7 : 0.38} />

      {introOp > 0 && (
        <AbsoluteFill style={{ opacity: introOp }}>
          <BrandIntro tagline="A flat, dark instrument panel." />
        </AbsoluteFill>
      )}

      {tourOp > 0 && (
        <AbsoluteFill style={{ opacity: tourOp, justifyContent: "center", alignItems: "center" }}>
          <div style={{ position: "relative", transform: windowTransform }}>
            {inXfade && prev ? (
              <div style={{ position: "absolute", inset: 0 }}>
                <AppWindow active={prev.page} />
              </div>
            ) : null}
            <div style={{ opacity: topOpacity }}>
              <AppWindow active={cur.page} />
            </div>
          </div>

          <div style={{ position: "absolute", top: 56 }}>
            <Caption kicker={cur.kicker} title={cur.title} local={localCur} fps={fps} hold={116} />
          </div>
        </AbsoluteFill>
      )}

      {outroOp > 0 && (
        <Sequence from={OUTRO_IN} layout="none">
          <AbsoluteFill style={{ opacity: outroOp }}>
            <BrandOutro headline="One hotkey. Every app. Zero cloud." />
          </AbsoluteFill>
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
