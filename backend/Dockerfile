FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
COPY prices.yaml ./
RUN pip install --no-cache-dir -e . && (edot-bootstrap --action=install || true)
ENV OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY \
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=openai \
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true \
    OTEL_SERVICE_NAME=glassbox-backend
EXPOSE 8000
CMD ["opentelemetry-instrument", "uvicorn", "app.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
