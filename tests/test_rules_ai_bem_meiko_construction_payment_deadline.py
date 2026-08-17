import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from App.Rules_AI_BEM_MEIKO import (
    _build_xaydung_payment_deadline_source,
    process_ai_llms_models_rules,
)


class ConstructionPaymentDeadlineSourceTests(unittest.TestCase):
    def test_advance_uses_all_contract_dates_and_ignores_interleaved_docs(self):
        content = """
{ Loại chứng từ: CONTRACT | Ngày hợp đồng: 12/02/2027 | Tên file: contract-1.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hiện trường | Ngày biên bản nghiệm thu: 13/02/2027 | Tên file: ignored.pdf }
{ Loại chứng từ: CONTRACT | Ngày hợp đồng: 15/02/2027 | Tên file: contract-2.pdf }
"""

        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Đặt cọc/trả trước", "Installment": ""},
            content,
        )

        self.assertEqual(
            result,
            {
                "DueDate": "12/02/2027, 15/02/2027",
                "FileName": "contract-1.pdf, contract-2.pdf",
                "Description": "",
            },
        )

    def test_installments_one_and_two_accept_only_material_handover(self):
        content = """
{ Loại chứng từ: HANDOVER | Loại biên bản bàn giao: Biên bản bàn giao - Handover | Ngày biên bản bàn giao: 07/04/2027 | Tên file: general.pdf }
{ Loại chứng từ: HANDOVER | Loại biên bản bàn giao: Bien ban ban giao vat tu | Ngày biên bản bàn giao: 08/04/2027 | Tên file: material-handover.pdf }
"""

        for installment in ("Lần 1", "Lan 2"):
            with self.subTest(installment=installment):
                result = _build_xaydung_payment_deadline_source(
                    {"FormationID": "Kế thừa công nợ", "Installment": installment},
                    content,
                )

                self.assertEqual(result["DueDate"], "08/04/2027")
                self.assertEqual(result["FileName"], "material-handover.pdf")

    def test_before_last_accepts_accentless_system_inspection(self):
        content = """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Bien ban nghiem thu he thong | Ngày biên bản nghiệm thu: 16/06/2027 | Tên file: system.pdf }
"""

        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Ke thua cong no", "Installment": "Truoc lan cuoi"},
            content,
        )

        self.assertEqual(result["DueDate"], "16/06/2027")
        self.assertEqual(result["FileName"], "system.pdf")

    def test_installment_three_and_six_use_field_inspection(self):
        content = """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Biên bản nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 19/07/2027 | Tên file: system.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Biên bản nghiệm thu hiện trường | Ngày biên bản nghiệm thu: 20/07/2027 | Tên file: field-inspection.pdf }
"""

        for installment in ("Lần 3", "Lan 6"):
            with self.subTest(installment=installment):
                result = _build_xaydung_payment_deadline_source(
                    {"FormationID": "Kế thừa công nợ", "Installment": installment},
                    content,
                )

                self.assertEqual(result["DueDate"], "20/07/2027")
                self.assertEqual(result["FileName"], "field-inspection.pdf")

    def test_final_prefers_all_valid_one_year_inspections(self):
        content = """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Biên bản nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 10/05/2026 | Tên file: system.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu sau một năm | Ngày biên bản nghiệm thu: 14/05/2027 | Tên file: one-year-1.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiem thu sau 1 nam | Ngày biên bản nghiệm thu: 20/05/2027 | Tên file: one-year-2.pdf }
"""

        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            content,
        )

        self.assertEqual(result["DueDate"], "14/05/2027, 20/05/2027")
        self.assertEqual(result["FileName"], "one-year-1.pdf, one-year-2.pdf")

    def test_final_falls_back_to_system_when_one_year_dates_are_invalid(self):
        content = """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu sau một năm | Ngày biên bản nghiệm thu: 31/02/2027 | Tên file: invalid-one-year.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 21/09/2026 | Tên file: system.pdf }
"""

        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            content,
        )

        self.assertEqual(result["DueDate"], "21/09/2027")
        self.assertEqual(result["FileName"], "system.pdf")

    def test_final_converts_leap_day_to_february_end(self):
        content = """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 29/02/2024 | Tên file: leap-system.pdf }
"""

        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            content,
        )

        self.assertEqual(result["DueDate"], "28/02/2025")

    def test_business_errors_distinguish_rule_document_and_date_failures(self):
        invalid_formation = _build_xaydung_payment_deadline_source(
            {"FormationID": "Khác", "Installment": "Lần 1"},
            "",
        )
        invalid_installment = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": ""},
            "",
        )
        no_matching_document = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần 3"},
            "{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 01/01/2027 | Tên file: system.pdf }",
        )
        matching_document_invalid_date = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần 3"},
            "{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hiện trường | Ngày biên bản nghiệm thu: 31/02/2027 | Tên file: field.pdf }",
        )

        self.assertEqual(
            invalid_formation,
            {
                "DueDate": None,
                "FileName": "",
                "Description": "Không xác định được Nguồn hình thành.",
            },
        )
        self.assertEqual(
            invalid_installment["Description"],
            "Không xác định được quy tắc theo Lần thanh toán.",
        )
        self.assertEqual(
            no_matching_document["Description"],
            'Không có chứng từ phù hợp: Nguồn hình thành = Kế thừa công nợ; '
            'Lần thanh toán = Lần 3; yêu cầu Biên bản nghiệm thu có '
            'Loại biên bản nghiệm thu chứa "nghiệm thu hiện trường".',
        )
        self.assertEqual(
            matching_document_invalid_date["Description"],
            "Không có ngày mốc hợp lệ từ chứng từ bắt buộc.",
        )

    def test_final_returns_null_when_both_priority_groups_are_unavailable(self):
        no_matching = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            "{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hiện trường | Ngày biên bản nghiệm thu: 01/01/2027 | Tên file: field.pdf }",
        )
        invalid_dates = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu sau một năm | Ngày biên bản nghiệm thu: null | Tên file: one-year.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 31/02/2027 | Tên file: system.pdf }
