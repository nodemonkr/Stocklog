from __future__ import annotations

import ipaddress
import re
from typing import Any, Iterable


ACCESS_MODE_ALLOW_ALL = "allow_all"
ACCESS_MODE_ALLOWLIST = "allowlist"
ACCESS_MODES = {ACCESS_MODE_ALLOW_ALL, ACCESS_MODE_ALLOWLIST}


class AccessRuleError(ValueError):
    pass


def normalize_client_ip(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    # request.client.host is already proxy-normalized by Uvicorn. Brackets and
    # IPv4-mapped IPv6 are normalized here for stable comparisons and display.
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return ""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    return address.compressed


def _split_rule_values(values: Iterable[Any] | None) -> list[str]:
    parts: list[str] = []
    for value in values or []:
        parts.extend(x for x in re.split(r"[\s,]+", str(value or "").strip()) if x)
    return parts


def normalize_access_rules(values: Iterable[Any] | None, *, max_rules: int = 200) -> list[str]:
    normalized: list[str] = []
    invalid: list[str] = []
    for raw in _split_rule_values(values):
        try:
            if "/" in raw:
                network = ipaddress.ip_network(raw, strict=False)
                rule = network.with_prefixlen
            else:
                rule = normalize_client_ip(raw)
                if not rule:
                    raise ValueError(raw)
        except ValueError:
            invalid.append(raw[:80])
            continue
        if rule not in normalized:
            normalized.append(rule)
        if len(normalized) > max_rules:
            raise AccessRuleError(f"허용 IP는 최대 {max_rules}개까지 등록할 수 있습니다.")
    if invalid:
        preview = ", ".join(invalid[:5])
        extra = f" 외 {len(invalid)-5}개" if len(invalid) > 5 else ""
        raise AccessRuleError(f"IP 또는 CIDR 형식을 확인해주세요: {preview}{extra}")
    return normalized


def ip_matches_rules(client_ip: Any, rules: Iterable[Any] | None) -> bool:
    normalized_ip = normalize_client_ip(client_ip)
    if not normalized_ip:
        return False
    address = ipaddress.ip_address(normalized_ip)
    for raw in rules or []:
        rule = str(raw or "").strip()
        if not rule:
            continue
        try:
            if "/" in rule:
                network = ipaddress.ip_network(rule, strict=False)
                comparable = address
                if isinstance(network, ipaddress.IPv4Network) and isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                    comparable = address.ipv4_mapped
                if comparable.version == network.version and comparable in network:
                    return True
            elif normalize_client_ip(rule) == normalized_ip:
                return True
        except ValueError:
            continue
    return False


def access_allowed(mode: Any, client_ip: Any, rules: Iterable[Any] | None, *, allow_loopback: bool = True) -> bool:
    normalized_ip = normalize_client_ip(client_ip)
    if allow_loopback and normalized_ip:
        try:
            if ipaddress.ip_address(normalized_ip).is_loopback:
                return True
        except ValueError:
            pass
    if str(mode or ACCESS_MODE_ALLOW_ALL) == ACCESS_MODE_ALLOW_ALL:
        return True
    return ip_matches_rules(normalized_ip, rules)
