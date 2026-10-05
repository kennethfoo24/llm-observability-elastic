from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    provider: str   # "eis" (Elastic Inference Service) | "gemma"
    model_id: str
    endpoint: str = ""  # EIS inference endpoint id (chat_completion task)


DEFAULT_MODEL_KEY = "eis-gpt-mini"  # cheapest of the three EIS models in prices.yaml


def get_models(s: Settings) -> dict[str, ModelSpec]:
    return {
        "eis-gpt-mini": ModelSpec("eis-gpt-mini", "GPT-5.4 mini", "eis", "gpt-5.4-mini", s.eis_gpt_mini_endpoint),
        "eis-claude-haiku": ModelSpec("eis-claude-haiku", "Claude 4.5 Haiku", "eis", "claude-4.5-haiku",
                                      s.eis_claude_haiku_endpoint),
        "eis-gemini-flash": ModelSpec("eis-gemini-flash", "Gemini 3.5 Flash", "eis", "gemini-3.5-flash",
                                      s.eis_gemini_flash_endpoint),
        "gemma": ModelSpec("gemma", "Gemma 4 31B (self-hosted)", "gemma", s.gemma_model_id),
    }
