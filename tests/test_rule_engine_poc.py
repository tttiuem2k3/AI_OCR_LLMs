import unittest
from decimal import Decimal

from App.rule_engine_poc import (
    RuleEngineNotAvailableError,
    evaluate_nvl_amount_rule,
    evaluate_nvl_currency_rule,
)


class RuleEnginePocTests(unittest.TestCase):
    def test_currency_rule_returns_ok_when_required_evidence_matches_dntt_currency(self):
        result = evaluate_nvl_currency_rule(
            {
                "dntt": {"currency": "USD"},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "currency": "USD"},
                    {"doc_type": "PO", "file_name": "po.pdf", "currency": "USD"},
                    {"doc_type": "RINGI", "file_name": "ringi.pdf", "currency": "USD"},
                    {"doc_type": "INVOICE", "file_name": "invoice.pdf", "currency": "USD"},
                ],
            }
        )

        self.assertEqual(result.status, "OK")
        self.assertEqual(result.criterion, "LOAITIEN")
        self.assertEqual(result.rule_version, "nvl-poc-2026-10-06")
        self.assertIn("CUSTOMSHEET", result.evidence)
        self.assertIn("INVOICE", result.evidence)

    def test_currency_rule_returns_review_when_required_evidence_is_missing(self):
        result = evaluate_nvl_currency_rule(
            {
                "dntt": {"currency": "USD"},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "currency": "USD"},
                    {"doc_type": "PO", "file_name": "po.pdf", "currency": "USD"},
                ],
            }
        )

        self.assertEqual(result.status, "REVIEW")
        self.assertIn("Thiếu chứng từ", result.reason)
        self.assertIn("RINGI", result.reason)

    def test_amount_rule_returns_ok_when_multiple_invoices_sum_to_dntt_amount(self):
        result = evaluate_nvl_amount_rule(
            {
                "dntt": {"amount": Decimal("1500.00")},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "RINGI", "file_name": "ringi.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "INVOICE", "file_name": "invoice-1.pdf", "amount": Decimal("1000.00")},
                    {"doc_type": "INVOICE", "file_name": "invoice-2.pdf", "amount": Decimal("500.00")},
                ],
            }
        )

        self.assertEqual(result.status, "OK")
        self.assertEqual(result.criterion, "SOTIEN")
        self.assertEqual(result.evidence["invoice_total"], "1500.00")
        self.assertEqual(result.evidence["invoice_files"], ["invoice-1.pdf", "invoice-2.pdf"])

    def test_amount_rule_does_not_double_count_statement_and_invoice_total(self):
        result = evaluate_nvl_amount_rule(
            {
                "dntt": {"amount": Decimal("1500.00")},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "RINGI", "file_name": "ringi.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "INVOICE", "file_name": "invoice-1.pdf", "amount": Decimal("1000.00")},
                    {"doc_type": "INVOICE", "file_name": "invoice-2.pdf", "amount": Decimal("500.00")},
                    {"doc_type": "STATEMENT", "file_name": "statement.xlsx", "amount": Decimal("1500.00")},
                ],
            }
        )

        self.assertEqual(result.status, "OK")
        self.assertEqual(result.evidence["invoice_total"], "1500.00")
        self.assertEqual(result.evidence["statement_amount"], "1500.00")

    def test_amount_rule_returns_review_when_statement_conflicts_with_invoice_total(self):
        result = evaluate_nvl_amount_rule(
            {
                "dntt": {"amount": Decimal("1500.00")},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "RINGI", "file_name": "ringi.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "INVOICE", "file_name": "invoice.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "STATEMENT", "file_name": "statement.xlsx", "amount": Decimal("1600.00")},
                ],
            }
        )

        self.assertEqual(result.status, "REVIEW")
        self.assertIn("mâu thuẫn", result.reason)

    def test_amount_rule_returns_review_when_evidence_is_conflicting(self):
        result = evaluate_nvl_amount_rule(
            {
                "dntt": {"amount": Decimal("1500.00")},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "amount": Decimal("1500.00")},
                    {"doc_type": "RINGI", "file_name": "ringi.pdf", "amount": Decimal("1600.00")},
                    {"doc_type": "INVOICE", "file_name": "invoice-1.pdf", "amount": Decimal("1500.00")},
                ],
            }
        )

        self.assertEqual(result.status, "REVIEW")
        self.assertIn("mâu thuẫn", result.reason)
        self.assertEqual(result.evidence["customsheet_amount"], "1500.00")
        self.assertEqual(result.evidence["ringi_amount"], "1600.00")

    def test_amount_rule_returns_ng_when_evidence_is_complete_but_amount_does_not_match(self):
        result = evaluate_nvl_amount_rule(
            {
                "dntt": {"amount": Decimal("1500.00")},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "amount": Decimal("1400.00")},
                    {"doc_type": "RINGI", "file_name": "ringi.pdf", "amount": Decimal("1400.00")},
                    {"doc_type": "INVOICE", "file_name": "invoice-1.pdf", "amount": Decimal("1400.00")},
                ],
            }
        )

        self.assertEqual(result.status, "NG")
        self.assertIn("DNTT", result.reason)

    def test_currency_rule_returns_ng_when_complete_evidence_has_wrong_currency(self):
        result = evaluate_nvl_currency_rule(
            {
                "dntt": {"currency": "USD"},
                "evidence": [
                    {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "currency": "USD"},
                    {"doc_type": "PO", "file_name": "po.pdf", "currency": "USD"},
                    {"doc_type": "RINGI", "file_name": "ringi.pdf", "currency": "USD"},
                    {"doc_type": "INVOICE", "file_name": "invoice.pdf", "currency": "JPY"},
                ],
            }
        )

        self.assertEqual(result.status, "NG")
        self.assertIn("DNTT", result.reason)

    def test_rule_returns_not_applicable_when_criterion_is_disabled_for_case(self):
        result = evaluate_nvl_currency_rule(
            {
                "applicable": False,
                "dntt": {"currency": "USD"},
                "evidence": [],
            }
        )

        self.assertEqual(result.status, "N/A")
        self.assertIn("không áp dụng", result.reason)

    def test_poc_exposes_clear_error_if_rule_engine_library_is_not_installed(self):
        import App.rule_engine_poc as poc

        original = poc.rule_engine
        poc.rule_engine = None
        try:
            with self.assertRaises(RuleEngineNotAvailableError):
                evaluate_nvl_currency_rule(
                    {
                        "dntt": {"currency": "USD"},
                        "evidence": [
                            {"doc_type": "CUSTOMSHEET", "file_name": "tk.pdf", "currency": "USD"},
                            {"doc_type": "PO", "file_name": "po.pdf", "currency": "USD"},
                            {"doc_type": "RINGI", "file_name": "ringi.pdf", "currency": "USD"},
                            {"doc_type": "INVOICE", "file_name": "invoice.pdf", "currency": "USD"},
                        ],
                    }
                )
        finally:
            poc.rule_engine = original


if __name__ == "__main__":
    unittest.main()
