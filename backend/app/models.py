from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    provider: str   # "vertex" | "gemma"
    model_id: str


def get_models(s: Settings) -> dict[str, ModelSpec]:
    return {
        "flash-lite": ModelSpec("flash-lite", "Gemini Flash-Lite", "vertex", s.gemini_flash_lite_id),
        "flash": ModelSpec("flash", "Gemini Flash", "vertex", s.gemini_flash_id),
        "gemma": ModelSpec("gemma", "Gemma 4 31B (self-hosted)", "gemma", s.gemma_model_id),
    }
