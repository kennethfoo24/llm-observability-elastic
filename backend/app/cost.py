from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PRICES_PATH = Path(__file__).resolve().parent.parent / "prices.yaml"


class UnknownModel(KeyError):
    pass


@dataclass(frozen=True)
class Cost:
    input_usd: float
    output_usd: float
    total_usd: float
    basis: str


@lru_cache
def _cached(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def load_prices(path: Path | None = None) -> dict:
    return _cached(str(path or PRICES_PATH))


def compute_cost(model_id: str, input_tokens: int, output_tokens: int,
                 thinking_tokens: int = 0, prices: dict | None = None) -> Cost:
    if min(input_tokens, output_tokens, thinking_tokens) < 0:
        raise ValueError("token counts must be non-negative")
    table = (prices or load_prices())["models"]
    if model_id not in table:
        raise UnknownModel(model_id)
    entry = table[model_id]
    billed_out = output_tokens + thinking_tokens
    if "gpu_hourly_usd" in entry:
        per_token = entry["gpu_hourly_usd"] / entry["assumed_tokens_per_hour"]
        i, o, basis = input_tokens * per_token, billed_out * per_token, "gpu_amortised"
    else:
        i = input_tokens * entry["input_per_mtok"] / 1e6
        o = billed_out * entry["output_per_mtok"] / 1e6
        basis = "per_token"
    return Cost(round(i, 8), round(o, 8), round(i + o, 8), basis)
