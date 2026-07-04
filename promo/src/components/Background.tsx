import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { COLORS } from "../theme";

/** Premium dark background with two slowly drifting colored glows + vignette. */
export const Background: React.FC<{ a?: string; b?: string }> = ({
  a = COLORS.purple,
  b = COLORS.blue,
}) => {
  const frame = useCurrentFrame();
  const t = frame / 30;
  const x1 = 30 + Math.sin(t * 0.5) * 12;
  const y1 = 25 + Math.cos(t * 0.4) * 10;
  const x2 = 70 + Math.cos(t * 0.45) * 12;
  const y2 = 75 + Math.sin(t * 0.5) * 10;

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.ink }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(45% 35% at ${x1}% ${y1}%, ${a}55, transparent 70%),
                       radial-gradient(45% 35% at ${x2}% ${y2}%, ${b}4d, transparent 70%)`,
        }}
      />
      {/* subtle grid */}
      <AbsoluteFill
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)",
          backgroundSize: "80px 80px",
          maskImage: "radial-gradient(circle at 50% 45%, black, transparent 80%)",
        }}
      />
      {/* vignette */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 45%, transparent 45%, rgba(0,0,0,0.55) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};
