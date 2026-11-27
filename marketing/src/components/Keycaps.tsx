import React from "react";
import { COLORS, mono } from "../theme";

const Cap: React.FC<{ label: string; pressed: number; wide?: boolean }> = ({
  label,
  pressed,
  wide,
}) => {
  // pressed: 0..1 — depresses + lights with the accent.
  const depress = pressed * 3;
  return (
    <div
      style={{
        fontFamily: mono,
        fontSize: 22,
        fontWeight: 700,
        letterSpacing: 1,
        color: pressed > 0.2 ? COLORS.bg : COLORS.fg,
        background: pressed > 0.2 ? COLORS.accent : COLORS.bgAlt,
        border: `1.5px solid ${pressed > 0.2 ? COLORS.accent : COLORS.borderStrong}`,
        borderRadius: 10,
        padding: wide ? "16px 46px" : "16px 22px",
        minWidth: wide ? 220 : 58,
        textAlign: "center",
        transform: `translateY(${depress}px)`,
        boxShadow:
          pressed > 0.2
            ? `0 0 26px ${COLORS.accent}66, 0 ${6 - depress}px 0 ${COLORS.accentHover}`
            : `0 6px 0 #000, 0 8px 14px rgba(0,0,0,0.5)`,
      }}
    >
      {label}
    </div>
  );
};

export const Keycaps: React.FC<{ pressed: number }> = ({ pressed }) => {
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
      <Cap label="Ctrl" pressed={pressed} />
      <span style={{ color: COLORS.fgMuted, fontSize: 26, fontFamily: mono }}>+</span>
      <Cap label="Shift" pressed={pressed} />
      <span style={{ color: COLORS.fgMuted, fontSize: 26, fontFamily: mono }}>+</span>
      <Cap label="Space" pressed={pressed} wide />
    </div>
  );
};