""",
        )

        self.assertIsNone(no_matching["DueDate"])
        self.assertEqual(
            no_matching["Description"],
            'Không có chứng từ phù hợp: Nguồn hình thành = Kế thừa công nợ; '
            'Lần thanh toán = Lần cuối; yêu cầu Biên bản nghiệm thu thuộc loại '
            '"nghiệm thu sau một năm" hoặc "nghiệm thu hệ thống".',
        )
        self.assertIsNone(invalid_dates["DueDate"])
        self.assertEqual(
            invalid_dates["Description"],
            "Không có ngày mốc hợp lệ từ chứng từ bắt buộc.",
        )

    def test_missing_document_descriptions_use_vietnamese_document_names(self):
        cases = [
            (
                {"FormationID": "Đặt cọc/trả trước", "Installment": "Lần 1"},
                "Không có chứng từ phù hợp: Nguồn hình thành = Đặt cọc/trả trước; "
                "Lần thanh toán = Lần 1; yêu cầu Hợp đồng có Ngày hợp đồng.",
            ),
            (
                {"FormationID": "Kế thừa công nợ", "Installment": "Lần 2"},
                "Không có chứng từ phù hợp: Nguồn hình thành = Kế thừa công nợ; "
                'Lần thanh toán = Lần 2; yêu cầu Biên bản bàn giao có '
                'Loại biên bản bàn giao chứa "bàn giao vật tư".',
            ),
            (
                {"FormationID": "Kế thừa công nợ", "Installment": "Trước lần cuối"},
                "Không có chứng từ phù hợp: Nguồn hình thành = Kế thừa công nợ; "
                'Lần thanh toán = Trước lần cuối; yêu cầu Biên bản nghiệm thu có '
                'Loại biên bản nghiệm thu chứa "nghiệm thu hệ thống".',
            ),
        ]

        for prompt_info, expected_description in cases:
            with self.subTest(prompt_info=prompt_info):
                result = _build_xaydung_payment_deadline_source(prompt_info, "")

                self.assertEqual(result["Description"], expected_description)
                self.assertNotIn("CONTRACT", result["Description"])
                self.assertNotIn("HANDOVER", result["Description"])
                self.assertNotIn("INSPECTION", result["Description"])

    def test_deduplicates_dates_and_limits_only_file_names(self):
        blocks = [
            "{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hiện trường | "
            f"Ngày biên bản nghiệm thu: {day:02d}/01/2027 | Tên file: field-{day}.pdf }}"
            for day in range(1, 13)
        ]
        blocks.insert(
            1,
            "{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hiện trường | "
            "Ngày biên bản nghiệm thu: 01/01/2027 | Tên file: duplicate-date.pdf }",
        )

        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần 4"},
            chr(10).join(blocks),
        )

        self.assertEqual(len(result["DueDate"].split(", ")), 12)
        self.assertEqual(len(result["FileName"].split(", ")), 10)
        self.assertNotIn("duplicate-date.pdf", result["FileName"])


class ConstructionPaymentDeadlineIntegrationTests(unittest.TestCase):
    class Logger:
        def warning(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

    def _run_process(self, latest_user: str, data_holidays_dir: Path):
        response_logs = []
        cleanup_calls = []

        def fail_if_llm_called(**kwargs):
            raise AssertionError("LLM không được gọi cho Hạn thanh toán Xây dựng")

        result, status_code = process_ai_llms_models_rules(
            latest_system="",
            latest_user=latest_user,
            cfg={},
            special_id="test-model",
            max_new_tokens=128,
            temperature=0.0,
            ocr_split_max_pages=5,
            ocr_split_overlap_pages=0,
            normalize_txt_path=data_holidays_dir / "normalize.txt",
            sections_txt_path=data_holidays_dir / "sections.txt",
            data_holidays_dir=data_holidays_dir,
            split_ocr_text_fn=lambda **kwargs: [],
            generate_with_trim_fn=fail_if_llm_called,
            append_response_log_fn=response_logs.append,
            light_cuda_cleanup_fn=lambda: cleanup_calls.append(True),
            logger=self.Logger(),
        )
        return result, status_code, response_logs, cleanup_calls

    def test_scoped_branch_uses_construction_rules_without_calling_llm(self):
        latest_user = """***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Xây dựng",
 "FormationID": "Kế thừa công nợ",
 "Installment": "Lần 3",
 "CriterionName": "Hạn thanh toán",
 "Deadline": "31/05/2026"
}
***
1. Dữ liệu đề nghị thanh toán (ĐNTT):
{ Nguồn hình thành: Kế thừa công nợ | Lần thanh toán: Lần 3 }

