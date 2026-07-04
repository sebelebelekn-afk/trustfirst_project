import React from "react";
import { COLORS, FONT } from "../theme";

const GRADS = [
  ["#5856D6", "#007AFF"],
  ["#FF9500", "#FF2D92"],
  ["#34C759", "#007AFF"],
  ["#FF2D92", "#5856D6"],
  ["#00C6FB", "#005BEA"],
  ["#FF9500", "#FF3B30"],
];

export const Avatar: React.FC<{ name: string; size?: number; ring?: boolean }> = ({
  name,
  size = 96,
  ring = false,
}) => {
  const idx = (name.charCodeAt(0) + (name.charCodeAt(1) || 0)) % GRADS.length;
  const [a, b] = GRADS[idx];
  const inner = (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: `linear-gradient(135deg, ${a}, ${b})`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontFamily: FONT,
        fontWeight: 700,
        fontSize: size * 0.42,
        flexShrink: 0,
      }}
    >
      {name.charAt(0).toUpperCase()}
    </div>
  );
  if (!ring) return inner;
  return (
    <div
      style={{
        padding: size * 0.05,
        borderRadius: "50%",
        background: `conic-gradient(from 30deg, ${COLORS.blue}, ${COLORS.purple}, ${COLORS.orange}, ${COLORS.blue})`,
        display: "inline-flex",
      }}
    >
      <div style={{ padding: size * 0.04, borderRadius: "50%", background: COLORS.ink }}>{inner}</div>
    </div>
  );
};

export const VerifiedBadge: React.FC<{ size?: number; color?: string }> = ({
  size = 40,
  color = COLORS.blue,
}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{ display: "block", flexShrink: 0 }}>
    <path
      fill={color}
      d="M12 1l2.4 1.8 3 .2.9 2.9 2.4 1.8-.9 2.9.9 2.9-2.4 1.8-.9 2.9-3 .2L12 23l-2.4-1.8-3-.2-.9-2.9L3.3 16.3l.9-2.9-.9-2.9 2.4-1.8.9-2.9 3-.2z"
    />
    <path
      fill="#fff"
      d="M10.6 14.6l-2.2-2.2-1.3 1.3 3.5 3.5 6-6-1.3-1.3z"
    />
  </svg>
);

export const Pill: React.FC<{ children: React.ReactNode; bg?: string; color?: string }> = ({
  children,
  bg = "rgba(255,255,255,0.1)",
  color = "#fff",
}) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      background: bg,
      color,
      fontFamily: FONT,
      fontWeight: 600,
      fontSize: 30,
      padding: "14px 26px",
      borderRadius: 100,
      backdropFilter: "blur(8px)",
    }}
  >
    {children}
  </div>
);
