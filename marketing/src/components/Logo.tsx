import React from "react";

// The JasperVoice mark — ported verbatim from assets/icon.svg.
export const Logo: React.FC<{ size?: number; glow?: number }> = ({
  size = 256,
  glow = 0,
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 256 256"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{
        filter: glow > 0 ? `drop-shadow(0 0 ${glow}px rgba(217,119,87,0.55))` : undefined,
      }}
    >
      <rect x="8" y="8" width="240" height="240" rx="52" fill="#0F0F0F" />
      <rect x="8.5" y="8.5" width="239" height="239" rx="51.5" stroke="#2A2A2A" strokeWidth="1" />

      <g stroke="#9E9A9A" strokeWidth="6" strokeLinecap="round" fill="none" opacity="0.55">
        <path d="M64 104 a 26 26 0 0 0 0 48" />
        <path d="M192 104 a 26 26 0 0 1 0 48" />
      </g>
      <g stroke="#D97757" strokeWidth="6" strokeLinecap="round" fill="none">
        <path d="M48 86 a 52 52 0 0 0 0 84" />
        <path d="M208 86 a 52 52 0 0 1 0 84" />
      </g>

      <rect x="104" y="56" width="48" height="92" rx="24" fill="#D97757" />
      <circle cx="128" cy="82" r="9" fill="#0F0F0F" opacity="0.35" />

      <path
        d="M88 128 a 40 40 0 0 0 80 0"
        stroke="#E8E6E6"
        strokeWidth="9"
        strokeLinecap="round"
        fill="none"
      />
      <line x1="128" y1="168" x2="128" y2="196" stroke="#E8E6E6" strokeWidth="9" strokeLinecap="round" />
      <line x1="100" y1="196" x2="156" y2="196" stroke="#E8E6E6" strokeWidth="9" strokeLinecap="round" />
    </svg>
  );
};
