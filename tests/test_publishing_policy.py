import unittest
from datetime import date

from scripts.publishing_policy import should_publish


class PublishingPolicyTests(unittest.TestCase):
    def test_conversion_policy_allows_noon(self):
        allowed, _ = should_publish("noon", date(2026, 10, 20))
        self.assertTrue(allowed)

    def test_conversion_policy_keeps_sunday_noon(self):
        allowed, _ = should_publish("noon", date(2026, 10, 25))
        self.assertTrue(allowed)

    def test_conversion_policy_skips_scheduled_evening_and_blog(self):
        self.assertFalse(should_publish("evening", date(2026, 10, 20))[0])
        self.assertFalse(should_publish("blog", date(2026, 10, 20))[0])

    def test_standard_schedule_applies_before_conversion_policy(self):
        self.assertTrue(should_publish("evening", date(2026, 10, 19))[0])
        self.assertTrue(should_publish("blog", date(2026, 10, 19))[0])

    def test_force_override(self):
        self.assertTrue(should_publish("evening", date(2026, 10, 20), force=True)[0])


if __name__ == "__main__":
    unittest.main()
