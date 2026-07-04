import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { COLORS, FONT } from "../theme";
import { seg, pop, fadeInOut, ease } from "../anim";
import { Avatar, VerifiedBadge } from "../components/ui";

export const SceneVerify: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeInOut(frame, dur);

  const cardIn = ease(frame, fps, 6);
  const scan = seg(frame, 30, 110); // scan line travels 0..1
  const scanning = seg(frame, 28, 40, 0, 1) * (1 - seg(frame, 108, 124));
  const badgePop = pop(frame, fps, 120);
  const ring = seg(frame, 120, 165);
  const textIn = seg(frame, 140, 165);

  const CARD = 620;

  return (
    <AbsoluteFill style={{ opacity }}>
      <Background a={COLORS.blue} b={COLORS.purple} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
        <div
          style={{
            width: CARD,
            background: COLORS.card,
            borderRadius: 48,
            border: `1px solid ${COLORS.line}`,
            padding: 56,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            transform: `translateY(${(1 - cardIn) * 80}px) scale(${0.9 + cardIn * 0.1})`,
            boxShadow: "0 40px 120px rgba(0,0,0,0.5)",
            position: "relative",
            overflow: "hidden",
          }}
        >
          {/* avatar + scan overlay */}
          <div style={{ position: "relative", borderRadius: "50%", overflow: "hidden" }}>
            <Avatar name="Kgothi" size={260} />
            {/* scan line */}
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: `${scan * 100}%`,
                height: 6,
                background: COLORS.green,
                boxShadow: `0 0 30px 8px ${COLORS.green}`,
                opacity: scanning,
              }}
            />
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: `linear-gradient(${COLORS.green}22, transparent)`,
                clipPath: `inset(0 0 ${(1 - scan) * 100}% 0)`,
                opacity: scanning * 0.8,
              }}
            />
          </div>

          {/* badge stamp */}
          <div style={{ position: "relative", marginTop: -60, marginRight: -180 }}>
            <div
              style={{
                position: "absolute",
                inset: 0,
                margin: "auto",
                width: 120,
                height: 120,
                borderRadius: "50%",
                border: `4px solid ${COLORS.blue}`,
                transform: `scale(${1 + ring * 1.6})`,
                opacity: (1 - ring) * 0.8,
              }}
            />
            <div style={{ transform: `scale(${badgePop})` }}>
              <VerifiedBadge size={120} />
            </div>
          </div>

          <div
            style={{
              fontFamily: FONT,
              fontWeight: 800,
              fontSize: 56,
              color: "#fff",
              marginTop: 30,
              display: "flex",
              alignItems: "center",
              gap: 14,
            }}
          >
            Kgothi
          </div>
          <div style={{ fontFamily: FONT, fontSize: 34, color: COLORS.gray }}>
            Identity verified · KYC
          </div>
        </div>

        <div
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 72,
            color: "#fff",
            textAlign: "center",
            marginTop: 70,
            opacity: textIn,
            transform: `translateY(${(1 - textIn) * 30}px)`,
          }}
        >
          Every profile, verified.
        </div>
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 500,
            fontSize: 40,
            color: COLORS.gray,
            marginTop: 12,
            opacity: textIn,
          }}
        >
          Real people. Real trust. No bots.
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
