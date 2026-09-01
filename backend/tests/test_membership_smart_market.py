from backend.app.membership import DEFAULT_POLICY


def test_normal_member_does_not_have_full_market_access_by_default():
    assert DEFAULT_POLICY["NORMAL"]["smart_full_market"] == (False, None)


def test_premium_and_above_have_full_market_access_by_default():
    for tier in ("PREMIUM","EVENT","ADMIN"):
        assert DEFAULT_POLICY[tier]["smart_full_market"][0] is True
