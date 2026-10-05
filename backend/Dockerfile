# node:22-slim, digest resolved 2026-10-05 (multi-arch index digest)
FROM node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# python:3.12-slim, digest resolved 2026-10-04 (multi-arch index digest)
FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016
WORKDIR /srv
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/prices.yaml ./
RUN pip install --no-cache-dir --no-deps -e .
# edot-bootstrap adds the instrumentation packages for the libraries installed above (fastapi, httpx, ...).
# It also installs elastic-opentelemetry-instrumentation-openai, which registers under the same
# entry-point name (`openai`) as the official opentelemetry-instrumentation-genai-openai. Remove the
# Elastic one so the official gen_ai instrumentor (Gemma / openai-client calls) is the one that loads.
# No `|| true`: a failed bootstrap must fail the build, otherwise the fastapi server span (and the
# cost/persona attributes set on it) silently disappears.
# `pip show` with several names succeeds if any one exists, so each package is checked on its own.
RUN edot-bootstrap --action=install \
    && pip uninstall -y elastic-opentelemetry-instrumentation-openai \
    && pip show opentelemetry-instrumentation-fastapi >/dev/null \
    && pip show opentelemetry-instrumentation-genai-openai >/dev/null \
    && ! pip show elastic-opentelemetry-instrumentation-openai >/dev/null 2>&1
# Built UI; create_app's default static_dir (app/../frontend/dist) resolves to /srv/frontend/dist.
COPY --from=ui /ui/dist /srv/frontend/dist
RUN chown -R app:app /srv
ENV OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY \
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true \
    OTEL_SERVICE_NAME=glassbox-backend
USER 10001
EXPOSE 8000
CMD ["opentelemetry-instrument", "uvicorn", "app.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
