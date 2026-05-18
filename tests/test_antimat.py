import unittest

from cogs.antimat import parse_words


class AntiMatWordParsingTests(unittest.TestCase):
    def test_parse_words_accepts_comma_separated_words(self):
        self.assertEqual(parse_words("spam, CAPS, spam, flood"), ["spam", "caps", "flood"])

    def test_parse_words_accepts_new_lines_like_commas(self):
        self.assertEqual(parse_words("one\ntwo, three"), ["one", "two", "three"])


if __name__ == "__main__":
    unittest.main()
