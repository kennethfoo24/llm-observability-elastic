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

    eis_gemini_flash_endpoint: str = ".google-gemini-3.5-flash-chat_completion"
    eis_claude_haiku_endpoint: str = ".anthropic-claude-4.5-haiku-chat_completion"
    eis_gpt_mini_endpoint: str = ".openai-gpt-5.4-mini-chat_completion"
    eis_max_tokens: int = 2048  # max_completion_tokens per EIS chat call (bounds cost; thinking tokens count against it)
    gemma_base_url: str = "https://llm-34-126-172-79.nip.io/v1"
    gemma_api_key: str = ""
    gemma_model_id: str = "google/gemma-4-31B-it"

    injection_model_id: str = "protectai__deberta-v3-base-prompt-injection-v2"
    ner_model_id: str = "elastic__distilbert-base-cased-finetuned-conll03-english"
    guardrail_timeout_s: float = 1.5
    max_message_chars: int = 4000
    app_password: str = ""

    llm_timeout_s: float = 60.0
    rate_limit_per_min: int = 120
    chat_rate_limit_per_min: int = 20
    auth_fail_limit: int = 10
    auth_fail_window_s: int = 300
    trusted_proxy_hops: int = 1

    # Direct OTLP/HTTP export of guardrail prompt logs to Observability and Security (empty = disabled)
    guardrail_log_obs_endpoint: str = ""
    guardrail_log_obs_key: str = ""
    guardrail_log_sec_endpoint: str = ""
    guardrail_log_sec_key: str = ""

    @property
    def guardrail_es_key(self) -> str:
        return self.obs_es_guardrail_key or self.obs_es_admin_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
