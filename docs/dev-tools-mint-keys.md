# Mint the LLM Observability API keys in Kibana Dev Tools

Run these in **Kibana → Dev Tools** of the **Observability** project (they run as you, so they can create keys with their own privileges).
Each response contains an `encoded` field. Copy the `encoded` value of each key into `backend/secrets/persona_keys.json` as:

```json
{"employee": "<encoded>", "manager": "<encoded>", "hr": "<encoded>", "exec": "<encoded>", "catalog": "<encoded>", "guardrail": "<encoded>"}
```

The file is gitignored; do not paste the keys anywhere else. `guardrail` is the restricted key the app will use for the `_infer` calls instead of the project admin key; its privileges (`monitor_ml`, `monitor_inference`) are an assumption to confirm with one `_infer` call.

```
POST /_security/api_key
{
  "name": "glassbox-employee",
  "expiration": "90d",
  "role_descriptors": {
    "employee": {
      "cluster": [
        "monitor_inference"
      ],
      "indices": [
        {
          "names": [
            "hr-kb"
          ],
          "privileges": [
            "read"
          ],
          "query": {
            "terms": {
              "allowed_roles": [
                "employee"
              ]
            }
          }
        }
      ]
    }
  }
}

POST /_security/api_key
{
  "name": "glassbox-manager",
  "expiration": "90d",
  "role_descriptors": {
    "manager": {
      "cluster": [
        "monitor_inference"
      ],
      "indices": [
        {
          "names": [
            "hr-kb"
          ],
          "privileges": [
            "read"
          ],
          "query": {
            "terms": {
              "allowed_roles": [
                "manager"
              ]
            }
          }
        }
      ]
    }
  }
}

POST /_security/api_key
{
  "name": "glassbox-hr",
  "expiration": "90d",
  "role_descriptors": {
    "hr": {
      "cluster": [
        "monitor_inference"
      ],
      "indices": [
        {
          "names": [
            "hr-kb"
          ],
          "privileges": [
            "read"
          ],
          "query": {
            "terms": {
              "allowed_roles": [
                "hr"
              ]
            }
          }
        }
      ]
    }
  }
}

POST /_security/api_key
{
  "name": "glassbox-exec",
  "expiration": "90d",
  "role_descriptors": {
    "exec": {
      "cluster": [
        "monitor_inference"
      ],
      "indices": [
        {
          "names": [
            "hr-kb"
          ],
          "privileges": [
            "read"
          ],
          "query": {
            "terms": {
              "allowed_roles": [
                "exec"
              ]
            }
          }
        }
      ]
    }
  }
}

POST /_security/api_key
{
  "name": "glassbox-catalog",
  "expiration": "90d",
  "role_descriptors": {
    "catalog": {
      "cluster": [
        "monitor_inference"
      ],
      "indices": [
        {
          "names": [
            "hr-kb"
          ],
          "privileges": [
            "read"
          ],
          "field_security": {
            "grant": [
              "title",
              "classification",
              "allowed_roles",
              "content",
              "content_semantic"
            ]
          }
        }
      ]
    }
  }
}

POST /_security/api_key
{
  "name": "glassbox-guardrail",
  "expiration": "90d",
  "role_descriptors": {
    "guardrail": {
      "cluster": [
        "monitor_ml",
        "monitor_inference"
      ],
      "indices": []
    }
  }
}

```
