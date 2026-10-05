import pytest

from app.config import Settings
from app.cost import load_prices
from app.models import DEFAULT_MODEL_KEY, get_models


@pytest.fixture
def s(monkeypatch):
    for k, v in {"OBS_ES_URL": "https://e", "OBS_ES_ADMIN_KEY": "k", "OBS_KIBANA_URL": "https://k"}.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


def test_registry_has_exactly_the_three_eis_models_and_gemma(s):
    m = get_models(s)
    assert list(m) == ["eis-gpt-mini", "eis-claude-haiku", "eis-gemini-flash", "gemma"]
    assert [m[k].label for k in list(m)[:3]] == ["GPT-5.4 mini", "Claude 4.5 Haiku", "Gemini 3.5 Flash"]
    assert all(m[k].provider == "eis" and m[k].endpoint.startswith(".") and m[k].endpoint.endswith("-chat_completion")
               for k in list(m)[:3])
    assert m["gemma"].provider == "gemma"


def test_every_model_is_priced_and_the_default_is_the_cheapest_eis_model(s):
    prices = load_prices()["models"]
    models = get_models(s)
    assert all(x.model_id in prices for x in models.values())
    eis = [x for x in models.values() if x.provider == "eis"]
    cheapest = min(eis, key=lambda x: prices[x.model_id]["input_per_mtok"] + prices[x.model_id]["output_per_mtok"])
    assert DEFAULT_MODEL_KEY == cheapest.key
