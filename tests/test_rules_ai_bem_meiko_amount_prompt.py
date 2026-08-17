import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import App.Rules_AI_BEM_MEIKO as rules


class AmountComparePromptTests(unittest.TestCase):
    class Logger:
        def warning(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

    def test_amount_prompt_normalizes_zero_fraction_to_two_decimals(self):
        directive = {
            "PromptType": "Doi chieu",
            "DnttType": "Nguyen vat lieu",
            "FormationID": "Ke thua cong no",
            "Installment": "",
            "CriterionName": "So tien",
        }
        content = "\n".join((
            "1. Du lieu de nghi thanh toan (DNTT):",
            "{ So hoa don: 00000069 | So tien yeu cau: 50105440.00000000 }",
            "=> Tong so tien yeu cau: 50105440.00000000",
            "2. Du lieu dau vao:",
            "{ Loai chung tu: CUSTOMSHEET | So hoa don: 00000069 | So tien: 50105440 | Ten file: custom.xlsx }",
            "{ Loai chung tu: INVOICE | So hoa don: 00000069 | So tien: 50105440 | Ten file: invoice.pdf }",
        ))
        latest_user = f"***\n{json.dumps(directive)}\n***\n{content}"
        captured = {}
        events = []
        snapshots = []

        def generate_with_trim(**kwargs):
            events.append("generate")
            captured.update(kwargs)
            return json.dumps({
                "criteria": {
                    "CriteriaName": "So tien",
                    "CriteriaStatus": "OK",
                    "FileName": "",
                    "Description": "Amounts match.",
                }
            })

        def capture_snapshot(messages, extra):
            events.append("snapshot")
            snapshots.append((messages, extra))

        with TemporaryDirectory() as temp_dir:
            result, status_code = rules.process_ai_llms_models_rules(
                latest_system="system prompt",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=lambda **kwargs: [],
                generate_with_trim_fn=generate_with_trim,
                append_prompt_client_snapshot_fn=capture_snapshot,
                append_response_log_fn=lambda payload: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=self.Logger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
        sent_user = captured["base_messages"][1]["content"]
        self.assertIn("So tien yeu cau: 50105440.00", sent_user)
        self.assertIn("Tong so tien yeu cau: 50105440.00", sent_user)
        self.assertNotIn("50105440.00000000", sent_user)
        self.assertIs(captured["think"], True)
        self.assertEqual(events, ["snapshot", "generate"])
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0][0], captured["base_messages"])
        self.assertEqual(
            snapshots[0][1],
            {
                "stage": "after_compare_filter_before_llm",
                "prompt_mode": "DOICHIEU",
                "dntt_type": "NGUYENVATLIEU",
                "formation_id": "KETHUA_CONGNO",
                "installment": "",
                "criterion_name": "So tien",
                "removed_extra_lines": 0,
                "normalized_amount_fields": 2,
            },
        )

    def test_zero_fraction_keeps_two_decimals_but_integer_stays_integer(self):
        self.assertEqual(rules._normalize_money_number_token("1234.0000000"), "1234.00")
        self.assertEqual(rules._normalize_money_number_token("1234"), "1234")

    def test_non_amount_compare_enables_thinking(self):
        directive = {
            "PromptType": "Doi chieu",
            "DnttType": "Nguyen vat lieu",
            "FormationID": "Ke thua cong no",
            "Installment": "",
            "CriterionName": "So hoa don",
        }
        content = "\n".join((
            "{ Loai chung tu: CUSTOMSHEET | So hoa don: 00000069 | So tien: 50105440 | Ten file: custom.xlsx }",
            "{ Loai chung tu: INVOICE | So hoa don: 00000069 | So tien: 50105440 | Ten file: invoice.pdf }",
        ))
        latest_user = f"***\n{json.dumps(directive)}\n***\n{content}"
        captured = {}

        def generate_with_trim(**kwargs):
            captured.update(kwargs)
            return json.dumps({
                "criteria": {
                    "CriteriaName": "So hoa don",
                    "CriteriaStatus": "OK",
                    "FileName": "",
                    "Description": "Invoice numbers match.",
                }
            })

        with TemporaryDirectory() as temp_dir:
            result, status_code = rules.process_ai_llms_models_rules(
                latest_system="system prompt",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=lambda **kwargs: [],
                generate_with_trim_fn=generate_with_trim,
                append_response_log_fn=lambda payload: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=self.Logger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
        self.assertIs(captured["think"], True)

    def test_empty_compare_input_reports_required_all_documents_from_default_rule(self):
        latest_user = """***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Xây dựng",
 "FormationID": "Kế thừa công nợ",
 "Installment": "Lần cuối",
 "CriterionName": "Số hóa đơn"
}
***
1. Dữ liệu đề nghị thanh toán (ĐNTT):
{ Số hóa đơn: 00000139 }

2. Dữ liệu đầu vào:"""

        def fail_if_llm_called(**kwargs):
            raise AssertionError("LLM không được gọi khi dữ liệu đầu vào rỗng")

        with TemporaryDirectory() as temp_dir:
            result, status_code = rules.process_ai_llms_models_rules(
                latest_system="system prompt",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=lambda **kwargs: [],
                generate_with_trim_fn=fail_if_llm_called,
                append_response_log_fn=lambda payload: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=self.Logger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")
        self.assertEqual(
            result["criteria"]["Description"],
            "Thiếu các loại chứng từ bắt buộc để đối chiếu Số hóa đơn là hóa đơn và tờ khai hải quan",
        )


if __name__ == "__main__":
    unittest.main()
