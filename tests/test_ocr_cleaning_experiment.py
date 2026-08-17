import unittest

from tools.ocr_cleaning_experiment import clean_ocr_text


class OCRCleaningExperimentTests(unittest.TestCase):
    def test_cleaning_removes_safe_noise_and_preserves_evidence(self):
        source = """INVOICE NO. IV-001     DATE: 24/07/2026          
PACKING     LIST
%%%pp
TOTAL: USD 1,250.00
TOTAL: USD 1,250.00
||||||||||||
----1----
"""

        cleaned, report = clean_ocr_text(source)

        self.assertIn("INVOICE NO. IV-001", cleaned)
        self.assertIn("DATE: 24/07/2026", cleaned)
        self.assertIn("PACKING | LIST", cleaned)
        self.assertIn("TOTAL: USD 1,250.00", cleaned)
        self.assertIn("----1----", cleaned)
        self.assertNotIn("%%%pp", cleaned)
        self.assertNotIn("||||||||||||", cleaned)
        self.assertEqual(cleaned.count("TOTAL: USD 1,250.00"), 1)
        self.assertGreater(report["removed_characters"], 0)
        self.assertEqual(report["page_markers_before"], report["page_markers_after"])
        self.assertEqual(report["numeric_tokens_before"], report["numeric_tokens_after"])
        self.assertEqual(report["evidence_retention_percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
