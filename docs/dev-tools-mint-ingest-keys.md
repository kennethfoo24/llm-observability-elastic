# Mint ingest-only keys for the guardrail log export

The app exports guardrail prompt logs straight to the managed OTLP endpoint of each project. Give it an
ingest-only key per project instead of the project admin key, so a compromised pod cannot read or change anything.

Run one block in **Kibana, Dev Tools** of the **Observability** project and one in the **Security** project.
Each response has an `encoded` field. Paste the two values into the gitignored file
`backend/secrets/guardrail_log_keys.json` (covered by `.gitignore`, never commit it):

```json
{"obs": "<PASTE encoded value from the Observability response>", "sec": "<PASTE encoded value from the Security response>"}
```

`deploy/scripts/create_secrets.sh` reads that file (or the `GLOG_OBS_KEY` / `GLOG_SEC_KEY` environment variables, which win)
and stores the values in the `glassbox-app` Secret. Do not paste the keys anywhere else. The keys expire after 90 days.

## Observability project

```
POST /_security/api_key
{
  "name": "glassbox-guardrail-log-obs",
  "expiration": "90d",
  "role_descriptors": {
    "guardrail_log_ingest": {
      "cluster": [],
      "indices": [
        {
          "names": ["logs-genai_guardrail.otel-*"],
          "privileges": ["create_doc", "auto_configure", "create_index"]
        }
      ]
    }
  }
}
```

## Security project

```
POST /_security/api_key
{
  "name": "glassbox-guardrail-log-sec",
  "expiration": "90d",
  "role_descriptors": {
    "guardrail_log_ingest": {
      "cluster": [],
      "indices": [
        {
          "names": ["logs-genai_guardrail.otel-*"],
          "privileges": ["create_doc", "auto_configure", "create_index"]
        }
      ]
    }
  }
}
```

Note: the managed OTLP endpoint appends `.otel` to the dataset, so `genai_guardrail` lands in `logs-genai_guardrail.otel-default`.
After deploying, confirm one log arrives in each project; if the endpoint answers 403, widen the index names in the role
and mint the key again (do not fall back to the admin key).
