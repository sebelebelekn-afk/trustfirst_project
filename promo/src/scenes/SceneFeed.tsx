import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT } from "../theme";
import { seg, fadeInOut, ease } from "../anim";
import { Avatar, VerifiedBadge } from "../components/ui";
import { InfinityLogo } from "../components/InfinityLogo";

const STORIES = ["You", "Naledi", "Sipho", "Aisha", "Themba", "Lerato"];
const POSTS = [
  { name: "Naledi M.", handle: "@naledi", grad: ["#5856D6", "#007AFF"], cap: "Golden hour in Jozi 🌇", likes: "2,481", cmt: "312" },
  { name: "Sipho K.", handle: "@siphok", grad: ["#FF9500", "#FF2D92"], cap: "New studio, who dis 🎧", likes: "5,102", cmt: "740" },
  { name: "Aisha R.", handle: "@aisha", grad: ["#34C759", "#007AFF"], cap: "Morning run done ✅", likes: "1,209", cmt: "88" },
];

export const SceneFeed: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeInOut(frame, dur);
  const uiIn = ease(frame, fps, 4);
  const scroll = seg(frame, 40, dur - 20, 0, 720); // scroll feed upward
  const labelIn = seg(frame, 12, 34);

  return (
    <AbsoluteFill style={{ opacity, backgroundColor: COLORS.ink }}>
      <AbsoluteFill style={{ transform: `translateY(${(1 - uiIn) * 60}px)`, opacity: uiIn }}>
        {/* top bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "70px 50px 24px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <InfinityLogo size={78} glow={false} strokeWidth={80} />
            <span style={{ fontFamily: FONT, fontWeight: 800, fontSize: 52, color: "#fff" }}>
              Trust<span style={{ color: COLORS.blue }}>First</span>
            </span>
          </div>
          <div style={{ display: "flex", gap: 30, fontSize: 44, color: "#fff" }}>♡ ✉</div>
        </div>

        {/* stories row */}
        <div style={{ display: "flex", gap: 30, padding: "10px 50px 26px", overflow: "hidden" }}>
          {STORIES.map((s) => (
            <div key={s} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
              <Avatar name={s} size={130} ring />
              <span style={{ fontFamily: FONT, fontSize: 26, color: COLORS.gray }}>{s}</span>
            </div>
          ))}
        </div>
        <div style={{ height: 1, background: COLORS.line }} />

        {/* feed */}
        <div style={{ transform: `translateY(${-scroll}px)` }}>
          {POSTS.concat(POSTS).map((p, i) => (
            <div key={i} style={{ padding: "30px 50px 10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 22 }}>
                <Avatar name={p.name} size={92} />
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontFamily: FONT, fontWeight: 700, fontSize: 38, color: "#fff" }}>
                      {p.name}
                    </span>
                    <VerifiedBadge size={34} />
                  </div>
                  <span style={{ fontFamily: FONT, fontSize: 28, color: COLORS.gray }}>{p.handle}</span>
                </div>
              </div>
              <div
                style={{
                  height: 620,
                  borderRadius: 36,
                  background: `linear-gradient(135deg, ${p.grad[0]}, ${p.grad[1]})`,
                }}
              />
              <div style={{ display: "flex", gap: 44, padding: "26px 6px 6px", fontFamily: FONT, fontSize: 40, color: "#fff" }}>
                <span>♥ {p.likes}</span>
                <span>💬 {p.cmt}</span>
                <span>↗</span>
              </div>
              <div style={{ fontFamily: FONT, fontSize: 34, color: "#fff", padding: "4px 6px 20px" }}>
                <b>{p.handle}</b> {p.cap}
              </div>
            </div>
          ))}
        </div>
      </AbsoluteFill>

      {/* label */}
      <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 90 }}>
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 76,
            color: "#fff",
            textAlign: "center",
            opacity: labelIn,
            transform: `translateY(${(1 - labelIn) * 30}px)`,
            textShadow: "0 6px 40px rgba(0,0,0,0.8)",
          }}
        >
          A feed you can<br /> believe in.
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
