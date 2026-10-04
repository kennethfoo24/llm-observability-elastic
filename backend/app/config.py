from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    obs_es_url: str
    obs_es_admin_key: str
    obs_kibana_url: str
    obs_es_guardrail_key: str = ""  # optional ML-infer-only key for the inline guardrail; falls back to admin
    obs_otlp_url: str = ""
    sec_es_url: str = ""
    sec_es_admin_key: str = ""
    sec_kibana_url: str = ""

    index_name: str = "hr-kb"
    persona_keys_path: str = "secrets/persona_keys.json"

    vertex_project: str = "elastic-sa"
    vertex_location: str = "global"
    gemini_flash_lite_id: str = "gemini-3.1-flash-lite"
    gemini_flash_id: str = "gemini-3.5-flash"  # in the 12-month-availability table of the Vertex model-versions page (fetched 2026-10-04); newer 3.6-3.8 are short-term-availability models
    gemma_base_url: str = "https://llm-34-126-172-79.nip.io/v1"
    gemma_api_key: str = ""
    gemma_model_id: str = "google/gemma-4-31B-it"

    injection_model_id: str = "protectai__deberta-v3-base-prompt-injection-v2"
    ner_model_id: str = "elastic__distilbert-base-cased-finetuned-conll03-english"
    guardrail_timeout_s: float = 1.5
    max_message_chars: int = 4000
    app_password: str = ""

    @property
    def guardrail_es_key(self) -> str:
        return self.obs_es_guardrail_key or self.obs_es_admin_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
