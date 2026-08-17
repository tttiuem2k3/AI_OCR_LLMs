import unittest
from unittest.mock import patch

import run_test


class RunTestFilenameSectionTypeTests(unittest.TestCase):
    def test_known_filename_prefixes_return_configured_section_types(self):
        cases = {
            "INV_PL_001.pdf": ("INVOICE", "PACKINGLIST"),
            "IV_PL_001.pdf": ("INVOICE", "PACKINGLIST"),
            "IV-PL_Hoa don va bang ke.pdf": ("INVOICE", "PACKINGLIST"),
            "IN_PL_001.pdf": ("INVOICE", "PACKINGLIST"),
            "COM_PL_001.pdf": ("COMMERCIALINVOICE", "PACKINGLIST"),
            "HANDOVER_001.pdf": ("HANDOVER",),
            "INSPEC_001.pdf": ("INSPECTION",),
            "OTHER_001.pdf": ("OTHER",),
            "INV_001.pdf": ("INVOICE",),
            "IV_001.pdf": ("INVOICE",),
            "VAT_001.pdf": ("INVOICE",),
            "CUS_001.pdf": ("CUSTOMSHEET",),
            "tokhaihq7n_qdtq_000001231.pdf": ("CUSTOMSHEET",),
            "PO_001.pdf": ("PO",),
            "RING_001.pdf": ("RINGI",),
            "RINGI_001.pdf": ("RINGI",),
            "LIST_001.pdf": ("STATEMENT",),
            "COM_001.pdf": ("COMMERCIALINVOICE",),
            "PL_001.pdf": ("PACKINGLIST",),
            "BILL_001.pdf": ("BILL",),
            "CT_001.pdf": ("CONTRACT",),
            "CSC_CT_2026.pdf": ("CONTRACT",),
        }

        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(run_test._section_types_for_filename(filename), expected)

    def test_unknown_filename_prefix_returns_one_random_section_type(self):
        with patch.object(run_test.random, "choice", return_value="BILL"):
            self.assertEqual(run_test._section_types_for_filename("BBNT.pdf"), ("BILL",))

    def test_extract_prompt_uses_filename_section_types(self):
        prompt = "Tên File: IV_Đơn đề nghị thanh toán số 001.2026.pdf - Dữ liệu OCR: mock text"

        payload = run_test._mock_extract_payload(prompt)

        self.assertEqual(
            [section["master"]["SectionType"] for section in payload["sections"]],
            ["INVOICE"],
        )

    def test_extract_prompt_combines_unique_section_types_from_multiple_files(self):
        prompt = "\n".join([
            "Tên file: INV_PL_001.pdf }",
            "Tên file: CUS_001.pdf }",
            "Tên file: INV_PL_001.pdf }",
        ])

        payload = run_test._mock_extract_payload(prompt)

        self.assertEqual(
            [section["master"]["SectionType"] for section in payload["sections"]],
            ["INVOICE", "PACKINGLIST", "CUSTOMSHEET"],
        )


if __name__ == "__main__":
    unittest.main()
