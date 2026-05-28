# Bundled favicons

These files mirror the repo's `static/` directory (FastAPI serves
those at `/static/*` for the web app). Duplicated here so Vite
bundles them into `dist/` and the Capacitor Android wrapper finds
them at `https://localhost/static/*` — without the mirror the
WebView would `net::ERR_FILE_NOT_FOUND` on every favicon request.

If you update the favicons or the webmanifest, update both copies.
