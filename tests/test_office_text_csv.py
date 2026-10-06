import tempfile
import unittest
from pathlib import Path

from App.OCR_BE.office_text import OFFICE_TEXT_EXTENSIONS, extract_office_text


class CsvTextExtractionTests(unittest.TestCase):
    def test_extract_office_text_reads_utf8_bom_semicolon_csv_as_tabular_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "invoice.csv"
            csv_path.write_bytes(
                "Mã hóa đơn;Số tiền;Nhà cung cấp\r\nINV-001;1250000;MEIKO\r\n".encode("utf-8-sig")
            )

            pages = extract_office_text(csv_path)

        self.assertEqual(
            pages,
            [
                "[Sheet] CSV\n"
                "Mã hóa đơn\tSố tiền\tNhà cung cấp\n"
                "INV-001\t1250000\tMEIKO"
            ],
        )

    def test_csv_is_a_supported_text_parser_format(self):
        self.assertIn(".csv", OFFICE_TEXT_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
