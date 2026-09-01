from backend.app.theme_taxonomy import (
    THEME_ENGINE_VERSION,
    canonical_group_for_theme,
    classify_stock_context,
    map_theme_name,
    taxonomy_tree,
)


def test_semiconductor_children_share_parent():
    assert canonical_group_for_theme("팹리스") == "반도체"
    assert canonical_group_for_theme("HBM") == "반도체"
    assert canonical_group_for_theme("메모리 반도체") == "반도체"
    assert canonical_group_for_theme("반도체 장비") == "반도체"


def test_cosmetics_children_share_parent():
    assert canonical_group_for_theme("K-뷰티") == "화장품"
    assert canonical_group_for_theme("화장품 ODM") == "화장품"


def test_known_stocks_are_stable():
    samsung=classify_stock_context({"name":"삼성전자"})
    jeju=classify_stock_context({"name":"제주반도체"})
    cosmax=classify_stock_context({"name":"코스맥스","official_industry":"화학"})
    assert samsung["theme_group"] == "반도체"
    assert jeju["theme_group"] == "반도체"
    assert "팹리스" in jeju["subthemes"]
    assert cosmax["theme_group"] == "화장품"
    assert cosmax["engine_version"] == THEME_ENGINE_VERSION


def test_provider_evidence_beats_broad_official_industry():
    result=classify_stock_context({
        "name":"테스트화장품",
        "official_industry":"화학",
        "provider_themes":["K-뷰티","화장품 ODM/OEM"],
        "recent_reports":["화장품 ODM 매출 성장과 글로벌 고객 확대"],
        "recent_news":["K-뷰티 수출 증가"],
    })
    assert result is not None
    assert result["theme_group"] == "화장품"
    assert "화장품 ODM/OEM" in result["subthemes"]


def test_official_industry_alone_does_not_force_chemical_theme():
    result=classify_stock_context({"name":"미확인기업","official_industry":"화학"})
    assert result is None


def test_taxonomy_tree_exposes_semiconductor_children():
    tree=taxonomy_tree()
    assert "반도체" in tree
    assert "팹리스" in tree["반도체"]
    assert "HBM" in tree["반도체"]


def test_map_theme_name_keeps_child_information():
    matches=map_theme_name("시스템반도체/팹리스")
    assert any(x["group"] == "반도체" and x["subtheme"] == "팹리스" for x in matches)


def test_previous_verified_theme_is_reused_as_rebuild_evidence():
    result=classify_stock_context({
        "name":"기존분류기업",
        "previous_theme_group":"반도체",
        "existing_investment_theme":"반도체",
    })
    assert result is not None
    assert result["theme_group"] == "반도체"
    assert result["classification_mode"] == "evidence"


def test_safe_dart_industry_can_be_used_as_low_confidence_fallback():
    result=classify_stock_context({
        "name":"정밀기기기업",
        "official_industry":"의료·정밀기기",
    })
    assert result is not None
    assert result["theme_group"] == "의료기기"
    assert result["classification_mode"] == "industry_fallback"
    assert result["confidence"] < 60


def test_ambiguous_dart_industry_still_does_not_force_theme():
    result=classify_stock_context({
        "name":"범용화학기업",
        "official_industry":"화학",
    })
    assert result is None
