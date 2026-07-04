import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { COLORS, FONT } from "../theme";
import { seg, fadeInOut, pop } from "../anim";
import { Avatar, VerifiedBadge } from "../components/ui";

const Rail: React.FC<{ icon: string; label: string; pulse?: number }> = ({ icon, label, pulse = 0 }) => (
  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
    <div style={{ fontSize: 72, transform: `scale(${1 + pulse * 0.3})` }}>{icon}</div>
    <span style={{ fontFamily: FONT, fontWeight: 700, fontSize: 30, color: "#fff" }}>{label}</span>
  </div>
);

export const SceneClips: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeInOut(frame, dur);

  // clip "swipe" — a second clip slides up at ~mid
  const swipe = seg(frame, 130, 155, 0, -1920);
  const heart = pop(frame, fps, 70);
  const likeCount = Math.round(interpolate(frame, [70, 110], [8420, 9337], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const titleIn = seg(frame, 10, 34);

  const clip = (author: string, grad: string[], cap: string, likes: string, hb = 0) => (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: `linear-gradient(160deg, ${grad[0]}, ${grad[1]})` }} />
      <AbsoluteFill style={{ background: "linear-gradient(transparent 55%, rgba(0,0,0,0.7))" }} />
      {/* play glyph pulse */}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 150, color: "rgba(255,255,255,0.25)" }}>▶</div>
      </AbsoluteFill>
      {/* right rail */}
      <div
        style={{
          position: "absolute",
          right: 40,
          bottom: 320,
          display: "flex",
          flexDirection: "column",
          gap: 54,
          alignItems: "center",
        }}
      >
        <Avatar name={author} size={110} ring />
        <Rail icon="❤️" label={likes} pulse={hb} />
        <Rail icon="💬" label="1.2k" />
        <Rail icon="↗" label="Share" />
      </div>
      {/* caption */}
      <div style={{ position: "absolute", left: 50, right: 240, bottom: 300 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <span style={{ fontFamily: FONT, fontWeight: 800, fontSize: 42, color: "#fff" }}>@{author.toLowerCase()}</span>
          <VerifiedBadge size={36} />
        </div>
        <div style={{ fontFamily: FONT, fontSize: 38, color: "#fff", lineHeight: 1.35 }}>{cap}</div>
        <div style={{ fontFamily: FONT, fontSize: 32, color: "rgba(255,255,255,0.85)", marginTop: 18 }}>
          ♫ Original audio — {author}
        </div>
      </div>
    </AbsoluteFill>
  );

  return (
    <AbsoluteFill style={{ opacity, backgroundColor: "#000" }}>
      <div style={{ transform: `translateY(${swipe}px)`, height: "100%" }}>
        {clip("Lerato", ["#FF2D92", "#5856D6"], "POV: your first verified post goes viral ✨", likeCount.toLocaleString(), heart)}
      </div>
      <div style={{ position: "absolute", top: 1920, left: 0, right: 0, height: "100%", transform: `translateY(${swipe}px)` }}>
        {clip("Themba", ["#007AFF", "#00C6FB"], "Behind the scenes of my studio 🎬", "12.4k")}
      </div>

      {/* title */}
      <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "center", paddingTop: 90 }}>
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 80,
            color: "#fff",
            opacity: titleIn,
            transform: `translateY(${(1 - titleIn) * -30}px)`,
            textShadow: "0 6px 40px rgba(0,0,0,0.8)",
          }}
        >
          TrustClips
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
