import logging
import sys
import time
from pathlib import Path

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from app.config import Settings  # noqa: E402

PROMPT = sys.argv[1] if len(sys.argv) > 1 else "p0 probe prompt"
s = Settings()
exporter = OTLPLogExporter(endpoint=s.obs_otlp_url.rstrip("/") + "/v1/logs",
                           headers={"Authorization": f"ApiKey {s.obs_es_admin_key}"})
provider = LoggerProvider(resource=Resource.create({"service.name": "p0-log-probe"}))
provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
log = logging.getLogger("p0")
log.setLevel(logging.INFO)
log.addHandler(LoggingHandler(logger_provider=provider))
log.info("p0 probe", extra={"data_stream.dataset": "genai_guardrail", "genai.prompt_text": PROMPT})
time.sleep(5)
print("sent")
