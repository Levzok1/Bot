import unittest

from cogs.dashboard_api import ApiError, _bounded_int, _parse_snowflake, _safe_emoji


class DashboardApiValidationTests(unittest.TestCase):
    def test_parse_snowflake_accepts_discord_id(self):
        self.assertEqual(_parse_snowflake("123456789012345678", "guildId"), 123456789012345678)

    def test_parse_snowflake_rejects_command_text(self):
        with self.assertRaises(ApiError):
            _parse_snowflake("123; shutdown", "guildId")

    def test_bounded_int_rejects_out_of_range(self):
        with self.assertRaises(ApiError):
            _bounded_int("500", "amount", 1, 200)

    def test_safe_emoji_rejects_mapping_separator(self):
        with self.assertRaises(ApiError):
            _safe_emoji("😀=123")


if __name__ == "__main__":
    unittest.main()
