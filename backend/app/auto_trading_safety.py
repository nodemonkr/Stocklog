from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


class GbotDecisionContractError(RuntimeError):
    """Raised when an automatic-trading Gbot response is unsafe to execute."""


@dataclass(frozen=True)
class GbotValidationResult:
    decisions: list[dict[str, Any]]
    rejected: list[str]
    coverage: dict[str, Any]


def _as_code_set(values) -> set[str]:
    return {str(value or "").strip() for value in (values or []) if str(value or "").strip()}


_PERCENT_NUMBER = re.compile(r"^([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(%|점)?$")


def _normalize_code(value: Any) -> str:
    code = str(value or "").strip()
    # Gemini occasionally serializes a six-digit Korean stock code as a JSON
    # number and therefore drops leading zeroes. Only restore those zeroes when
    # the resulting code still has to pass the current-cycle whitelist below.
    if code.isdigit() and len(code) < 6:
        code = code.zfill(6)
    return code


def _percent_number(value: Any, *, fraction_allowed: bool = True) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    suffix = ""
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = _PERCENT_NUMBER.fullmatch(str(value).strip())
        if not match:
            return None
        number = float(match.group(1))
        suffix = match.group(2) or ""
    if not math.isfinite(number):
        return None
    # 0.82 is a common JSON representation for 82%. Explicit percent/score
    # suffixes always retain their written scale.
    if fraction_allowed and not suffix and 0 < number < 1:
        number *= 100
    return number


def validate_gbot_decisions(
    decisions: Any,
    *,
    candidate_codes,
    owned_codes,
    holding_review: bool = False,
) -> GbotValidationResult:
    """Validate the model response before any decision can reach the order path.

    Automatic trading is fail-closed. The model may only act on codes that StockLog
    supplied in the current cycle, and executable signals must contain auditable
    reasons/evidence/exit rules. Any malformed or out-of-universe response rejects
    the entire Gbot response rather than partially executing it.
    """

    candidates = _as_code_set(candidate_codes)
    owned = _as_code_set(owned_codes)
    allowed = candidates | owned
    if not isinstance(decisions, list):
        raise GbotDecisionContractError("Gbot 응답의 decisions 형식이 배열이 아닙니다. 주문하지 않습니다.")

    if allowed and not decisions:
        raise GbotDecisionContractError("검토할 종목이 있지만 Gbot 판단이 0건입니다. 주문하지 않습니다.")

    valid_signals = {"add", "hold", "watch", "reduce", "sell"} if holding_review else {"buy", "sell", "hold"}
    sanitized: list[dict[str, Any]] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for index, item in enumerate(decisions):
        prefix = f"#{index + 1}"
        if not isinstance(item, dict):
            rejected.append(f"{prefix} 판단 항목이 객체가 아님")
            continue
        code = _normalize_code(item.get("code"))
        signal = str(item.get("action") or "").strip().lower()
        if not code:
            rejected.append(f"{prefix} 종목코드 누락")
            continue
        if code not in allowed:
            rejected.append(f"{code} 현재 후보/보유 목록 밖 종목")
            continue
        if code in seen:
            rejected.append(f"{code} 중복 판단")
            continue
        if signal not in valid_signals:
            rejected.append(f"{code} 허용되지 않은 신호 {signal or '-'}")
            continue
        if signal in {"sell", "reduce"} and code not in owned:
            rejected.append(f"{code} 미보유 종목 매도 신호")
            continue
        if signal in {"buy", "add"} and code not in candidates and code not in owned:
            rejected.append(f"{code} 후보 밖 매수 신호")
            continue

        actionable = signal in {"buy", "add", "sell", "reduce"}
        confidence = _percent_number(item.get("confidence"))
        # A missing confidence on HOLD/WATCH cannot create an order. Treat it
        # as zero confidence instead of failing the entire holding review.
        if confidence is None and not actionable:
            confidence = 0.0
        if confidence is None:
            rejected.append(f"{code} 확신도 형식 오류")
            continue
        if not 0 <= confidence <= 100:
            rejected.append(f"{code} 확신도 범위 오류")
            continue

        reason = str(item.get("reason") or "").strip()
        evidence = item.get("evidence")
        risks = item.get("risks")
        exit_plan = str(item.get("exit_plan") or "").strip()
        if not reason:
            rejected.append(f"{code} 판단 이유 누락")
            continue
        clean_evidence = [str(x).strip() for x in (evidence or []) if str(x or "").strip()] if isinstance(evidence, list) else []
        if actionable and len(clean_evidence) < 3:
            rejected.append(f"{code} 실행 신호의 독립 근거가 3개 미만")
            continue
        if risks is not None and not isinstance(risks, list):
            rejected.append(f"{code} 위험요인 형식 오류")
            continue
        clean_risks = [str(x).strip() for x in (risks or []) if str(x or "").strip()] if isinstance(risks, list) else []
        if signal in {"buy", "add"} and not clean_risks:
            rejected.append(f"{code} 매수 신호의 반대 위험요인 누락")
            continue
        if actionable and not exit_plan:
            rejected.append(f"{code} 실행 신호의 재평가/청산 기준 누락")
            continue

        clean = dict(item)
        clean["code"] = code
        clean["action"] = signal
        clean["confidence"] = confidence
        clean["reason"] = reason
        clean["evidence"] = clean_evidence
        clean["risks"] = clean_risks
        clean["exit_plan"] = exit_plan
        if signal in {"buy", "add"}:
            allocation_pct = _percent_number(item.get("allocation_pct"))
            clean["allocation_pct"] = max(0.0, min(100.0, allocation_pct if allocation_pct is not None else 0.0))
        if signal == "reduce":
            reduce_pct = _percent_number(item.get("reduce_pct"))
            if reduce_pct is None:
                reduce_pct = 50.0
            if reduce_pct not in {25.0, 50.0, 75.0}:
                rejected.append(f"{code} 축소비율 형식 오류")
                continue
            clean["reduce_pct"] = int(reduce_pct)
        sanitized.append(clean)
        seen.add(code)

    if rejected:
        preview = " · ".join(rejected[:4])
        extra = f" 외 {len(rejected) - 4}건" if len(rejected) > 4 else ""
        raise GbotDecisionContractError(f"Gbot 응답 무결성 검사 실패: {preview}{extra}. 주문하지 않습니다.")

    missing_owned = sorted(owned - seen)
    if owned and missing_owned:
        preview = ", ".join(missing_owned[:5])
        extra = f" 외 {len(missing_owned) - 5}종목" if len(missing_owned) > 5 else ""
        raise GbotDecisionContractError(f"Gbot이 보유종목 판단을 누락했습니다: {preview}{extra}. 주문하지 않습니다.")

    return GbotValidationResult(
        decisions=sanitized,
        rejected=[],
        coverage={
            "candidate_count": len(candidates),
            "owned_count": len(owned),
            "returned_count": len(sanitized),
            "owned_covered": len(owned),
            "whitelist_enforced": True,
            "fail_closed": True,
        },
    )
