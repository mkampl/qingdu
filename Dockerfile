# --- Stage 1: build the Vue 3 frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime ---
FROM python:3.11-slim

WORKDIR /app

# No system-level build deps needed — every requirement installs from a
# prebuilt wheel on this platform (verified directly, not assumed). Used to
# install gcc/g++/ffmpeg/libsndfile1 here for the pronunciation-check
# feature (faster-whisper + librosa); removed with that feature 2026-08-06.

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/data /app/static

# Copy application code + favicons/manifest (still served at /static).
# The Vue 3 frontend supersedes the legacy templates — see Stage 1 build.
COPY app/ /app/app/
COPY static/ /app/static/

# Copy the Vite build artefact from the frontend stage.
COPY --from=frontend-build /build/dist /app/frontend/dist

# Self-host the tesseract.js OCR assets (worker script, WASM core, chi_sim
# language model) instead of letting the client fetch them from
# cdn.jsdelivr.net at runtime — F-Droid disallows apps that download and
# execute unreviewed code post-install. These files already land in
# node_modules via the ordinary `npm ci` in Stage 1, so nothing here makes
# an extra network call beyond what the frontend build already does.
RUN mkdir -p /app/static/tesseract/core /app/static/tesseract/lang
COPY --from=frontend-build /build/node_modules/tesseract.js/dist/worker.min.js /app/static/tesseract/worker.min.js
COPY --from=frontend-build \
    /build/node_modules/tesseract.js-core/tesseract-core-lstm.wasm.js \
    /build/node_modules/tesseract.js-core/tesseract-core-lstm.wasm \
    /build/node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm.js \
    /build/node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm \
    /app/static/tesseract/core/
COPY --from=frontend-build /build/node_modules/@tesseract.js-data/chi_sim/4.0.0_best_int/chi_sim.traineddata.gz /app/static/tesseract/lang/chi_sim.traineddata.gz

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Health check — use urllib (stdlib) so we don't pull in requests/curl
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)" || exit 1

# Single worker: this is a personal-scale deployment, not high-concurrency
# traffic, and every worker independently loads its own copy of jieba's
# dictionary + HSK vocab + CC-CEDICT since uvicorn's workers are spawned,
# not forked (no copy-on-write sharing) — 2 workers meant paying that cost
# twice for no real benefit. (The one CPU-heavy endpoint that used to
# justify hedging on this, /api/pronounce, was removed 2026-08-06 along
# with the rest of the Whisper/librosa pronunciation-check feature.)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
