import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { InfinityLogo } from "../components/InfinityLogo";
import { COLORS, FONT } from "../theme";
import { seg, pop, fadeInOut } from "../anim";
import { Pill } from "../components/ui";

// 👇 Change this to your real URL before final render.
const URL = "trustfirst.app";

export const SceneCTA: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeInOut(frame, dur, 16, 30);

  const logoPop = pop(frame, fps, 4);
  const draw = seg(frame, 6, 50);
  const headIn = seg(frame, 30, 55);
  const pillsIn = pop(frame, fps, 58);
  const urlIn = seg(frame, 74, 96);
  const glow = 0.5 + Math.sin(frame / 10) * 0.5;

  return (
    <AbsoluteFill style={{ opacity }}>
      <Background />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
        <div style={{ transform: `scale(${logoPop})`, filter: `drop-shadow(0 0 ${40 * glow}px ${COLORS.blue}88)` }}>
          <InfinityLogo size={440} progress={draw} />
        </div>

        <div
          style={{
            fontFamily: FONT,
            fontWeight: 900,
            fontSize: 130,
            letterSpacing: -3,
            color: "#fff",
            marginTop: 30,
            opacity: headIn,
            transform: `translateY(${(1 - headIn) * 40}px)`,
          }}
        >
          Join Trust<span style={{ color: COLORS.blue }}>First</span>
        </div>

        <div
          style={{
            fontFamily: FONT,
            fontWeight: 500,
            fontSize: 46,
            color: COLORS.gray,
            marginTop: 6,
            opacity: headIn,
            textAlign: "center",
          }}
        >
          Where every connection is earned.
        </div>

        <div style={{ display: "flex", gap: 26, marginTop: 60, transform: `scale(${pillsIn})`, opacity: pillsIn }}>
          <Pill>📱 iOS</Pill>
          <Pill>🤖 Android</Pill>
          <Pill>🌐 Web</Pill>
        </div>

        <div
          style={{
            fontFamily: FONT,
            fontWeight: 700,
            fontSize: 54,
            color: "#fff",
            marginTop: 70,
            padding: "22px 60px",
            borderRadius: 100,
            background: `linear-gradient(120deg, ${COLORS.purple}, ${COLORS.blue})`,
            opacity: urlIn,
            transform: `translateY(${(1 - urlIn) * 30}px)`,
            boxShadow: `0 20px 70px ${COLORS.blue}66`,
          }}
        >
          {URL}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
