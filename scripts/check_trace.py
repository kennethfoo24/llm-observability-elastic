import sys
from pathlib import Path

from elasticsearch import Elasticsearch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import Settings  # noqa: E402

s = Settings()
es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
if len(sys.argv) > 1:
    tid = sys.argv[1]  # check a specific trace (the response's trace_id)
else:
    last = es.search(index="traces-*", query={"exists": {"field": "attributes.app.persona"}},
                     sort=[{"@timestamp": "desc"}], size=1)["hits"]["hits"]
    if not last:
        sys.exit("no traced chat request found yet (wait ~30s and retry)")
    tid = last[0]["_source"]["trace_id"]
spans = es.search(index="traces-*", query={"term": {"trace_id": tid}}, size=100, sort=[{"@timestamp": "asc"}])["hits"]["hits"]
print("trace", tid, "-", len(spans), "spans")
found_prompt = False
for h in spans:
    a = h["_source"].get("attributes", {})
    has = any(k.startswith("gen_ai.input.messages") or k.startswith("gen_ai") and "input" in k and "messages" in k for k in a)
    found_prompt |= has
    print(f"  {h['_source']['span_id'][:6]} <- {str(h['_source'].get('parent_span_id'))[:6]:<6} {h['_source'].get('name'):<34} cost={a.get('app.genai.cost_usd')} in_tok={a.get('gen_ai.usage.input_tokens')} prompt_captured={has}")
print("PROMPT CONTENT CAPTURED:", found_prompt)
