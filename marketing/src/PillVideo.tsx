import React from "react";
import {
  AbsoluteFill,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
  Sequence,
} from "remotion";
import { Background } from "./components/Background";
import { BrandIntro, BrandOutro } from "./components/Brand";
import { Pill } from "./components/Pill";
import { PillState } from "./theme";
import { Keycaps } from "./components/Keycaps";
import { ChatApp } from "./components/ChatApp";
import { Caption } from "./components/Caption";
import { COLORS } from "./theme";

const DICTATED = "Shipped the overlay pill, fixed the CUDA fallback, and cut the 1.0.5 release.";

// world (untransformed) is 1920×1080; the camera pushes into the pill corner.
const VW = 1920;
const VH = 1080;
const PILL = { x: 1560, y: 922 }; // bottom-right corner, in world coords
const ZOOM = 5.2;
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export const PillVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // ---- timeline (900 frames @30fps) ----
  const INTRO_END = 76;
  const ESTAB_IN = 70;
  const KEY_PRESS = 138;
  const ZOOM_IN0 = 150;
  const ZOOM_IN1 = 190;
  const LISTEN = 162;
  const PROCESS = 300;
  const SENT = 404;
  const ZOOM_OUT0 = 470;
  const ZOOM_OUT1 = 512;
  const TYPE0 = 524;
  const TYPE1 = 664;
  const SENT_MSG = 690;
  const OUTRO_IN = 766;

  // ---- camera zoom progress (0 = wide, 1 = on the pill) ----
  let zp = 0;
  if (frame >= ZOOM_IN0 && frame < ZOOM_IN1) {
    zp = interpolate(frame, [ZOOM_IN0, ZOOM_IN1], [0, 1], {
      easing: Easing.bezier(0.5, 0, 0.2, 1),
    });
  } else if (frame >= ZOOM_IN1 && frame < ZOOM_OUT0) {
    zp = 1;
  } else if (frame >= ZOOM_OUT0 && frame < ZOOM_OUT1) {
    zp = interpolate(frame, [ZOOM_OUT0, ZOOM_OUT1], [1, 0], {
      easing: Easing.bezier(0.5, 0, 0.2, 1),
    });
  }
  const cx = lerp(VW / 2, PILL.x, zp);
  const cy = lerp(VH / 2, PILL.y, zp);
  const cs = lerp(1, ZOOM, zp);
  const camTransform = `translate(${VW / 2 - cx * cs}px, ${VH / 2 - cy * cs}px) scale(${cs})`;

  // ---- pill state machine ----
  let pillState: PillState = "idle";
  let stateStart = 0;
  if (frame >= LISTEN && frame < PROCESS) {
    pillState = "recording";
    stateStart = LISTEN;
  } else if (frame >= PROCESS && frame < SENT) {
    pillState = "processing";
    stateStart = PROCESS;
  } else if (frame >= SENT && frame < ZOOM_OUT1) {
    pillState = "send";
    stateStart = SENT;
  }

  // ---- keycaps press ----
  const press = interpolate(frame, [KEY_PRESS - 14, KEY_PRESS, ZOOM_IN0 + 6, ZOOM_IN0 + 18], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const keycapsOp = interpolate(frame, [ESTAB_IN + 20, ESTAB_IN + 40, ZOOM_IN0, ZOOM_IN0 + 14], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ---- typing into composer ----
  const typed = interpolate(frame, [TYPE0, TYPE1], [0, DICTATED.length], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.linear,
  });
  const sentInChat = frame >= SENT_MSG;
  const caretOn = Math.floor((frame / fps) * 2) % 2 === 0;

  // ---- world (chat + pill) visibility ----
  const worldOp = interpolate(frame, [ESTAB_IN, ESTAB_IN + 16, OUTRO_IN - 6, OUTRO_IN], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const introOp = interpolate(frame, [-1, 1, INTRO_END - 16, INTRO_END], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const outroOp = interpolate(frame, [OUTRO_IN, OUTRO_IN + 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ---- active caption (screen space, not zoomed) ----
  type Cap = { kicker: string; title: string; from: number; hold: number; pos: "top" | "bottom" };
  let cap: Cap | null = null;
  if (frame >= ESTAB_IN && frame < ZOOM_IN0) {
    cap = { kicker: "In any app", title: "Hold the hotkey, anywhere.", from: ESTAB_IN, hold: 70, pos: "top" };
  } else if (frame >= LISTEN && frame < PROCESS) {
    cap = { kicker: "01 · Listen", title: "Just speak — naturally.", from: ZOOM_IN1, hold: 110, pos: "bottom" };
  } else if (frame >= PROCESS && frame < SENT) {
    cap = { kicker: "02 · Transcribe", title: "Whisper runs on your machine.", from: PROCESS, hold: 90, pos: "bottom" };
  } else if (frame >= SENT && frame < ZOOM_OUT1) {
    cap = { kicker: "03 · Done", title: "Pasted into the active app.", from: SENT, hold: 70, pos: "bottom" };
  } else if (frame >= ZOOM_OUT1 && frame < SENT_MSG) {
    cap = { kicker: "Live", title: "Your words, typed for you.", from: ZOOM_OUT1, hold: 150, pos: "top" };
  } else if (frame >= SENT_MSG && frame < OUTRO_IN) {
    cap = { kicker: "Sent", title: "Hands never left the keyboard.", from: SENT_MSG, hold: 90, pos: "top" };
  }

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      <Background accent={frame > OUTRO_IN || frame < INTRO_END ? 0.7 : 0.42} />

      {/* INTRO */}
      {introOp > 0 && (
        <AbsoluteFill style={{ opacity: introOp }}>
          <BrandIntro tagline="Push-to-talk dictation, 100% offline." />
        </AbsoluteFill>
      )}

      {/* WORLD: chat + corner pill, driven by the camera */}
      {worldOp > 0 && (
        <AbsoluteFill style={{ opacity: worldOp }}>
          <AbsoluteFill style={{ transform: camTransform, transformOrigin: "0 0" }}>
            {/* chat centered in the world */}
            <div
              style={{
                position: "absolute",
                left: VW / 2,
                top: VH / 2,
                transform: "translate(-50%, -50%)",
              }}
            >
              <ChatApp full={DICTATED} typed={typed} sent={sentInChat} caret={caretOn && !sentInChat} />
            </div>
            {/* overlay pill anchored in the bottom-right corner */}
            <div
              style={{
                position: "absolute",
                left: PILL.x,
                top: PILL.y,
                transform: "translate(-50%, -50%)",
              }}
            >
              <Pill state={pillState} localFrame={frame - stateStart} fps={fps} scale={1.4} />
            </div>
          </AbsoluteFill>
        </AbsoluteFill>
      )}

      {/* keycaps (screen space) */}
      {keycapsOp > 0 && (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", opacity: keycapsOp }}>
          <div style={{ marginBottom: 96 }}>
            <Keycaps pressed={press} />
          </div>
        </AbsoluteFill>
      )}

      {/* caption overlay (screen space) */}
      {cap && (
        <AbsoluteFill
          style={{
            justifyContent: cap.pos === "top" ? "flex-start" : "flex-end",
            alignItems: "center",
            padding: cap.pos === "top" ? "96px 0 0" : "0 0 110px",
          }}
        >
          <Caption kicker={cap.kicker} title={cap.title} local={frame - cap.from} fps={fps} hold={cap.hold} />
        </AbsoluteFill>
      )}

      {/* OUTRO */}
      {outroOp > 0 && (
        <Sequence from={OUTRO_IN} layout="none">
          <AbsoluteFill style={{ opacity: outroOp }}>
            <BrandOutro />
          </AbsoluteFill>
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
