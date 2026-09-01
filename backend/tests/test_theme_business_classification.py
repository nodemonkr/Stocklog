from backend.app.theme_classification import deterministic_business_theme as _deterministic_business_theme, normalize_ai_classification_items as _normalize_ai_classification_items


def test_cosmax_fallback_prefers_cosmetics_over_broad_chemical_industry():
    result = _deterministic_business_theme({
        "code": "192820",
        "name": "코스맥스",
        "official_industry": "화학",
        "provider_themes": ["사업/화학"],
        "recent_news": [],
        "recent_reports": [],
        "existing_business": "",
    })
    assert result["primary_theme"] == "화장품"
    assert result["confidence"] >= 90


def test_ai_item_list_is_mapped_back_to_exact_stock_code():
    contexts = [{"code": "005930", "name": "삼성전자"}]
    parsed = {"items": [{"code": 5930, "primary_theme": "반도체"}]}
    items = _normalize_ai_classification_items(parsed, contexts)
    assert items["005930"]["primary_theme"] == "반도체"


def test_ai_item_keyed_by_company_name_is_supported():
    contexts = [{"code": "192820", "name": "코스맥스"}]
    parsed = {"items": {"코스맥스": {"primary_theme": "화장품"}}}
    items = _normalize_ai_classification_items(parsed, contexts)
    assert items["192820"]["primary_theme"] == "화장품"
