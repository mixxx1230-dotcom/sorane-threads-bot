import unittest
from datetime import date

from scripts.post_blog_update import already_posted_today


class BlogPostingLimitTests(unittest.TestCase):
    def test_skips_second_blog_post_on_same_day(self):
        state = {"status": "posted", "posted_date": "2026-10-14"}
        self.assertTrue(already_posted_today(state, date(2026, 10, 14)))

    def test_allows_next_day_or_legacy_state(self):
        self.assertFalse(already_posted_today({"status": "posted", "posted_date": "2026-10-13"}, date(2026, 10, 14)))
        self.assertFalse(already_posted_today({"status": "posted"}, date(2026, 10, 14)))


if __name__ == "__main__":
    unittest.main()