2. Dữ liệu đầu vào:
{ Loại chứng từ: HANDOVER | Loại biên bản bàn giao: Biên bản bàn giao - Handover | Ngày biên bản bàn giao: 14/05/2026 | Tên file: CT-25-197-Biên bản bàn giao.pdf }
{ Loại chứng từ: CONTRACT | Ngày hợp đồng: 10/05/2026 | Tên file: CT-25-197-Trang hợp đồng thể hiện điều kiện thanh toán.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Biên bản nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 06/05/2026 | Tên file: CT-25-197-Nghiệm thu hệ thống.pdf }
"""

        with TemporaryDirectory() as temp_dir:
            result, status_code, response_logs, cleanup_calls = self._run_process(
                latest_user,
                Path(temp_dir),
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
                        "Không có chứng từ phù hợp: Nguồn hình thành = Kế thừa công nợ; "
                        "Lần thanh toán = Lần 3; yêu cầu Biên bản nghiệm thu có "
                        'Loại biên bản nghiệm thu chứa "nghiệm thu hiện trường".'
                    ),
                    "DueDateAI": None,
                }
            },
        )
        self.assertEqual(len(response_logs), 1)
        self.assertEqual(cleanup_calls, [True])

    def test_scoped_branch_normalizes_weekend_before_comparing_deadline(self):
        latest_user = """***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Xây dựng",
 "FormationID": "Đặt cọc/trả trước",
 "Installment": "",
 "CriterionName": "Hạn thanh toán",
 "Deadline": "01/01/2027"
}
***
Dữ liệu đầu vào:
{ Loại chứng từ: CONTRACT | Ngày hợp đồng: 03/01/2027 | Tên file: contract.pdf }
"""

        with TemporaryDirectory() as temp_dir:
            holiday_dir = Path(temp_dir)
            (holiday_dir / "2027.json").write_text(
                json.dumps(
                    {
                        "Master": {"HolidaySettingCode": "TEST/2027", "Year": 2027},
                        "Detail": {
                            "WeeklyDaysOff": {
                                "IsWorkMon": True,
                                "IsWorkTues": True,
                                "IsWorkWed": True,
                                "IsWorkThurs": True,
                                "IsWorkFri": True,
                                "IsWorkSat": False,
                                "IsWorkSun": False,
                            },
                            "PublicHolidays": [],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result, status_code, response_logs, cleanup_calls = self._run_process(
                latest_user,
                holiday_dir,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
        self.assertEqual(result["criteria"]["DueDateAI"], "01/01/2027")
        self.assertEqual(len(response_logs), 1)
        self.assertEqual(cleanup_calls, [True])


if __name__ == "__main__":
    unittest.main()
