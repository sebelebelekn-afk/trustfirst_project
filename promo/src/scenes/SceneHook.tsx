import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { COLORS, FONT } from "../theme";
import { seg, pop, fadeInOut } from "../anim";
import { VerifiedBadge } from "../components/ui";

const FAKES = ["🤖 bot_4471", "👤 user_x92", "🎭 fake_acct", "⚠️ spam_bot", "🕵️ scammer"];

export const SceneHook: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeInOut(frame, dur);

  const line1 = seg(frame, 8, 28);
  // fakes drift in then get "cleared"
  const fakesIn = seg(frame, 20, 45);
  const cleared = seg(frame, 95, 120);
  const trustPop = pop(frame, fps, 120);
  const stamp = pop(frame, fps, 150);

  return (
    <AbsoluteFill style={{ opacity }}>
      <Background a={COLORS.red} b={COLORS.purple} />
      <AbsoluteFill
        style={{
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: 80,
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 600,
            fontSize: 56,
            color: COLORS.gray,
            textAlign: "center",
            opacity: line1,
            transform: `translateY(${(1 - line1) * 30}px)`,
          }}
        >
          Social media forgot
          <br /> one thing.
        </div>

        {/* floating fake accounts that fade out */}
        <div
          style={{
            position: "relative",
            width: 900,
            height: 360,
            marginTop: 40,
            opacity: fakesIn * (1 - cleared),
          }}
        >
          {FAKES.map((f, i) => {
            const angle = (i / FAKES.length) * Math.PI * 2;
            const x = 380 + Math.cos(angle) * 300;
            const y = 150 + Math.sin(angle) * 120;
            return (
              <div
                key={f}
                style={{
                  position: "absolute",
                  left: x,
                  top: y,
                  transform: `translate(-50%,-50%) scale(${1 - cleared * 0.4})`,
                  fontFamily: FONT,
                  fontWeight: 600,
                  fontSize: 34,
                  color: "#fff",
                  background: "rgba(255,59,48,0.14)",
                  border: "1px solid rgba(255,59,48,0.4)",
                  padding: "12px 22px",
                  borderRadius: 100,
                  whiteSpace: "nowrap",
                }}
              >
                {f}
              </div>
            );
          })}
        </div>

        {/* the payoff */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 24,
            marginTop: -20,
            transform: `scale(${0.6 + trustPop * 0.4})`,
            opacity: trustPop,
          }}
        >
          <div
            style={{
              fontFamily: FONT,
              fontWeight: 900,
              fontSize: 200,
              letterSpacing: -6,
              background: `linear-gradient(120deg, ${COLORS.blue}, ${COLORS.purple})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            TRUST
          </div>
          <div style={{ transform: `scale(${stamp}) rotate(${(1 - stamp) * -40}deg)` }}>
            <VerifiedBadge size={120} />
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
