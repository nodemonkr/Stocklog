import unittest

from backend.app.account_security import (
    AccountSecurityError,
    membership_change_error,
    validate_admin_password,
)
from backend.app.security import create_access_token, decode_token_claims


class AccountSecurityTests(unittest.TestCase):
    def test_password_policy_accepts_valid_password(self):
        self.assertEqual(validate_admin_password("new-password-123", "member"), "new-password-123")

    def test_password_policy_rejects_short_blank_and_username(self):
        for value, username in (("short", "member"), ("        ", "member"), ("Member01", "member01")):
            with self.subTest(value=value):
                with self.assertRaises(AccountSecurityError):
                    validate_admin_password(value, username)

    def test_acting_admin_cannot_demote_self(self):
        error = membership_change_error(
            acting_admin_id=7,
            target_user_id=7,
            current_tier="ADMIN",
            next_tier="PREMIUM",
            admin_count=3,
        )
        self.assertIn("본인", error)

    def test_last_admin_cannot_be_demoted(self):
        error = membership_change_error(
            acting_admin_id=8,
            target_user_id=7,
            current_tier="ADMIN",
            next_tier="NORMAL",
            admin_count=1,
        )
        self.assertIn("최소 1명", error)

    def test_another_admin_can_be_demoted_when_admins_remain(self):
        self.assertIsNone(membership_change_error(
            acting_admin_id=8,
            target_user_id=7,
            current_tier="ADMIN",
            next_tier="NORMAL",
            admin_count=2,
        ))

    def test_access_token_carries_auth_version(self):
        token = create_access_token("member", auth_version=4)
        self.assertEqual(decode_token_claims(token), ("member", 4))


if __name__ == "__main__":
    unittest.main()
