import { interpolate, spring } from "remotion";

/** Simple clamped interpolation between two frames. */
export const seg = (
  frame: number,
  from: number,
  to: number,
  a = 0,
  b = 1
): number =>
  interpolate(frame, [from, to], [a, b], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

/** Fade in at the start and out at the end of a sequence of length `dur`. */
export const fadeInOut = (frame: number, dur: number, inLen = 14, outLen = 16): number =>
  interpolate(frame, [0, inLen, dur - outLen, dur], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

/** Bouncy spring pop, optionally delayed. */
export const pop = (frame: number, fps: number, delay = 0): number =>
  spring({
    frame: frame - delay,
    fps,
    config: { damping: 13, mass: 0.7, stiffness: 130 },
  });

/** Smooth (non-bouncy) spring, optionally delayed. */
export const ease = (frame: number, fps: number, delay = 0): number =>
  spring({
    frame: frame - delay,
    fps,
    config: { damping: 200, mass: 1, stiffness: 100 },
  });
