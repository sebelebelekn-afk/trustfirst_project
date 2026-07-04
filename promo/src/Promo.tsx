import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { COLORS } from "./theme";
import { SceneIntro } from "./scenes/SceneIntro";
import { SceneHook } from "./scenes/SceneHook";
import { SceneVerify } from "./scenes/SceneVerify";
import { SceneFeed } from "./scenes/SceneFeed";
import { SceneClips } from "./scenes/SceneClips";
import { SceneMessaging } from "./scenes/SceneMessaging";
import { SceneCTA } from "./scenes/SceneCTA";

// Scene plan (30fps) — durations sum to 1800 frames = 60.0s.
const SCENES: { c: React.FC<{ dur: number }>; dur: number }[] = [
  { c: SceneIntro, dur: 180 }, // 0–6s   logo reveal
  { c: SceneHook, dur: 240 }, // 6–14s   the problem → TRUST
  { c: SceneVerify, dur: 300 }, // 14–24s verified identity / KYC
  { c: SceneFeed, dur: 300 }, // 24–34s  feed & stories
  { c: SceneClips, dur: 300 }, // 34–44s TrustClips
  { c: SceneMessaging, dur: 240 }, // 44–52s messaging + wallet + badges
  { c: SceneCTA, dur: 240 }, // 52–60s  call to action
];

export const Promo: React.FC = () => {
  let from = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.ink }}>
      {SCENES.map((s, i) => {
        const el = (
          <Sequence key={i} from={from} durationInFrames={s.dur}>
            <s.c dur={s.dur} />
          </Sequence>
        );
        from += s.dur;
        return el;
      })}
    </AbsoluteFill>
  );
};
