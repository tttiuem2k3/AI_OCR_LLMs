import unittest

from App.OCR_BE.process_OCR import split_ocr_text


class OCRPageSkipTests(unittest.TestCase):
    def test_pages_at_or_above_twenty_thousand_characters_are_skipped(self):
        for oversized_length in (20000, 20001):
            with self.subTest(oversized_length=oversized_length):
                oversized_page = "X" * oversized_length
                following_page = "FOLLOWING PAGE CONTENT"
                ocr_text = (
                    f"{oversized_page}\n----1----\n"
                    f"{following_page}\n----2----"
                )

                chunks = split_ocr_text(
                    ocr_text,
                    max_pages=3,
                    max_chars_per_page=10000,
                )

                self.assertEqual(chunks, [f"{following_page}\n----2----"])

    def test_page_below_twenty_thousand_characters_is_still_processed(self):
        page_text = "X" * 19999

        chunks = split_ocr_text(
            f"{page_text}\n----1----",
            max_pages=3,
            max_chars_per_page=10000,
        )

        self.assertTrue(chunks)
        self.assertEqual(sum(chunk.count("X") for chunk in chunks), len(page_text))

    def test_file_with_only_an_oversized_page_returns_no_chunks(self):
        chunks = split_ocr_text(
            f"{'X' * 20000}\n----1----",
            max_pages=3,
            max_chars_per_page=10000,
        )

        self.assertEqual(chunks, [])


if __name__ == "__main__":
    unittest.main()
