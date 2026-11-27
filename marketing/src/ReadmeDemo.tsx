import React from "react";
import {
  AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, staticFile,
  interpolate, Easing, useCurrentFrame,
} from "remotion";
import transcript from "../public/showcase/transcript.json";

const media = (name: string) => staticFile("showcase/" + name);
const ink = "#F3F1EE";
const muted = "#B3BCC5";
const accent = "#F4A485";
const soft = Easing.bezier(0.2, 0.7, 0.2, 1);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const Scene: React.FC<{ label: string; heading: string; detail: string; children: React.ReactNode }> = ({
  label, heading, detail, children,
}) => {
  const frame = useCurrentFrame();
  const rise = interpolate(frame, [0, 15], [13, 0], { ...clamp, easing: soft });
  const opacity = interpolate(frame, [0, 11], [0.77, 1], clamp);
  return (
    <AbsoluteFill style={{ background: "#101418", color: ink, fontFamily: 'Inter, "Segoe UI", sans-serif' }}>
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 76% 58%, #292E34 0%, #171C21 45%, #101418 78%)" }} />
      <div style={{ position: "absolute", left: 86, top: 64, display: "flex", alignItems: "center", gap: 13, fontSize: 24, fontWeight: 650 }}>
        <Img src={media("icon.svg")} style={{ width: 38, height: 38 }} />
        JasperVoice
      </div>
      <div style={{ position: "absolute", right: 76, top: 73, color: muted, fontSize: 19 }}>
        Windows · v1.2
      </div>
      <div style={{ position: "absolute", top: 166, left: 86, right: 86, height: 1, background: "#333C45" }} />
      <div style={{ position: "absolute", left: 86, top: 294 + rise, width: 480, opacity }}>
        <div style={{ fontSize: 21, color: accent, fontWeight: 650 }}>{label}</div>
        <div style={{ marginTop: 19, fontSize: 80, fontWeight: 680, letterSpacing: "-0.047em", lineHeight: 1.02 }}>{heading}</div>
        <div style={{ marginTop: 26, color: muted, fontSize: 27, lineHeight: 1.38, maxWidth: 365 }}>{detail}</div>
      </div>
      <div style={{ position: "absolute", left: 590, top: 210 + rise, width: 924, height: 560, opacity }}>
        {children}
      </div>
    </AbsoluteFill>
  );
};

const Dictation: React.FC = () => {
  const frame = useCurrentFrame();
  const state = frame < 42 ? null : frame < 138 ? "recording" : frame < 167 ? "processing" : frame < 203 ? "send" : null;
  const typed = Math.floor(interpolate(frame, [167, 187], [0, transcript.text.length], clamp));
  const tile: React.CSSProperties = {
    position: "absolute", top: 113, left: 28, width: 867, height: 328, borderRadius: 22, overflow: "hidden",
    background: "#20262C", border: "1px solid #47515C", boxShadow: "0 25px 75px #080A0C9C",
  };
  return (
    <Scene label="On-device transcription" heading="Speak. Release. Done." detail="Hold the shortcut and dictate directly into the app you’re using.">
      <div style={tile}>
        <div style={{ display: "flex", alignItems: "center", height: 65, padding: "0 30px", color: muted, fontSize: 22, borderBottom: "1px solid #424A52", background: "#262D34" }}>
          Draft notes
        </div>
        <div style={{ fontSize: 46, fontWeight: 610, letterSpacing: "-0.025em", margin: "62px 41px 0" }}>
          {typed > 0 ? transcript.text.slice(0, typed) : frame < 42 ? <span style={{ color: muted, fontSize: 32 }}>Ready to dictate</span> : ""}
          <span style={{ display: "inline-block", verticalAlign: "middle", marginLeft: 3, height: 42, width: 3, background: accent, opacity: frame % 32 < 22 ? 1 : 0.25 }} />
        </div>
        {state && (
          <Img src={media(state + ".png")} style={{ position: "absolute", bottom: 19, right: 22, width: 264 }} />
        )}
      </div>
      <div style={{ position: "absolute", top: 468, left: 28, display: "flex", gap: 9, alignItems: "center" }}>
        {["Ctrl", "Shift", "Space"].map(key => (
          <span key={key} style={{ border: "1px solid " + (state === "recording" ? accent : "#49535E"), borderRadius: 8, padding: "7px 12px", fontSize: 21 }}>{key}</span>
        ))}
      </div>
      <Sequence from={42} layout="none"><Audio src={media("dictation.wav")} volume={0.85} /></Sequence>
    </Scene>
  );
};

const Mic: React.FC = () => (
  <Scene label="Mic Check" heading="See your input." detail="Check the input level and peaks before you start dictating.">
    <div style={{ position: "absolute", top: 126, width: 924, height: 375, borderRadius: 22, overflow: "hidden", border: "1px solid #49535E", boxShadow: "0 25px 75px #080A0C9C", background: "#13161A" }}>
      <OffthreadVideo src={media("mic-check.mp4")} muted style={{ position: "absolute", width: 1122, height: "auto", left: -198, top: 5 }} />
    </div>
  </Scene>
);

const Polish: React.FC = () => {
  const frame = useCurrentFrame();
  const result = interpolate(frame, [64, 83], [0, 1], { ...clamp, easing: soft });
  const highlight = interpolate(frame, [36, 46, 65], [0, 1, 0], clamp);
  return (
    <Scene label="Optional AI Polish" heading="Keep your voice." detail="Preview the style and instructions with your own model or provider.">
      <div style={{ position: "absolute", top: 0, width: 924, height: 470, borderRadius: 22, overflow: "hidden", border: "1px solid #49535E", boxShadow: "0 25px 75px #080A0C9C", background: "#13161A" }}>
        <Img src={media("polish.png")} style={{ position: "absolute", width: 858, left: 32, top: 12, clipPath: "inset(0 0 47px 0)" }} />
        <div style={{ position: "absolute", left: 741, top: 401, width: 151, height: 40, borderRadius: 7, boxShadow: "0 0 0 2px " + accent, opacity: highlight }} />
      </div>
      <div style={{ position: "absolute", left: 28, top: 498 + 12 * (1 - result), opacity: result, display: "flex", alignItems: "center", gap: 16, fontSize: 33, letterSpacing: "-0.018em" }}>
        <span style={{ color: accent }}>✓</span>
        Hi team, the draft is ready for review.
      </div>
    </Scene>
  );
};

export const ReadmeDemo: React.FC = () => (
  <>
    <Sequence durationInFrames={220}><Dictation /></Sequence>
    <Sequence from={220} durationInFrames={167}><Mic /></Sequence>
    <Sequence from={387} durationInFrames={183}><Polish /></Sequence>
  </>
);
