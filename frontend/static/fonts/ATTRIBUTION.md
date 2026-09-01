# Font attribution

Self-hosted here (not loaded from a CDN) so the app keeps working fully
offline and the CSP's `style-src`/`default-src 'self'` policy doesn't
need a third-party exception — the same reasoning already applied to
vendoring Chart.js locally (see `frontend/static/js/vendor/`).

- **Inter** — Copyright 2016 The Inter Project Authors
  (https://github.com/rsms/inter)
- **JetBrains Mono** — Copyright 2020 The JetBrains Mono Project
  Authors (https://github.com/JetBrains/JetBrainsMono)

Both licensed under the SIL Open Font License, Version 1.1
(https://scripts.sil.org/OFL), which permits redistribution as part of
this software. Files extracted from the `@fontsource/inter` and
`@fontsource/jetbrains-mono` npm packages (Latin subset, woff2, static
weights only — no variable-font axes, no italics — to keep the total
footprint small).
