from backend.app.smart_scoring import build_scorecard


def sample_stock():
    return {
        "code":"000001",
        "name":"테스트",
        "roe":18,
        "revenue_growth":15,
        "operating_margin":14,
        "per":11,
        "pbr":1.1,
        "dividend_yield":2.5,
        "momentum_20d":8,
        "change_rate":1.2,
        "volatility":2.2,
        "market_cap":120000,
    }


def test_scorecard_exposes_ai_and_profile_separately():
    result=build_scorecard(
        sample_stock(),
        flow={"days":5,"foreign_net":1000,"institution_net":500,"positive_days":4,"net_ratio":35},
        sentiment={"positive":6,"neutral":2,"negative":1,"news":7,"reports":2},
        profile_scores={"percentages":{
            "horizon":{"L":75,"N":20,"S":5},
            "risk":{"A":20,"D":80},
            "value":{"G":35,"V":65},
            "profit":{"P":30,"H":70},
            "spread":{"F":20,"M":80},
        }},
        profile_code="LDVHM",
    )
    assert 0 <= result["ai_score"] <= 100
    assert 0 <= result["profile_score"] <= 100
    assert result["ai_score"] != result["profile_score"]
    assert len(result["components"]) == 6
    assert {x["key"] for x in result["components"]} == {"financial","valuation","momentum","flow","sentiment","stability"}
    assert all("ai_view" in x and "profile_view" in x for x in result["components"])


def test_scorecard_without_profile_keeps_ai_score():
    result=build_scorecard(sample_stock())
    assert result["ai_score"] > 0
    assert result["profile_score"] is None
    assert result["profile_label"] == "성향 미검사"
    assert all(x["profile_score"] is None for x in result["components"])


def test_missing_synced_data_reduces_coverage_not_ai_to_zero():
    stock=sample_stock()
    stock["momentum_20d"]=None
    stock["change_rate"]=None
    result=build_scorecard(stock,flow=None,sentiment=None)
    assert result["coverage"] < 100
    assert result["ai_score"] > 0
    by_key={x["key"]:x for x in result["components"]}
    assert by_key["flow"]["available"] is False
    assert by_key["sentiment"]["available"] is False
    assert by_key["momentum"]["available"] is False


def test_cached_components_reproduce_profile_fit_without_signal_rescan():
    from backend.app.smart_scoring import profile_score_from_components
    base=build_scorecard(
        sample_stock(),
        flow={"days":5,"foreign_net":1000,"institution_net":500,"positive_days":4,"net_ratio":35},
        sentiment={"positive":6,"neutral":2,"negative":1,"news":7,"reports":2},
    )
    profile_scores={"percentages":{
        "horizon":{"L":75,"N":20,"S":5},
        "risk":{"A":20,"D":80},
        "value":{"G":35,"V":65},
        "profit":{"P":30,"H":70},
        "spread":{"F":20,"M":80},
    }}
    live=build_scorecard(
        sample_stock(),
        flow={"days":5,"foreign_net":1000,"institution_net":500,"positive_days":4,"net_ratio":35},
        sentiment={"positive":6,"neutral":2,"negative":1,"news":7,"reports":2},
        profile_scores=profile_scores,
        profile_code="LDVHM",
    )
    cached=profile_score_from_components(
        base["components"],profile_scores=profile_scores,profile_code="LDVHM"
    )
    assert cached["score"] == live["profile_score"]
    assert cached["label"] == live["profile_label"]
    assert len(cached["components"]) == 6


def test_personal_fit_is_independent_from_aggregate_score_across_varied_stocks():
    import math
    profile={"percentages":{
        "horizon":{"L":80,"N":15,"S":5},
        "risk":{"A":15,"D":85},
        "value":{"G":25,"V":75},
        "profit":{"P":25,"H":75},
        "spread":{"F":20,"M":80},
    }}
    variants=[
        (25,30,20,40,4,0.2,18,6,5000),
        (8,-5,5,8,0.8,5,-4,2,200000),
        (15,10,12,12,1.2,3,3,3,80000),
        (5,25,2,60,8,0,22,10,1500),
        (22,18,18,28,3,1,12,5,30000),
        (3,-15,-2,6,0.5,6,-10,1,120000),
        (12,5,9,18,2,2,20,11,4000),
        (18,2,16,9,0.7,4,-2,2,250000),
    ]
    pairs=[]
    for roe,growth,margin,per,pbr,dividend,momentum,volatility,cap in variants:
        stock=sample_stock()
        stock.update({
            "roe":roe,"revenue_growth":growth,"operating_margin":margin,
            "per":per,"pbr":pbr,"dividend_yield":dividend,
            "momentum_20d":momentum,"volatility":volatility,"market_cap":cap,
        })
        result=build_scorecard(
            stock,
            flow={"days":10,"foreign_net":1000,"institution_net":500,"positive_days":6,"net_ratio":15},
            sentiment={"positive":3,"neutral":2,"negative":2,"news":5,"reports":2},
            profile_scores=profile,
            profile_code="LDVHM",
        )
        pairs.append((result["ai_score"],result["profile_score"]))

    xs=[x for x,_ in pairs]; ys=[y for _,y in pairs]
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
    numerator=sum((x-mx)*(y-my) for x,y in pairs)
    denominator=math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))
    correlation=numerator/denominator
    assert correlation < 0.85
    assert any(abs(x-y) >= 20 for x,y in pairs)


def test_same_stock_can_fit_defensive_and_aggressive_users_very_differently():
    stock=sample_stock()
    stock.update({"volatility":9.5,"market_cap":2500,"momentum_20d":20,"change_rate":6,"dividend_yield":0.2,"per":35,"pbr":4.5})
    aggressive={"percentages":{
        "horizon":{"L":5,"N":15,"S":80},"risk":{"A":90,"D":10},
        "value":{"G":85,"V":15},"profit":{"P":65,"H":35},"spread":{"F":80,"M":20},
    }}
    defensive={"percentages":{
        "horizon":{"L":85,"N":10,"S":5},"risk":{"A":10,"D":90},
        "value":{"G":20,"V":80},"profit":{"P":20,"H":80},"spread":{"F":15,"M":85},
    }}
    common=dict(flow={"days":10,"foreign_net":5000,"institution_net":3000,"positive_days":8,"net_ratio":55}, sentiment={"positive":5,"neutral":2,"negative":1,"news":6,"reports":2})
    a=build_scorecard(stock,profile_scores=aggressive,profile_code="SAGPF",**common)
    d=build_scorecard(stock,profile_scores=defensive,profile_code="LDVHM",**common)
    assert abs(a["profile_score"]-d["profile_score"]) >= 18
    assert a["ai_score"] == d["ai_score"]
