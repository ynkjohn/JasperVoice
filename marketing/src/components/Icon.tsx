import React from "react";

// Minimal line glyphs mirroring NAV_GLYPHS in ui.py (grid, clock, book,
// sliders, mic, chip, spark, download, pulse).
export type Glyph =
  | "grid"
  | "clock"
  | "book"
  | "sliders"
  | "mic"
  | "chip"
  | "spark"
  | "download"
  | "pulse";

export const Icon: React.FC<{ glyph: Glyph; size?: number; color: string }> = ({
  glyph,
  size = 16,
  color,
}) => {
  const p = {
    fill: "none",
    stroke: color,
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      {glyph === "grid" && (
        <g {...p}>
          <rect x="4" y="4" width="6.5" height="6.5" rx="1" />
          <rect x="13.5" y="4" width="6.5" height="6.5" rx="1" />
          <rect x="4" y="13.5" width="6.5" height="6.5" rx="1" />
          <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1" />
        </g>
      )}
      {glyph === "clock" && (
        <g {...p}>
          <circle cx="12" cy="12" r="8" />
          <path d="M12 8v4l3 2" />
        </g>
      )}
      {glyph === "book" && (
        <g {...p}>
          <path d="M5 5h6a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H5z" />
          <path d="M19 5h-6a2 2 0 0 0-2 2v12a2 2 0 0 1 2-2h6z" />
        </g>
      )}
      {glyph === "sliders" && (
        <g {...p}>
          <path d="M5 7h9M18 7h1M5 12h2M11 12h8M5 17h6M15 17h4" />
          <circle cx="16" cy="7" r="2" />
          <circle cx="9" cy="12" r="2" />
          <circle cx="13" cy="17" r="2" />
        </g>
      )}
      {glyph === "mic" && (
        <g {...p}>
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6" />
        </g>
      )}
      {glyph === "chip" && (
        <g {...p}>
          <rect x="7" y="7" width="10" height="10" rx="1.5" />
          <path d="M10 2v3M14 2v3M10 19v3M14 19v3M2 10h3M2 14h3M19 10h3M19 14h3" />
        </g>
      )}
      {glyph === "spark" && (
        <g {...p}>
          <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
          <path d="M18 16l.7 2 .8 2-2-.8-2-.7 2-.8z" />
        </g>
      )}
      {glyph === "download" && (
        <g {...p}>
          <path d="M12 3v11M8 11l4 4 4-4M5 19h14" />
        </g>
      )}
      {glyph === "pulse" && (
        <g {...p}>
          <path d="M3 12h4l2-6 4 12 2-6h6" />
        </g>
      )}
    </svg>
  );
};
