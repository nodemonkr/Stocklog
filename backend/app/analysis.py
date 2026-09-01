def classify_stock(s):
    scores = {
        "가치주": 0,
        "성장주": 0,
        "모멘텀": 0,
        "배당": 0,
        "저변동": 0,
    }
    if s.per and 0 < s.per <= 15: scores["가치주"] += 2
    if s.pbr and 0 < s.pbr <= 1.5: scores["가치주"] += 2
    if s.roe and s.roe >= 10: scores["가치주"] += 1
    if s.revenue_growth and s.revenue_growth >= 10: scores["성장주"] += 3
    if s.roe and s.roe >= 15: scores["성장주"] += 1
    if s.momentum_20d and s.momentum_20d >= 5: scores["모멘텀"] += 3
    if s.change_rate >= 2: scores["모멘텀"] += 1
    if s.dividend_yield and s.dividend_yield >= 2.5: scores["배당"] += 3
    if s.volatility is not None and s.volatility <= 2.0: scores["저변동"] += 3
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "종합"


def compute_score(s, news_items=None):
    score = 50.0
    reasons = []
    risks = []

    if s.per is not None:
        if 0 < s.per <= 15:
            score += 8; reasons.append(f"PER {s.per:.1f}배로 밸류에이션 부담이 비교적 낮음")
        elif s.per > 35:
            score -= 6; risks.append(f"PER {s.per:.1f}배로 밸류에이션 부담")
    if s.pbr is not None:
        if 0 < s.pbr <= 1.5:
            score += 7; reasons.append(f"PBR {s.pbr:.2f}배로 자산가치 대비 가격 부담이 낮은 편")
        elif s.pbr > 5:
            score -= 5; risks.append(f"PBR {s.pbr:.2f}배로 자산가치 대비 높은 가격")
    if s.roe is not None:
        if s.roe >= 15:
            score += 10; reasons.append(f"ROE {s.roe:.1f}%로 자본 효율성이 우수")
        elif s.roe < 5:
            score -= 7; risks.append(f"ROE {s.roe:.1f}%로 자본 효율성이 낮음")
    if s.revenue_growth is not None:
        if s.revenue_growth >= 15:
            score += 10; reasons.append(f"매출 성장률 {s.revenue_growth:.1f}%로 외형 성장성이 높음")
        elif s.revenue_growth < 0:
            score -= 8; risks.append(f"매출 성장률 {s.revenue_growth:.1f}%로 역성장")
    if s.operating_margin is not None:
        if s.operating_margin >= 10:
            score += 6; reasons.append(f"영업이익률 {s.operating_margin:.1f}%로 본업 수익성이 양호")
        elif s.operating_margin < 0:
            score -= 10; risks.append("영업적자 구간으로 본업 수익성 확인 필요")
    if s.momentum_20d is not None:
        if s.momentum_20d >= 5:
            score += 6; reasons.append(f"20일 모멘텀 +{s.momentum_20d:.1f}%로 단기 수급이 우호적")
        elif s.momentum_20d <= -8:
            score -= 6; risks.append(f"20일 모멘텀 {s.momentum_20d:.1f}%로 단기 추세가 약함")
    if s.volatility is not None and s.volatility >= 5:
        score -= 5; risks.append(f"변동성 지표 {s.volatility:.1f}로 가격 흔들림이 큰 편")

    if news_items:
        vals = [x.get("sentiment_score", 0) for x in news_items]
        avg = sum(vals) / len(vals) if vals else 0
        score += avg * 8
        if avg > .15: reasons.append("최근 뉴스 제목/요약의 감성 흐름이 대체로 긍정적")
        elif avg < -.15: risks.append("최근 뉴스 제목/요약의 감성 흐름이 대체로 부정적")

    score = max(0, min(100, round(score, 1)))
    recommendation = "추천" if score >= 68 else "관망" if score >= 48 else "비추천"
    return score, recommendation, reasons[:7], risks[:7]


