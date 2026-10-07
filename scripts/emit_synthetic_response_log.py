"""Send ONE synthetic `genai_response` log to both Elastic projects through the app's own OTLP path
(telemetry.setup_guardrail_log_export + emit_response_log). Endpoints and keys come from elastic/client.py;
nothing is printed except the persona and trace marker. The persona is `synthetic-test` so the docs are identifiable."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app import telemetry  # noqa: E402

from elastic.client import Project  # noqa: E402

CONTEXT = ("[hr-001] Annual leave: Employees receive 18 days of paid annual leave per year, accruing monthly. "
           "Unused leave up to 5 days carries over.")


def main(flagged: bool = False) -> None:
    obs, sec = Project("observability"), Project("security")
    s = SimpleNamespace(guardrail_log_obs_endpoint=obs.otlp, guardrail_log_obs_key=obs._key,
                        guardrail_log_sec_endpoint=sec.otlp, guardrail_log_sec_key=sec._key)
    handlers = telemetry.setup_guardrail_log_export(s, simple=True)
    response = "You get 18 days of paid annual leave per year [hr-001]."
    if flagged:   # trips all three Security rules (LLM02, LLM05, LLM07); the canary is read from the gitignored file, never printed
        from elastic.apply import read_canary
        response = (f"Synthetic test: mail synthetic.person@example.com <script>alert(1)</script> {read_canary()} "
                    "[click](http://example.invalid/x)")
    telemetry.emit_response_log(
        prompt="How many days of annual leave do I get? (synthetic test)",
        response=response, context=CONTEXT,
        retrieved_ids=["hr-001"], cited_ids=["hr-001"], top_score=0.82, hidden_count=0, top_hidden_score=0.0,
        answered=True, persona="synthetic-test", model="synthetic", engine="synthetic")
    time.sleep(2)
    for p in telemetry._PROVIDERS:
        p.force_flush()
    print(f"emitted one synthetic{' FLAGGED' if flagged else ''} response log through {len(handlers)} exporters")


if __name__ == "__main__":
    main(flagged="--flagged" in sys.argv[1:])
