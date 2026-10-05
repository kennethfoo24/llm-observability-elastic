"""Step 0C: mapped types of glassbox trace attributes + ES|QL probe (Observability project)."""
import json
from _es import call

FIELDS = ("attributes.app.genai.cost_usd,attributes.app.persona,attributes.app.genai.model,"
          "attributes.app.genai.engine,attributes.app.guardrail.verdict,attributes.app.guardrail.status,"
          "attributes.app.genai.input_tokens,attributes.app.genai.output_tokens,"
          "attributes.app.genai.thinking_tokens,attributes.app.genai.cost_basis,attributes.app.blocked,"
          "attributes.guardrail.verdict")
# Serverless has no _mapping/field (410); read types from the ES|QL column metadata instead.
s, d = call("observability", "elasticsearch", "POST", "/_query",
            {"query": "FROM traces-generic.otel-default | KEEP attributes.app.*, attributes.guardrail.*, service.name | LIMIT 0"})
print("column types status", s)
if s == 200:
    types = {c["name"]: c["type"] for c in d["columns"]}
    for k in FIELDS.split(","):
        print(" ", k, types.get(k, "(not mapped / no such column)"))
    print("  extra app.* columns:", sorted(set(types) - set(FIELDS.split(","))))
else:
    print(d)

def esql(q):
    s, d = call("observability", "elasticsearch", "POST", "/_query", {"query": q})
    print("ES|QL", s, q[:110])
    if s == 200:
        print("  cols", [(c["name"], c["type"]) for c in d["columns"]])
        for r in d["values"][:10]:
            print("  ", r)
    else:
        print("  ", d)

esql('FROM traces-generic.otel-default | WHERE service.name == "glassbox-backend" AND attributes.app.genai.cost_usd IS NOT NULL | STATS requests = COUNT(*), spend = SUM(attributes.app.genai.cost_usd) BY attributes.app.genai.model | LIMIT 10')
esql('FROM traces-generic.otel-default | WHERE service.name == "glassbox-backend" | STATS n = COUNT(*), oldest = MIN(@timestamp), newest = MAX(@timestamp)')