SECTOR_OUTLOOK = {
    "반도체": {
        "opportunity": "AI 서버/고대역폭 메모리/첨단 공정 투자 확대가 업황 개선으로 이어지는지 확인할 필요가 있습니다.",
        "watch": "메모리 가격, 재고 정상화 속도, CAPEX, 고객사 AI 투자 사이클이 핵심 변수입니다.",
    },
    "반도체장비": {
        "opportunity": "선단공정/HBM 증설이 지속되면 장비 발주와 고부가 공정 장비 수요가 확대될 가능성이 있습니다.",
        "watch": "고객사 투자 집행 지연, 특정 고객 의존도, 수주잔고의 매출 전환 속도를 확인해야 합니다.",
    },
    "2차전지": {
        "opportunity": "전기차 수요 회복과 ESS 확대, 원가 안정이 동시에 진행될 경우 실적 레버리지가 커질 수 있습니다.",
        "watch": "전기차 판매 성장률, 배터리 판가, 핵심 원재료 가격, 가동률이 중요한 변수입니다.",
    },
    "자동차": {
        "opportunity": "제품 믹스 개선과 하이브리드/전기차 판매 확대가 수익성 유지의 핵심 동력입니다.",
        "watch": "환율, 인센티브, 주요 지역 판매량, 관세/규제와 전동화 투자 부담을 점검해야 합니다.",
    },
    "바이오": {
        "opportunity": "신규 수주/파이프라인/생산능력 확대가 실적 성장으로 연결되면 높은 성장 프리미엄을 유지할 수 있습니다.",
        "watch": "임상/허가 일정, 고객 집중도, 연구개발비 증가와 밸류에이션 부담을 함께 봐야 합니다.",
    },
    "방산": {
        "opportunity": "수출 수주잔고와 장기 공급계약이 매출로 전환되는 구간에서 실적 가시성이 높아질 수 있습니다.",
        "watch": "수주 인식 시점, 원가율, 국가별 예산/계약 일정, 대규모 프로젝트 지연 여부가 중요합니다.",
    },
    "전력기기": {
        "opportunity": "전력망 교체, 데이터센터/AI 전력 수요 증가가 중장기 수주 환경을 지지할 수 있습니다.",
        "watch": "수주잔고, 북미/중동 설비투자, 구리 등 원재료 가격과 증설 효과를 확인해야 합니다.",
    },
    "로봇": {
        "opportunity": "산업 자동화와 휴머노이드 투자 확대가 실제 매출/수주로 연결되는지가 장기 성장의 핵심입니다.",
        "watch": "높은 밸류에이션, 적자 지속 여부, 양산 일정과 고객사 확보를 특히 주의해야 합니다.",
    },
    "의료AI": {
        "opportunity": "병원 도입 확대와 해외 인허가가 반복 매출로 전환될 경우 성장성이 크게 개선될 수 있습니다.",
        "watch": "적자 축소 속도, 의료기관 실제 사용량, 해외 허가/보험수가 확보 여부를 확인해야 합니다.",
    },
    "금융": {
        "opportunity": "주주환원 확대와 안정적 이익, 자본비율 개선은 밸류에이션 재평가 요소가 될 수 있습니다.",
        "watch": "순이자마진, 대손비용, 부동산 익스포저, 자본비율과 배당정책을 함께 봐야 합니다.",
    },
    "게임": {
        "opportunity": "신작 흥행과 글로벌 매출 확대가 실적 변곡점을 만들 수 있습니다.",
        "watch": "신작 일정, 기존 게임 매출 하락 속도, 마케팅비와 플랫폼 수수료 부담이 핵심입니다.",
    },
    "화장품": {
        "opportunity": "북미/일본 등 비중국 채널 성장과 브랜드 믹스 개선이 이익률을 끌어올릴 수 있습니다.",
        "watch": "중국 소비 회복, 면세/온라인 채널 변화, 마케팅비와 브랜드 경쟁 강도를 확인해야 합니다.",
    },
}


