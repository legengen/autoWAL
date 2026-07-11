import unittest

from autowal.config import DEFAULT_SOURCE_ID, build_survey_url, validate_source_id


class SourceIdTests(unittest.TestCase):
    def test_default_source_id_is_preserved(self):
        self.assertEqual(DEFAULT_SOURCE_ID, "719419")
        self.assertEqual(
            build_survey_url(),
            "https://myd.iscn.org.cn/#/s/yCWFPyRr?sourceID=719419",
        )

    def test_custom_six_digit_source_id_is_used(self):
        self.assertEqual(validate_source_id("123456"), "123456")
        self.assertEqual(
            build_survey_url("123456"),
            "https://myd.iscn.org.cn/#/s/yCWFPyRr?sourceID=123456",
        )

    def test_invalid_source_id_is_rejected(self):
        for value in ("12345", "1234567", "12A456", "", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_source_id(value)


if __name__ == "__main__":
    unittest.main()
