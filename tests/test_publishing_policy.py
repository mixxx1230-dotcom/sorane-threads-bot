import unittest
from datetime import date

from scripts.publishing_policy import should_publish


class PublishingPolicyTests(unittest.TestCase):
    def test_reset_allows_noon_on_monday_wednesday_friday(self):
        allowed, _ = should_publish("noon", date(2026, 11, 9))
        self.assertTrue(allowed)
        self.assertTrue(should_publish("noon", date(2026, 11, 11))[0])
        self.assertTrue(should_publish("noon", date(2026, 11, 13))[0])

    def test_reset_skips_other_weekdays(self):
        allowed, _ = should_publish("noon", date(2026, 11, 10))
        self.assertFalse(allowed)
        self.assertFalse(should_publish("noon", date(2026, 11, 15))[0])

    def test_reset_skips_evening_and_blog(self):
        self.assertFalse(should_publish("evening", date(2026, 11, 9))[0])
        self.assertFalse(should_publish("blog", date(2026, 11, 9))[0])

    def test_frequency_cap_remains_after_experiment_window(self):
        self.assertTrue(should_publish("noon", date(2026, 11, 23))[0])
        self.assertFalse(should_publish("noon", date(2026, 11, 24))[0])
        self.assertFalse(should_publish("evening", date(2026, 11, 23))[0])
        self.assertFalse(should_publish("blog", date(2026, 11, 23))[0])

    def test_force_override(self):
        self.assertTrue(should_publish("evening", date(2026, 11, 9), force=True)[0])


if __name__ == "__main__":
    unittest.main()
