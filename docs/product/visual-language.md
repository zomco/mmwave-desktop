# MMWave family appearance

[中文](visual-language_CN.md)

TraceCue uses the MMWave DIY flasher's visual language while retaining its name, local-first positioning and existing five navigation destinations. This is a presentation change, not a runtime dependency on Home Assistant or Fusion.

`desktop/frontend/src/styles.css` defines the brand palette (`#0b825c` primary), light/dark surface, text, border and semantic status tokens. `ui.tsx` owns shared buttons, fields, cards, badges, headers, focus states and outlined icons. Surfaces use 16 px radii, fields 10 px, buttons 8 px; controls are 40–44 px tall. The font stack is DM Sans / Noto Sans SC / system, without downloading fonts. Main text is 14 px, supporting text at least 12 px, titles 24–30 px and weight 600. Numeric/technical data may use monospace.

All five pages use these tokens. Timeline density stays green, selection remains amber and drag preview blue; camera overlays retain distinguishable categorical colors and thin strokes. Media itself is never recolored. The token-scoped phone share page uses the same palette and follows system appearance; sharing permissions, expiry, escaping and routes are unchanged.

The sidebar cycles System → Light → Dark, persisted under `tracecue.theme.v1`; inaccessible storage falls back to an in-memory choice. Reduced-motion preferences disable decorative transitions/spinners, not status text or data updates. Keyboard focus and disabled/destructive actions remain distinguishable.

## Check without devices

From `desktop/frontend`, run `npm run dev -- --port 5175`, then open `/test/visual.html`. It renders production components with simulated API responses and rejects all device writes. Open `/test/visual.html?populated#trace` to inspect the search form with a simulated recorder; camera images are intentionally unavailable. The preview is typechecked but is not a production build entry. Check all navigation views, forms, timeline, theme switching, keyboard focus and narrow/wide widths. Run `npm test`, `npm run build`, the backend sharing test, and `python scripts/ci/verify_repo.py` from the repository root. Real NVR playback, HA-native controls and hardware actions are separate acceptance tests.
