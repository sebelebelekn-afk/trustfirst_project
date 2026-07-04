import React from "react";
import { interpolate } from "remotion";
import { COLORS } from "../theme";

// Figure-8 / infinity Lissajous curve — identical shape to the app icons:
// x = cx + A*cos(t), y = cy + B*sin(2t)
function infinityPath(cx: number, cy: number, A: number, B: number, N = 260): string {
  let d = "";
  for (let i = 0; i <= N; i++) {
    const t = (2 * Math.PI * i) / N;
    const x = cx + A * Math.cos(t);
    const y = cy + B * Math.sin(2 * t);
    d += (i === 0 ? "M" : "L") + x.toFixed(2) + " " + y.toFixed(2) + " ";
  }
  return d;
}

const D = infinityPath(512, 512, 300, 180);

export const InfinityLogo: React.FC<{
  size?: number;
  /** 0 → 1 draw-on progress */
  progress?: number;
  /** show the rounded-square brand plate behind the mark */
  plate?: boolean;
  strokeWidth?: number;
  glow?: boolean;
}> = ({ size = 420, progress = 1, plate = false, strokeWidth = 64, glow = true }) => {
  const dashOffset = interpolate(progress, [0, 1], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 1024 1024"
      style={{ display: "block", overflow: "visible" }}
    >
      <defs>
        <linearGradient id="tf-grad" x1="0" y1="0" x2="1024" y2="1024" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={COLORS.purple} />
          <stop offset="0.55" stopColor={COLORS.blue} />
          <stop offset="1" stopColor={COLORS.orange} />
        </linearGradient>
        <filter id="tf-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="26" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {plate && (
        <rect x="0" y="0" width="1024" height="1024" rx="225" fill={COLORS.dark} />
      )}

      {/* soft glow underlay */}
      {glow && (
        <path
          d={D}
          fill="none"
          stroke="url(#tf-grad)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={dashOffset}
          opacity={0.55}
          filter="url(#tf-glow)"
        />
      )}

      {/* crisp stroke */}
      <path
        d={D}
        fill="none"
        stroke="url(#tf-grad)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={dashOffset}
      />
    </svg>
  );
};