def pct_change(current, previous):
    if previous in (None, 0) or current is None:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def enrich_financial_growth(financials):
    """Attach only like-for-like financial changes.

    Income statement metrics use the comparison values captured from the same
    quarterly/half-year/annual filing (prior-year same reporting basis).
    Balance-sheet metrics use the filing's previous-term balance.  Legacy rows
    without captured comparison values are compared only to the same report
    label from the prior year; adjacent 1Q/2Q/3Q/FY rows are never compared.
    """
    result=[]
    keys=["revenue","operating_profit","net_income","assets","liabilities","equity"]
    by_period={str(row.get("period") or ""): row for row in financials}

    for row in financials:
        enriched=dict(row)
        enriched["change"]={}
        enriched["change_labels"]={}
        enriched["change_directions"]={}
        enriched["comparison_periods"]={}
        period=str(row.get("period") or "")
        try:
            year_text,label=period.split("-",1)
            prior_same=f"{int(year_text)-1}-{label}"
        except Exception:
            prior_same=""

        legacy_same=by_period.get(prior_same) if prior_same else None
        income_period=row.get("comparison_income_period") or (prior_same if legacy_same else None)
        balance_period=row.get("comparison_balance_period")

        for key in keys:
            stored_key=f"comparison_{key}"
            previous=row.get(stored_key)
            comparison_period=income_period if key in {"revenue","operating_profit","net_income"} else balance_period

            # Old DB rows did not persist filing-native comparison values.
            # For them, only a true previous-year same report row is acceptable.
            if previous is None and legacy_same is not None:
                previous=legacy_same.get(key)
                comparison_period=prior_same

            current=row.get(key)
            numeric_change=None
            change_label="비교 데이터 없음"
            change_direction="none"

            if current is not None and previous is not None:
                try:
                    current_num=float(current)
                    previous_num=float(previous)
                except (TypeError,ValueError):
                    current_num=previous_num=None

                if current_num is not None and previous_num is not None:
                    if key in {"operating_profit","net_income"} and (previous_num <= 0 or current_num < 0):
                        if previous_num < 0 <= current_num:
                            change_label="+"
                            change_direction="up"
                        elif previous_num >= 0 > current_num:
                            change_label="-"
                            change_direction="down"
                        elif previous_num < 0 and current_num < 0:
                            if current_num > previous_num:
                                change_label="+"
                                change_direction="up"
                            elif current_num < previous_num:
                                change_label="-"
                                change_direction="down"
                            else:
                                change_label="0"
                                change_direction="flat"
                        elif current_num > previous_num:
                            change_label="+"
                            change_direction="up"
                        elif current_num < previous_num:
                            change_label="-"
                            change_direction="down"
                        else:
                            change_label="0"
                            change_direction="flat"
                    elif previous_num <= 0:
                        if current_num > previous_num:
                            change_label="+"
                            change_direction="up"
                        elif current_num < previous_num:
                            change_label="-"
                            change_direction="down"
                        else:
                            change_label="0"
                            change_direction="flat"
                    else:
                        numeric_change=pct_change(current_num,previous_num)
                        if numeric_change is None:
                            change_label="비교 데이터 없음"
                            change_direction="none"
                        elif numeric_change > 0:
                            change_label=f"+{numeric_change:.1f}%"
                            change_direction="up"
                        elif numeric_change < 0:
                            change_label=f"{numeric_change:.1f}%"
                            change_direction="down"
                        else:
                            change_label="0.0%"
                            change_direction="flat"

            enriched["change"][key]=numeric_change
            enriched["change_labels"][key]=change_label
            enriched["change_directions"][key]=change_direction
            enriched["comparison_periods"][key]=comparison_period

        enriched["comparison_period"]=income_period
        enriched["comparison_basis"]=(f"{income_period} 대비" if income_period else "동일 기준 비교값 없음")
        result.append(enriched)
    return result


def _fmt_pct(value):
    if value is None:
        return "확인 불가"
    return f"{value:+.1f}%"


