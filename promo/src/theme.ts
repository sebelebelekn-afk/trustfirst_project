import { loadFont } from "@remotion/google-fonts/Inter";

// Inter — clean, modern, close to the app's SF-style UI. Load only the Latin
// subset and the weights we actually use (keeps it to a handful of requests
// instead of 100+, and renders consistently on the Linux CI runner where
// system fonts like Segoe UI don't exist).
const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "600", "700", "800", "900"],
  subsets: ["latin"],
});
export const FONT = fontFamily;

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
