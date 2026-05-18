import unittest

from cogs.warnings import selected_warn_tier, validate_warn_policy


class WarningPolicyTests(unittest.TestCase):
    def test_validate_policy_sorts_tiers(self):
        policy = validate_warn_policy(
            {
                "decayDays": 14,
                "tiers": [
                    {"warns": 3, "action": "timeout", "durationMinutes": 60, "label": "third"},
                    {"warns": 1, "action": "none", "durationMinutes": 0, "label": "first"},
                ],
            }
        )
        self.assertEqual(policy["decayDays"], 14)
        self.assertEqual([tier["warns"] for tier in policy["tiers"]], [1, 3])

    def test_timeout_requires_duration(self):
        with self.assertRaises(ValueError):
            validate_warn_policy({"decayDays": 30, "tiers": [{"warns": 2, "action": "timeout", "durationMinutes": 0}]})

    def test_selected_tier_uses_highest_matching_threshold(self):
        policy = validate_warn_policy(
            {
                "decayDays": 30,
                "tiers": [
                    {"warns": 1, "action": "none"},
                    {"warns": 2, "action": "timeout", "durationMinutes": 10},
                    {"warns": 3, "action": "timeout", "durationMinutes": 60},
                ],
            }
        )
        tier = selected_warn_tier(policy, 4)
        self.assertEqual(tier["warns"], 3)
        self.assertEqual(tier["durationMinutes"], 60)


if __name__ == "__main__":
    unittest.main()