def build_deep_analysis(stock, financials, news_items):
    score, recommendation, reasons, risks = compute_score(stock, news_items)

    enriched_financials = enrich_financial_growth(financials)
    latest = enriched_financials[0] if enriched_financials else {}
    previous = financials[1] if len(financials) >= 2 else {}

    rev_qoq = (latest.get("change") or {}).get("revenue")
    op_qoq = (latest.get("change") or {}).get("operating_profit")
    ni_qoq = (latest.get("change") or {}).get("net_income")

    positive_news = sum(1 for n in news_items if n.get("sentiment") == "positive")
    negative_news = sum(1 for n in news_items if n.get("sentiment") == "negative")
    neutral_news = sum(1 for n in news_items if n.get("sentiment") == "neutral")

    sector = SECTOR_OUTLOOK.get(
        stock.sector,
        {
            "opportunity": "산업 수요와 회사의 실적 성장률이 실제 이익 증가로 연결되는지 지속적으로 확인할 필요가 있습니다.",
            "watch": "매출 성장, 영업이익률, 현금흐름, 밸류에이션과 업종 수급을 함께 관찰해야 합니다.",
        },
    )

    business = []
    if stock.revenue_growth is not None:
        if stock.revenue_growth >= 15:
            business.append(
                f"현재 데이터상 매출 성장률이 {stock.revenue_growth:.1f}%로 높은 편입니다. "
                "외형 성장이 영업이익 증가로 이어지는지를 다음 분기에도 확인할 가치가 있습니다."
            )
        elif stock.revenue_growth >= 0:
            business.append(
                f"매출 성장률은 {stock.revenue_growth:.1f}%로 플러스 성장을 유지하고 있으나 "
                "고성장 국면이라고 보기는 어려워 추가 성장 동력이 필요한 구간입니다."
            )
        else:
            business.append(
                f"매출 성장률이 {stock.revenue_growth:.1f}%로 역성장 구간입니다. "
                "단순 저평가보다 매출 회복의 선행 신호가 나타나는지 확인이 우선입니다."
            )
    if stock.operating_margin is not None:
        business.append(
            f"영업이익률은 {stock.operating_margin:.1f}%입니다. "
            + ("본업에서 이익을 남기는 힘이 비교적 좋은 편입니다." if stock.operating_margin >= 10
               else "매출 증가가 실제 이익 증가로 연결되는지 원가와 판관비 흐름을 함께 확인해야 합니다.")
        )

    comparison_name=(latest.get("comparison_periods") or {}).get("revenue") or "전년 동일 공시기간"
    financial=[f"최근 공시 {latest.get('period') or '-'} 기준으로 {comparison_name} 대비 매출 변화는 {_fmt_pct(rev_qoq)}, 영업이익은 {_fmt_pct(op_qoq)}, 순이익은 {_fmt_pct(ni_qoq)}입니다."]
    if stock.roe is not None:
        financial.append(
            f"ROE는 {stock.roe:.1f}%로 "
            + ("자본을 활용해 이익을 만드는 효율이 높은 편입니다." if stock.roe >= 15
               else "자본 효율성 측면에서 추가 개선 여부를 확인할 필요가 있습니다.")
        )
    if latest and latest.get("assets") and latest.get("liabilities") is not None:
        debt_ratio = latest["liabilities"] / max(latest.get("equity", 1), 1) * 100
        financial.append(
            f"최근 분기 단순 부채/자본 비율은 약 {debt_ratio:.1f}% 수준입니다. "
            "업종 특성과 현금성자산을 함께 확인해야 하지만 재무 부담의 방향성을 보는 보조지표로 사용할 수 있습니다."
        )

    valuation = []
    if stock.per is not None:
        valuation.append(
            f"PER {stock.per:.1f}배: "
            + ("이익 대비 가격 부담이 비교적 낮은 구간입니다." if 0 < stock.per <= 15
               else "성장 기대가 이미 가격에 많이 반영됐는지 동종업계와 비교가 필요합니다." if stock.per >= 30
               else "절대적으로 과도하지는 않지만 성장률과 함께 비교해야 합니다.")
        )
    if stock.pbr is not None:
        valuation.append(
            f"PBR {stock.pbr:.2f}배: "
            + ("장부가 대비 가격이 낮은 편이지만 자산의 질과 ROE를 같이 확인해야 합니다." if 0 < stock.pbr <= 1.5
               else "높은 PBR을 정당화할 수 있는 수익성과 성장성이 지속되는지 확인해야 합니다.")
        )

    momentum = [
        f"20일 모멘텀은 {_fmt_pct(stock.momentum_20d)}이며 최근 일간 등락률은 {_fmt_pct(stock.change_rate)}입니다.",
        f"최근 수집 뉴스 {len(news_items)}건 중 긍정 {positive_news}건, 관망 {neutral_news}건, 부정 {negative_news}건으로 분류되었습니다.",
    ]
    if stock.volatility is not None:
        momentum.append(
            f"변동성 지표는 {stock.volatility:.1f}입니다. "
            + ("가격 변동 폭이 큰 종목이므로 진입 시점과 손실 관리가 특히 중요합니다." if stock.volatility >= 5
               else "상대적으로 변동이 제한적인 편이지만 시장 급변 시에는 별도 위험관리가 필요합니다.")
        )

    outlook = [
        sector["opportunity"],
        sector["watch"],
        "자동 분석에서는 회사의 공시/실적/가격/뉴스 흐름을 함께 보되, "
        "향후 실적 추정치가 실제로 상향되는지와 다음 분기 숫자가 기존 기대를 충족하는지를 가장 중요하게 봅니다.",
    ]

    if recommendation == "추천":
        summary = (
            f"현재 자동 점수는 {score:.1f}점으로 추천 구간입니다. "
            "성장성/수익성/밸류에이션 또는 모멘텀 중 복수 항목이 긍정적으로 겹쳐 있습니다. "
            "다만 추천은 매수 지시가 아니라 추가 검토 우선순위가 높다는 의미입니다."
        )
    elif recommendation == "비추천":
        summary = (
            f"현재 자동 점수는 {score:.1f}점으로 비추천 구간입니다. "
            "실적 둔화, 낮은 수익성, 높은 가격 부담 또는 약한 모멘텀 중 여러 위험요인이 겹쳐 있습니다. "
            "실적 회복 신호가 확인되기 전까지는 보수적인 접근이 적절한 구간으로 분류했습니다."
        )
    else:
        summary = (
            f"현재 자동 점수는 {score:.1f}점으로 관망 구간입니다. "
            "긍정 요인과 위험 요인이 혼재해 있어 다음 실적 또는 가격 추세의 확인이 필요합니다."
        )

    return {
        "score": score,
        "recommendation": recommendation,
        "reasons": reasons,
        "risks": risks,
        "summary": summary,
        "sections": {
            "business_performance": business,
            "financial_health": financial,
            "valuation": valuation,
            "market_and_news": momentum,
            "future_outlook": outlook,
        },
        "notice": (
            "StockLog 자동 분석은 동기화된 가격/재무/뉴스 데이터를 규칙 기반으로 해석한 참고자료입니다. "
            "미래 실적과 주가를 보장하지 않으며 실제 투자 전 원문 공시와 최신 데이터를 별도로 확인해야 합니다."
        ),
    }
