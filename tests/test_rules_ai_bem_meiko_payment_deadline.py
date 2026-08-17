import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from App.Rules_AI_BEM_MEIKO import (
    _build_payment_deadline_result,
    _build_nguyenvatlieu_payment_deadline_source,
    process_ai_llms_models_rules,
)


class PaymentDeadlineSourceTests(unittest.TestCase):
    def test_ams90_preserves_anchor_order_and_removes_duplicates(self):
        content = """
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 10/03/2026 | Tên file: CUS_1.xlsx }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 12/03/2026 | Tên file: CUS_2.xlsx }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 18/03/2026 | Tên file: CUS_3.xlsx }
{ Loại chứng từ: PO | PaymentTerm: AMS 90 days by TT | Tên file: PO_1.pdf }
{ Loại chứng từ: PO | PaymentTerm: AMS90 | Tên file: PO_2.pdf }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 04/03/2026 | Tên file: CUS_4.xlsx }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 27/02/2026 | Tên file: CUS_5.xlsx }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 12/03/2026 | Tên file: CUS_6.xlsx }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 05/03/2026 | Tên file: CUS_7.xlsx }
"""

        result = _build_nguyenvatlieu_payment_deadline_source(content)

        self.assertEqual(
            result,
            {
                "DueDate": "08/06/2026, 10/06/2026, 16/06/2026, 02/06/2026, 28/05/2026, 03/06/2026",
                "FileName": "",
                "Description": "",
            },
        )

    def test_after_bl_uses_invoice_dates_and_supports_two_digit_years(self):
        content = """
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 15/01/2026 | Tên file: ignored.xlsx }
{ Loại chứng từ: PO | PaymentTerm: 30 days after B/L date by T/T | Tên file: PO_1.pdf }
{ Loại chứng từ: INVOICE | Ngày hóa đơn: 01/01/26 | Tên file: INV_1.pdf }
{ Loại chứng từ: COMMERCIALINVOICE | Ngày hóa đơn: 02-01-2026 | Tên file: INV_2.pdf }
"""

        result = _build_nguyenvatlieu_payment_deadline_source(content)

        self.assertEqual(result["DueDate"], "31/01/2026, 01/02/2026")

    def test_invalid_payment_terms_are_ignored_when_selecting_majority(self):
        content = """
{ Loại chứng từ: PO | PaymentTerm: CASH | Tên file: invalid.pdf }
{ Loại chứng từ: PO | PaymentTerm: AMS 60 DAYS | Tên file: valid_1.pdf }
{ Loại chứng từ: PO | PaymentTerm: AMS60 TTT | Tên file: valid_2.pdf }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 01/01/2026 | Tên file: CUS.pdf }
"""

        result = _build_nguyenvatlieu_payment_deadline_source(content)

        self.assertEqual(result["DueDate"], "02/03/2026")

    def test_tied_payment_terms_return_at_most_ten_po_file_names(self):
        po_blocks = []
        for index in range(1, 7):
            po_blocks.append(
                f"{{ Loại chứng từ: PO | PaymentTerm: AMS30 | Tên file: AMS_{index}.pdf }}"
            )
            po_blocks.append(
                f"{{ Loại chứng từ: PO | PaymentTerm: AMS60 | Tên file: AMS_{index + 6}.pdf }}"
            )

        result = _build_nguyenvatlieu_payment_deadline_source("\n".join(po_blocks))

        self.assertIsNone(result["DueDate"])
        self.assertEqual(result["Description"], "Có nhiều điều khoản thanh toán khác nhau")
        self.assertEqual(len(result["FileName"].split(", ")), 10)
        self.assertEqual(
            result["FileName"],
            "AMS_1.pdf, AMS_7.pdf, AMS_2.pdf, AMS_8.pdf, AMS_3.pdf, AMS_9.pdf, AMS_4.pdf, AMS_10.pdf, AMS_5.pdf, AMS_11.pdf",
        )

    def test_missing_valid_payment_term_returns_business_error(self):
        content = """
{ Loại chứng từ: PO | PaymentTerm: CASH | Tên file: PO_1.pdf }
{ Loại chứng từ: PO | PaymentTerm: AMS DAYS | Tên file: PO_2.pdf }
"""

        result = _build_nguyenvatlieu_payment_deadline_source(content)

        self.assertEqual(
            result,
            {
                "DueDate": None,
                "FileName": "",
                "Description": "Không tìm thấy điều khoản thanh toán AMS hoặc AFTER B/L hợp lệ trong chứng từ PO",
            },
        )

    def test_missing_ams_anchor_returns_business_error(self):
        content = """
{ Loại chứng từ: PO | PaymentTerm: AMS30 | Tên file: PO_1.pdf }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: null | Tên file: CUS_1.xlsx }
"""

        result = _build_nguyenvatlieu_payment_deadline_source(content)

        self.assertIsNone(result["DueDate"])
        self.assertEqual(
            result["Description"],
            "Không tìm thấy Ngày hoàn thành kiểm tra hợp lệ của chứng từ CUSTOMSHEET",
        )

    def test_missing_after_bl_anchor_returns_business_error(self):
        content = """
{ Loại chứng từ: PO | PaymentTerm: 60 AFTER BL | Tên file: PO_1.pdf }
{ Loại chứng từ: INVOICE | Ngày hóa đơn: 31/02/2026 | Tên file: INV_1.pdf }
"""

        result = _build_nguyenvatlieu_payment_deadline_source(content)

        self.assertIsNone(result["DueDate"])
        self.assertEqual(
            result["Description"],
            "Không tìm thấy Ngày hóa đơn hợp lệ của chứng từ INVOICE hoặc COMMERCIALINVOICE",
        )


