import unittest

from backend.app.access_control import (
    ACCESS_MODE_ALLOWLIST,
    AccessRuleError,
    access_allowed,
    ip_matches_rules,
    normalize_access_rules,
    normalize_client_ip,
)


class AccessControlTests(unittest.TestCase):
    def test_rules_accept_exact_ip_and_cidr_and_remove_duplicates(self):
        rules = normalize_access_rules(["203.0.113.10", "192.168.0.44/24", "203.0.113.10"])
        self.assertEqual(rules, ["203.0.113.10", "192.168.0.0/24"])

    def test_invalid_rule_is_rejected(self):
        with self.assertRaisesRegex(AccessRuleError, "형식"):
            normalize_access_rules(["not-an-ip"])

    def test_allowlist_matches_exact_and_network(self):
        rules = ["203.0.113.10", "192.168.0.0/24"]
        self.assertTrue(ip_matches_rules("203.0.113.10", rules))
        self.assertTrue(ip_matches_rules("192.168.0.99", rules))
        self.assertFalse(ip_matches_rules("192.168.1.99", rules))

    def test_ipv4_mapped_ipv6_is_normalized(self):
        self.assertEqual(normalize_client_ip("::ffff:192.168.0.10"), "192.168.0.10")
        self.assertTrue(ip_matches_rules("::ffff:192.168.0.10", ["192.168.0.0/24"]))

    def test_loopback_recovery_is_always_allowed(self):
        self.assertTrue(access_allowed(ACCESS_MODE_ALLOWLIST, "127.0.0.1", [], allow_loopback=True))
        self.assertTrue(access_allowed(ACCESS_MODE_ALLOWLIST, "::1", [], allow_loopback=True))

    def test_restricted_mode_fails_closed_for_unknown_client(self):
        self.assertFalse(access_allowed(ACCESS_MODE_ALLOWLIST, "", ["203.0.113.10"]))
        self.assertFalse(access_allowed(ACCESS_MODE_ALLOWLIST, "198.51.100.5", ["203.0.113.10"]))


if __name__ == "__main__":
    unittest.main()
