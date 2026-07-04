import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { COLORS, FONT } from "../theme";
import { seg, pop, fadeInOut } from "../anim";
import { Avatar } from "../components/ui";

const Bubble: React.FC<{
  side: "l" | "r";
  children: React.ReactNode;
  p: number;
  color?: string;
}> = ({ side, children, p, color }) => (
  <div
    style={{
      alignSelf: side === "r" ? "flex-end" : "flex-start",
      maxWidth: 620,
      background: side === "r" ? color || COLORS.blue : COLORS.card2,
      color: "#fff",
      fontFamily: FONT,
      fontSize: 40,
      lineHeight: 1.3,
      padding: "26px 34px",
      borderRadius: 40,
      borderBottomRightRadius: side === "r" ? 10 : 40,
      borderBottomLeftRadius: side === "l" ? 10 : 40,
      transform: `translateY(${(1 - p) * 40}px) scale(${0.8 + p * 0.2})`,
      opacity: p,
    }}
  >
    {children}
  </div>
);

export const SceneMessaging: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeInOut(frame, dur);

  const b1 = pop(frame, fps, 14);
  const b2 = pop(frame, fps, 34);
  const pay = pop(frame, fps, 58);
  const b3 = pop(frame, fps, 86);
  const badge = pop(frame, fps, 108);
  const labelIn = seg(frame, 130, 155);

  return (
    <AbsoluteFill style={{ opacity }}>
      <Background a={COLORS.green} b={COLORS.blue} />

      {/* chat header */}
      <div style={{ display: "flex", alignItems: "center", gap: 22, padding: "80px 50px 20px" }}>
        <Avatar name="Aisha" size={96} />
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontFamily: FONT, fontWeight: 700, fontSize: 44, color: "#fff" }}>Aisha R.</span>
          <span style={{ fontFamily: FONT, fontSize: 30, color: COLORS.green }}>● Online</span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 28, padding: "40px 50px" }}>
        <Bubble side="l" p={b1}>
          Loved your latest TrustClip 🔥
        </Bubble>
        <Bubble side="r" p={b2}>
          Thank you! 💙 Sending you that split now
        </Bubble>

        {/* payment card */}
        <div
          style={{
            alignSelf: "flex-end",
            width: 560,
            background: `linear-gradient(135deg, ${COLORS.green}, #0aa84f)`,
            borderRadius: 40,
            padding: 40,
            color: "#fff",
            fontFamily: FONT,
            transform: `translateY(${(1 - pay) * 40}px) scale(${0.8 + pay * 0.2})`,
            opacity: pay,
            boxShadow: "0 30px 80px rgba(52,199,89,0.35)",
          }}
        >
          <div style={{ fontSize: 34, opacity: 0.9 }}>TrustWallet · Sent</div>
          <div style={{ fontSize: 96, fontWeight: 800, margin: "6px 0" }}>R250</div>
          <div style={{ fontSize: 32, opacity: 0.9 }}>Delivered instantly ✓</div>
        </div>

        <Bubble side="l" p={b3}>
          Got it! You're the best 🙌
        </Bubble>
      </div>

      {/* badge earned toast */}
      <div
        style={{
          position: "absolute",
          top: 250,
          left: "50%",
          transform: `translateX(-50%) translateY(${(1 - badge) * -40}px) scale(${badge})`,
          opacity: badge,
          display: "flex",
          alignItems: "center",
          gap: 18,
          background: "rgba(255,255,255,0.12)",
          backdropFilter: "blur(16px)",
          border: `1px solid ${COLORS.line}`,
          padding: "20px 34px",
          borderRadius: 100,
          fontFamily: FONT,
          fontWeight: 700,
          fontSize: 38,
          color: "#fff",
        }}
      >
        🏆 Badge earned: Trusted Creator
      </div>

      <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 100 }}>
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 80,
            color: "#fff",
            opacity: labelIn,
            transform: `translateY(${(1 - labelIn) * 30}px)`,
            textShadow: "0 6px 40px rgba(0,0,0,0.8)",
          }}
        >
          Message. Send. Belong.
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