class PaymentDeadlineIntegrationTests(unittest.TestCase):
    def test_single_failed_due_date_is_included_in_description(self):
        result = _build_payment_deadline_result(
            prompt_info={"Deadline": "29/05/2026"},
            parsed_llm={
                "DueDate": "08/06/2026",
                "FileName": "",
                "Description": "",
            },
            raw_llm_text="",
            criterion_name="Hạn thanh toán",
            data_holidays_dir=str(Path("App/Data_Holidays")),
        )

        self.assertEqual(
            result,
            {
                "criteria": {
                    "CriteriaName": "Hạn thanh toán",
                    "CriteriaStatus": "NG",
                    "FileName": "",
                    "Description": (
                        "Ngày hạn thanh toán trên ĐNTT là 29/05/2026 sớm hơn ngày hạn thanh toán chuẩn được tính: "
                        "08/06/2026 (ngày không thỏa điều kiện)."
                    ),
                    "DueDateAI": "08/06/2026",
                }
            },
        )

    def test_scoped_compare_branch_returns_without_calling_llm(self):
        latest_user = """***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Nguyên vật liệu",
 "FormationID": "Kế thừa công nợ",
 "Installment": "",
 "CriterionName": "Hạn thanh toán",
 "Deadline": "30/05/2026"
}
***
Dữ liệu chứng từ:
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 10/03/2026 | Tên file: CUS_1.xlsx }
{ Loại chứng từ: PO | PaymentTerm: AMS 90 days by TT | Tên file: PO_1.pdf }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 27/02/2026 | Tên file: CUS_2.xlsx }
"""
        response_logs = []
        cleanup_calls = []

        def fail_if_llm_called(**kwargs):
            raise AssertionError("LLM không được gọi cho nhánh Hạn thanh toán Nguyên vật liệu")

        class Logger:
            def warning(self, *args, **kwargs):
                pass

            def info(self, *args, **kwargs):
                pass

        with TemporaryDirectory() as temp_dir:
            result, status_code = process_ai_llms_models_rules(
                latest_system="",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                data_holidays_dir=Path("App/Data_Holidays"),
                split_ocr_text_fn=lambda **kwargs: [],
                generate_with_trim_fn=fail_if_llm_called,
                append_response_log_fn=response_logs.append,
                light_cuda_cleanup_fn=lambda: cleanup_calls.append(True),
                logger=Logger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(
            result,
            {
                "criteria": {
                    "CriteriaName": "Hạn thanh toán",
                    "CriteriaStatus": "NG",
                    "FileName": "",
                    "Description": (
                        "Ngày hạn thanh toán trên ĐNTT là 30/05/2026 sớm hơn ngày hạn thanh toán chuẩn được tính: "
                        "08/06/2026 (các ngày không thỏa điều kiện). "
                        "=> Ngày hợp lệ là: 28/05/2026."
                    ),
                    "DueDateAI": "08/06/2026, 28/05/2026",
                }
            },
        )
        self.assertEqual(len(response_logs), 1)
        self.assertEqual(cleanup_calls, [True])


if __name__ == "__main__":
    unittest.main()
