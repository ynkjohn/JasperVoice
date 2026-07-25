import React from "react";
import { COLORS, sans, mono } from "../theme";

const Bubble: React.FC<{
  text: string;
  me?: boolean;
  muted?: boolean;
}> = ({ text, me, muted }) => (
  <div style={{ display: "flex", justifyContent: me ? "flex-end" : "flex-start" }}>
    <div
      style={{
        maxWidth: "72%",
        background: me ? COLORS.accent : COLORS.bgHover,
        color: me ? COLORS.bg : COLORS.fg,
        opacity: muted ? 0.55 : 1,
        padding: "12px 16px",
        borderRadius: 14,
        borderBottomRightRadius: me ? 4 : 14,
        borderBottomLeftRadius: me ? 14 : 4,
        fontFamily: sans,
        fontSize: 17,
        lineHeight: 1.45,
        fontWeight: me ? 600 : 400,
      }}
    >
      {text}
    </div>
  </div>
);

// A messaging app receiving dictated text. `typed` = chars revealed in the
// composer; once `sent` is true the text flips to a sent bubble.
export const ChatApp: React.FC<{
  full: string;
  typed: number;
  sent: boolean;
  caret: boolean;
}> = ({ full, typed, sent, caret }) => {
  const shown = full.slice(0, Math.max(0, Math.floor(typed)));
  return (
    <div
      style={{
        width: 760,
        height: 560,
        background: COLORS.bg,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 16,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        boxShadow: "0 40px 120px rgba(0,0,0,0.6)",
      }}
    >
      {/* title bar */}
      <div
        style={{
          height: 52,
          background: COLORS.sidebar,
          borderBottom: `1px solid ${COLORS.border}`,
          display: "flex",
          alignItems: "center",
          padding: "0 18px",
          gap: 14,
        }}
      >
        <div style={{ display: "flex", gap: 8 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
            <div key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c }} />
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: 8 }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 15,
              background: COLORS.accent,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: mono,
              fontWeight: 700,
              color: COLORS.bg,
              fontSize: 14,
            }}
          >
            A
          </div>
          <div>
            <div style={{ color: COLORS.fg, fontFamily: sans, fontSize: 15, fontWeight: 600 }}>
              #engineering
            </div>
            <div style={{ color: COLORS.fgMuted, fontFamily: sans, fontSize: 11 }}>
              typing with your voice
            </div>
          </div>
        </div>
      </div>

      {/* messages */}
      <div
        style={{
          flex: 1,
          padding: 22,
          display: "flex",
          flexDirection: "column",
          gap: 14,
          justifyContent: "flex-end",
        }}
      >
        <Bubble text="Can you send the standup update?" muted />
        <Bubble text="On it — one sec." me muted />
        {sent ? <Bubble text={full} me /> : null}
      </div>

      {/* composer */}
      <div
        style={{
          borderTop: `1px solid ${COLORS.border}`,
          padding: 16,
          background: COLORS.bg,
        }}
      >
        <div
          style={{
            minHeight: 52,
            background: COLORS.bgAlt,
            border: `1px solid ${sent ? COLORS.border : COLORS.accent}`,
            borderRadius: 12,
            padding: "14px 16px",
            display: "flex",
            alignItems: "center",
            color: shown ? COLORS.fg : COLORS.fgDisabled,
            fontFamily: sans,
            fontSize: 17,
          }}
        >
          {sent ? (
            <span style={{ color: COLORS.fgDisabled }}>Message sent</span>
          ) : (
            <span>
              {shown || "Type a message…"}
              {caret ? (
                <span
                  style={{
                    display: "inline-block",
                    width: 2,
                    height: 20,
                    background: COLORS.accent,
                    marginLeft: 1,
                    transform: "translateY(3px)",
                  }}
                />
              ) : null}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
