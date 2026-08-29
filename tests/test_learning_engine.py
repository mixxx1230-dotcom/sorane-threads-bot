import unittest

from scripts.learning_engine import build_learning_profile, engagement_score, extract_features


class LearningEngineTests(unittest.TestCase):
    def test_weighted_engagement_rewards_conversation(self):
        passive = {"views": 1000, "likes": 10, "replies": 0, "reposts": 0, "quotes": 0}
        conversational = {"views": 1000, "likes": 10, "replies": 8, "reposts": 2, "quotes": 1}
        self.assertGreater(engagement_score(conversational), engagement_score(passive))

    def test_extracts_content_features(self):
        features = extract_features("肩、重くないですか？\n10秒だけほぐしてみてください🌿")
        self.assertTrue(features["hook_question"])
        self.assertTrue(features["has_selfcare"])
        self.assertEqual(features["length_band"], "short")

    def test_timestamp_is_converted_to_jst(self):
        features = extract_features("テスト", "2026-08-28T02:01:37+0000")
        self.assertEqual(features["hour"], 11)
        self.assertEqual(features["time_band"], "noon")

    def test_extracts_growth_features(self):
        features = extract_features(
            "施術していて最近多いのが、首肩のこわばり。\n予約はこちら https://example.com",
            media_type="IMAGE",
        )
        self.assertEqual(features["opening_type"], "practitioner_observation")
        self.assertEqual(features["topic"], "neck_shoulder")
        self.assertTrue(features["has_booking_link"])
        self.assertEqual(features["media"], "image_or_video")

    def test_profile_ignores_single_sample_buckets(self):
        profile = build_learning_profile([
            {"text": "疲れていませんか？", "views": 100, "likes": 3},
            {"text": "肩、重くないですか？", "views": 200, "likes": 8},
        ])
        features = {item["feature"] for item in profile["feature_stats"]}
        self.assertIn("hook_question:true", features)
        self.assertEqual(profile["sample_size"], 2)


if __name__ == "__main__":
    unittest.main()

