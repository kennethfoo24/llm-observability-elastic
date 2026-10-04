import pytest

from app.cost import UnknownModel, compute_cost

PRICES = {
    "models": {
        "gemini-3.1-flash-lite": {"input_per_mtok": 0.25, "output_per_mtok": 1.50},
        "google/gemma-4-31B-it": {"gpu_hourly_usd": 6.0, "assumed_tokens_per_hour": 1_200_000},
    }
}


def test_per_token_cost():
    c = compute_cost("gemini-3.1-flash-lite", 3000, 400, prices=PRICES)
    assert c.input_usd == pytest.approx(0.00075)
    assert c.output_usd == pytest.approx(0.0006)
    assert c.total_usd == pytest.approx(0.00135)
    assert c.basis == "per_token"


def test_thinking_tokens_billed_as_output():
    c = compute_cost("gemini-3.1-flash-lite", 0, 100, thinking_tokens=900, prices=PRICES)
    assert c.output_usd == pytest.approx(1000 * 1.50 / 1e6)


def test_gpu_amortised_gemma():
    c = compute_cost("google/gemma-4-31B-it", 600_000, 600_000, prices=PRICES)
    assert c.total_usd == pytest.approx(6.0 / 1_200_000 * 1_200_000)
    assert c.basis == "gpu_amortised"


def test_zero_tokens_cost_zero():
    assert compute_cost("gemini-3.1-flash-lite", 0, 0, prices=PRICES).total_usd == 0


def test_unknown_model():
    with pytest.raises(UnknownModel):
        compute_cost("nope", 1, 1, prices=PRICES)


def test_negative_tokens_rejected():
    with pytest.raises(ValueError):
        compute_cost("gemini-3.1-flash-lite", -1, 0, prices=PRICES)


def test_shipped_prices_have_no_zero_price_placeholders():
    from app.cost import load_prices
    for name, e in load_prices()["models"].items():
        if "input_per_mtok" in e:
            assert e["input_per_mtok"] > 0 and e["output_per_mtok"] > 0, name


def test_empty_prices_table_is_respected_not_replaced_by_shipped_prices():
    with pytest.raises(UnknownModel):
        compute_cost("gemini-3.1-flash-lite", 1, 1, prices={"models": {}})
