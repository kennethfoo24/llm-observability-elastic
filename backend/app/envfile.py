MAPPING = {
    "OBSERVABILITY_ELASTICSEARCH": "OBS_ES_URL",
    "OBSERVABILITY_API_KEY": "OBS_ES_ADMIN_KEY",
    "OBSERVABILITY_KIBANA": "OBS_KIBANA_URL",
    "OBSERVABILITY_OPENTELEMETRY": "OBS_OTLP_URL",
    "SECURITY_ELASTICSEARCH": "SEC_ES_URL",
    "SECURITY_API_KEY": "SEC_ES_ADMIN_KEY",
    "SECURITY_KIBANA": "SEC_KIBANA_URL",
}


def parse_env_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and " " not in key:
            out[key] = value.strip()
    return out


def to_app_env(raw: dict[str, str]) -> dict[str, str]:
    return {new: raw[old] for old, new in MAPPING.items() if old in raw}
