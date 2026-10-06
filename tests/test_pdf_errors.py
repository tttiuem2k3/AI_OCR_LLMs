import unittest

from App.OCR_BE.pdf_errors import PDF_DATA_FORMAT_ERROR_MESSAGE, pdf_data_format_error_pages


class PdfiumError(Exception):
    pass


class PdfErrorTests(unittest.TestCase):
    def test_data_format_error_returns_the_standard_ocr_error_page(self):
        error = PdfiumError("Failed to load document (PDFium: Data format error).")

        self.assertEqual(
            pdf_data_format_error_pages(error),
            [PDF_DATA_FORMAT_ERROR_MESSAGE],
        )

    def test_other_errors_are_not_recovered(self):
        self.assertIsNone(pdf_data_format_error_pages(PdfiumError("Password error")))
        self.assertIsNone(pdf_data_format_error_pages(ValueError("Data format error")))


if __name__ == "__main__":
    unittest.main()
