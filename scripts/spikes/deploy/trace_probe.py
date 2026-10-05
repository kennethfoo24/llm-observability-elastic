"""Step 0E(1): send ONE OTLP/HTTP JSON trace to the local port-forward of the daemon collector."""
import json, os, secrets, time, urllib.request
tid, sid = secrets.token_hex(16), secrets.token_hex(8)
now = time.time_ns()
body = {"resourceSpans": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "deploy-p0-trace-probe"}}]},
  "scopeSpans": [{"scope": {"name": "p0"}, "spans": [{"traceId": tid, "spanId": sid, "name": "p0-probe", "kind": 1,
  "startTimeUnixNano": str(now), "endTimeUnixNano": str(now + 5_000_000),
  "attributes": [{"key": "app.probe", "value": {"stringValue": "p0"}}]}]}]}]}
req = urllib.request.Request(f"http://127.0.0.1:{os.environ.get('PORT','14318')}/v1/traces", data=json.dumps(body).encode(),
                             method="POST", headers={"Content-Type": "application/json"})
print("status", urllib.request.urlopen(req, timeout=15).status, "trace_id", tid)
