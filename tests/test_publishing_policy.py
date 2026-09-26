import unittest
from datetime import date

from scripts.publishing_policy import should_publish


class PublishingPolicyTests(unittest.TestCase):
    def test_reset_allows_noon_on_weekday(self):
        allowed, _ = should_publish("noon", date(2026, 9, 26))
        self.assertTrue(allowed)

    def test_reset_skips_sunday(self):
        allowed, _ = should_publish("noon", date(2026, 9, 27))
        self.assertFalse(allowed)

    def test_reset_skips_evening_and_blog(self):
        self.assertFalse(should_publish("evening", date(2026, 9, 28))[0])
        self.assertFalse(should_publish("blog", date(2026, 9, 28))[0])

    def test_standard_schedule_returns_after_test(self):
        self.assertTrue(should_publish("evening", date(2026, 10, 10))[0])
        self.assertTrue(should_publish("blog", date(2026, 10, 10))[0])

    def test_force_override(self):
        self.assertTrue(should_publish("evening", date(2026, 9, 28), force=True)[0])


if __name__ == "__main__":
    unittest.main()
