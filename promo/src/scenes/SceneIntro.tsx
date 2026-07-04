import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { InfinityLogo } from "../components/InfinityLogo";
import { COLORS, FONT } from "../theme";
import { seg, pop, fadeInOut } from "../anim";

export const SceneIntro: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const draw = seg(frame, 6, 70); // logo draws on
  const logoScale = 0.85 + pop(frame, fps, 0) * 0.15;
  const nameRise = pop(frame, fps, 60);
  const tagOpacity = seg(frame, 90, 115);
  const opacity = fadeInOut(frame, dur, 10, 20);

  return (
    <AbsoluteFill style={{ opacity }}>
      <Background />
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <div style={{ transform: `scale(${logoScale})` }}>
          <InfinityLogo size={520} progress={draw} />
        </div>

        <div
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 150,
            letterSpacing: -4,
            color: COLORS.white,
            transform: `translateY(${(1 - nameRise) * 60}px)`,
            opacity: nameRise,
            marginTop: 20,
          }}
        >
          Trust<span style={{ color: COLORS.blue }}>First</span>
        </div>

        <div
          style={{
            fontFamily: FONT,
            fontWeight: 500,
            fontSize: 42,
            color: COLORS.gray,
            opacity: tagOpacity,
            letterSpacing: 1,
          }}
        >
          The trust-first social platform
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
