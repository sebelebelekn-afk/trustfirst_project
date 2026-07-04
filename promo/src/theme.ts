// System font stack — zero network requests during render (fast + reliable on
// a slow/flaky connection). Segoe UI on the Windows render host closely matches
// the app's SF-style UI. Avoids @remotion/google-fonts making 100+ requests.
export const FONT =
  '"Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Roboto, Arial, sans-serif';

export const COLORS = {
  blue: "#007AFF",
  purple: "#5856D6",
  orange: "#FF9500",
  green: "#34C759",
  red: "#FF3B30",
  pink: "#FF2D92",
  ink: "#07070c", // near-black background
  dark: "#1a1a1a", // brand square background
  card: "#16161c",
  card2: "#1f1f27",
  white: "#ffffff",
  gray: "#8e8e93",
  line: "rgba(255,255,255,0.08)",
};

// Brand gradient used across the promo.
export const BRAND_GRADIENT = `linear-gradient(120deg, ${COLORS.purple}, ${COLORS.blue} 55%, ${COLORS.orange})`;

export const VIDEO = {
  width: 1080,
  height: 1920,
  fps: 30,
  durationInFrames: 30 * 60, // 60 seconds
};
