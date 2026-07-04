# TrustFirst — 60s Promo (Remotion)

A programmatic, re-renderable motion-graphics promo for TrustFirst. Renders to a
real **1080×1920 MP4** (vertical, ideal for Reels/TikTok/Shorts + app stores).

## Setup

```bash
cd promo
npm install
```

## Preview / edit live

```bash
npm run studio
```

Opens Remotion Studio in the browser — scrub the timeline, tweak any scene, see
changes instantly. Scene files live in `src/scenes/`.

## Render the video

```bash
npm run render        # → out/trustfirst-promo.mp4  (h264, CRF 18)
npm run render:hq     # → out/trustfirst-promo-hq.mp4 (CRF 16, larger/cleaner)
```

Remotion ships its own ffmpeg — nothing else to install.

## Scene plan (60s @ 30fps)

| Time | Scene | Content |
|------|-------|---------|
| 0–6s  | Intro     | Infinity logo draws on, "TrustFirst" |
| 6–14s | Hook      | "Social media forgot one thing" → **TRUST** |
| 14–24s| Verify    | Face-scan → blue verified badge (KYC) |
| 24–34s| Feed      | Stories ring + scrolling verified feed |
| 34–44s| TrustClips| Vertical reel with like/comment/share rail |
| 44–52s| Messaging | Chat + TrustWallet payment + badge earned |
| 52–60s| CTA       | Logo, "Join TrustFirst", URL |

## Customize

- **URL / call-to-action:** `src/scenes/SceneCTA.tsx` (top constant `URL`).
- **Colors:** `src/theme.ts`.
- **Copy / timing:** each `src/scenes/Scene*.tsx`.
- **Music:** drop an mp3 in `public/`, then add
  `<Audio src={staticFile("music.mp3")} />` inside `src/Promo.tsx`
  (import `Audio`, `staticFile` from `remotion`). Use a licensed track.
- **Landscape version:** change `width/height` in `src/theme.ts` to `1920×1080`
  (scenes are built responsively but will need minor spacing tweaks).
