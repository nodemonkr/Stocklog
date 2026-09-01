import unittest

from backend.app.db_utils import commit_or_rollback, flush_or_rollback, rollback_quietly


class FakeSession:
    def __init__(self, commit_error=None, flush_error=None, rollback_error=None):
        self.commit_error = commit_error
        self.flush_error = flush_error
        self.rollback_error = rollback_error
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    def flush(self):
        self.flushes += 1
        if self.flush_error:
            raise self.flush_error

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_error:
            raise self.rollback_error


class DbUtilsTest(unittest.TestCase):
    def test_commit_success_does_not_rollback(self):
        session = FakeSession()
        commit_or_rollback(session)
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.rollbacks, 0)

    def test_commit_failure_rolls_back_and_reraises(self):
        session = FakeSession(commit_error=RuntimeError("commit failed"))
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            commit_or_rollback(session)
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.rollbacks, 1)

    def test_flush_failure_rolls_back_and_reraises(self):
        session = FakeSession(flush_error=RuntimeError("flush failed"))
        with self.assertRaisesRegex(RuntimeError, "flush failed"):
            flush_or_rollback(session)
        self.assertEqual(session.flushes, 1)
        self.assertEqual(session.rollbacks, 1)

    def test_rollback_quietly_never_masks_original_failure(self):
        session = FakeSession(rollback_error=RuntimeError("rollback failed"))
        rollback_quietly(session)
        self.assertEqual(session.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
