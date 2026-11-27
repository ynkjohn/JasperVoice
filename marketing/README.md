# JasperVoice — marketing videos (Remotion)

Two 30-second, 1080p (1920×1080 @ 30fps) marketing videos built from scratch
with [Remotion](https://www.remotion.dev). They mirror the JasperVoice design
tokens (`src/theme.ts`, based on `src/jaspervoice/theme.py`) and recreate the
overlay-pill behavior for deterministic footage that matches the product.

| Composition | What it shows |
|---|---|
| **`PillDemo`** | Cinematic end-to-end: a chat app + the hotkey, then a zoom into the overlay pill running Listening → Processing → Sent, then a pan to the chat as the dictated text types itself in. |
| **`AppTour`** | A guided tour of the settings window — Overview, History, Model & Engine, AI Polish, Dictionary — with the live pill floating in the corner. |

The spectrum bars in the pill and the animated backdrop are drawn on an HTML
`<canvas>` (`src/components/Pill.tsx`, `src/components/Background.tsx`).

## Develop

```bash
npm install
npm run dev          # open Remotion Studio
```

## Render

```bash
npx remotion render PillDemo out/JasperVoice-demo.mp4
npx remotion render AppTour  out/JasperVoice-tour.mp4

# poster frames used in the repo README
npx remotion still PillDemo out/poster-demo.png --frame=235
npx remotion still AppTour  out/poster-tour.png --frame=150
```

Final assets are committed to `../docs/media/` and referenced from the top-level
`README.md`.
