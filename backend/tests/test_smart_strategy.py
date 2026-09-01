from types import SimpleNamespace

from backend.app.smart_scoring import strategy_match, profile_score_from_components


def stock(**kwargs):
    values={
        "per":None,"pbr":None,"roe":None,"revenue_growth":None,
        "momentum_20d":None,"dividend_yield":None,"volatility":None,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_all_strategy_never_crashes_or_filters():
    assert strategy_match(stock(), "전체") is True

def test_value_strategy():
    assert strategy_match(stock(per=10), "가치") is True
    assert strategy_match(stock(per=30,pbr=3), "가치") is False

def test_growth_strategy():
    assert strategy_match(stock(revenue_growth=15), "성장") is True

def test_momentum_dividend_stability_strategies():
    assert strategy_match(stock(momentum_20d=6), "모멘텀") is True
    assert strategy_match(stock(dividend_yield=3), "배당") is True
    assert strategy_match(stock(volatility=3,roe=8), "안정") is True

def test_mapping_and_bad_numeric_values_are_safe():
    assert strategy_match({"per":"not-a-number","pbr":1.2}, "가치") is True
    assert strategy_match({"momentum_20d":"bad"}, "모멘텀") is False

def test_malformed_component_entries_do_not_break_profile_scoring_contract():
    # profile scorer itself remains valid for the normalized dict-only list used by API cache reader.
    result=profile_score_from_components([],profile_scores={"percentages":{}},profile_code="LAVHF")
    assert result["score"] is None
