import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from App.Rules_AI_BEM_MEIKO import (
    _merge_sections_by_rules,
    process_ai_llms_models_rules,
)


class SilentLogger:
    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


class ContractExtractionMergeTests(unittest.TestCase):
    def test_contract_keeps_first_non_null_value_and_merges_all_details(self):
        sections = [
            {
                "master": {
                    "SectionOrder": "1",
                    "SectionType": "CONTRACT",
                    "SectionTitle": "Contract first",
                    "TotalAmount": 100,
                    "TotalCurrency": None,
                    "Signature": None,
                },
                "details": [
                    {
                        "ContractNo": "CT-001",
                        "OrderDate": None,
                        "RingiNo": None,
                        "SupplierName": "Supplier first",
                        "Currency": None,
                        "DeliveryTerm": None,
                        "PaymentTerm": None,
                        "Amount": None,
                    },
                    {
                        "ContractNo": "CT-LATER-IN-SAME-CHUNK",
                        "OrderDate": "2026-08-01",
                        "RingiNo": "RINGI-01",
                        "SupplierName": "Supplier later",
                        "Currency": "USD",
                        "DeliveryTerm": "FOB HAI PHONG",
                        "PaymentTerm": None,
                        "Amount": 1000,
                    },
                ],
            },
            {
                "master": {
                    "SectionOrder": "2",
                    "SectionType": "CONTRACT",
                    "SectionTitle": "Contract later",
                    "TotalAmount": 200,
                    "TotalCurrency": "USD",
                    "Signature": "Signed",
                },
                "details": [
                    {
                        "ContractNo": "CT-LATER-CHUNK",
                        "OrderDate": "2026-08-02",
                        "RingiNo": "RINGI-02",
                        "SupplierName": "Supplier latest",
                        "Currency": "JPY",
                        "DeliveryTerm": "CIF TOKYO",
                        "PaymentTerm": "NET 30",
                        "Amount": 2000,
                    }
                ],
            },
        ]

        result = _merge_sections_by_rules(sections)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["master"]["SectionOrder"], "1")
        self.assertEqual(result[0]["master"]["SectionTitle"], "Contract first")
        self.assertEqual(result[0]["master"]["TotalAmount"], 100)
        self.assertEqual(result[0]["master"]["TotalCurrency"], "USD")
        self.assertEqual(result[0]["master"]["Signature"], "Signed")
        self.assertEqual(
            result[0]["details"],
            [{
                "ContractNo": "CT-001",
                "OrderDate": "2026-08-01",
                "RingiNo": "RINGI-01",
                "SupplierName": "Supplier first",
                "Currency": "USD",
                "DeliveryTerm": "FOB HAI PHONG",
                "PaymentTerm": "NET 30",
                "Amount": 1000,
                "OrderNo": "1",
            }],
        )

    def test_contract_stops_requesting_chunks_after_all_fields_are_filled(self):
        chunks = ["CHUNK-1", "CHUNK-2", "CHUNK-3"]
        llm_outputs = [
            {
                "sections": [{
                    "master": {"SectionType": "CONTRACT"},
                    "details": [{
                        "ContractNo": "CT-001",
                        "OrderDate": None,
                        "RingiNo": "RINGI-01",
                        "SupplierName": "Supplier first",
                        "Currency": "USD",
                        "DeliveryTerm": None,
                        "PaymentTerm": None,
                        "Amount": 1000,
                    }],
                }],
            },
            {
                "sections": [{
                    "master": {"SectionType": "CONTRACT"},
                    "details": [{
                        "ContractNo": "CT-LATER",
                        "OrderDate": "2026-08-01",
                        "RingiNo": "RINGI-LATER",
                        "SupplierName": "Supplier later",
                        "Currency": "JPY",
                        "DeliveryTerm": "FOB HAI PHONG",
                        "PaymentTerm": "NET 30",
                        "Amount": 2000,
                    }],
                }],
            },
        ]
        generated_prompts = []

        def generate_with_trim(**kwargs):
            generated_prompts.append(kwargs["base_messages"][1]["content"])
            return json.dumps(llm_outputs[len(generated_prompts) - 1])

        latest_user = "\n".join((
            "***",
            '{"Prompt_Type": "Trích xuất"}',
            "***",
            "Tên File: CT_001.pdf - Dữ liệu OCR: OCR-CONTENT",
        ))

        with TemporaryDirectory() as temp_dir:
            result, status_code = process_ai_llms_models_rules(
                latest_system="LEGACY SYSTEM PROMPT",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=lambda text, **kwargs: chunks,
                generate_with_trim_fn=generate_with_trim,
                append_response_log_fn=lambda payload: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=SilentLogger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(len(generated_prompts), 2)
        self.assertIn("CHUNK-1", generated_prompts[0])
        self.assertIn("CHUNK-2", generated_prompts[1])
        self.assertEqual(len(result["sections"]), 1)
        self.assertEqual(len(result["sections"][0]["details"]), 1)
        self.assertEqual(result["sections"][0]["details"][0]["ContractNo"], "CT-001")
        self.assertEqual(result["sections"][0]["details"][0]["OrderDate"], "2026-08-01")
        self.assertEqual(result["sections"][0]["details"][0]["PaymentTerm"], "NET 30")

    def test_contract_requests_all_chunks_while_any_field_is_missing(self):
        generated_prompts = []
        partial_output = {
            "sections": [{
                "master": {"SectionType": "CONTRACT"},
                "details": [{
                    "ContractNo": "CT-001",
                    "OrderDate": "2026-08-01",
                    "RingiNo": "RINGI-01",
                    "SupplierName": "Supplier first",
                    "Currency": "USD",
                    "DeliveryTerm": "FOB HAI PHONG",
                    "PaymentTerm": None,
                    "Amount": 1000,
                }],
            }],
        }

        def generate_with_trim(**kwargs):
            generated_prompts.append(kwargs["base_messages"][1]["content"])
            return json.dumps(partial_output)

        latest_user = "\n".join((
            "***",
            '{"Prompt_Type": "Extract"}',
            "***",
            "T\u00ean File: CT_001.pdf - D\u1eef li\u1ec7u OCR: OCR-CONTENT",
        ))

        with TemporaryDirectory() as temp_dir:
            result, status_code = process_ai_llms_models_rules(
                latest_system="LEGACY SYSTEM PROMPT",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=lambda text, **kwargs: ["CHUNK-1", "CHUNK-2", "CHUNK-3"],
                generate_with_trim_fn=generate_with_trim,
                append_response_log_fn=lambda payload: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=SilentLogger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(len(generated_prompts), 3)
        self.assertIsNone(result["sections"][0]["details"][0]["PaymentTerm"])

    def test_contract_ignores_zero_amount_until_a_non_zero_amount_is_found(self):
        generated_prompts = []
        amounts = [0, 2500]

        def generate_with_trim(**kwargs):
            generated_prompts.append(kwargs["base_messages"][1]["content"])
            amount = amounts[len(generated_prompts) - 1]
            return json.dumps({
                "sections": [{
                    "master": {"SectionType": "CONTRACT"},
                    "details": [{
                        "ContractNo": "CT-001",
                        "OrderDate": "2026-08-01",
                        "RingiNo": "RINGI-01",
                        "SupplierName": "Supplier first",
                        "Currency": "USD",
                        "DeliveryTerm": "FOB HAI PHONG",
                        "PaymentTerm": "NET 30",
                        "Amount": amount,
                    }],
                }],
            })

        latest_user = "\n".join((
            "***",
            '{"Prompt_Type": "Extract"}',
            "***",
            "T\u00ean File: CT_001.pdf - D\u1eef li\u1ec7u OCR: OCR-CONTENT",
        ))

        with TemporaryDirectory() as temp_dir:
            result, status_code = process_ai_llms_models_rules(
                latest_system="LEGACY SYSTEM PROMPT",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=lambda text, **kwargs: ["CHUNK-1", "CHUNK-2", "CHUNK-3"],
                generate_with_trim_fn=generate_with_trim,
                append_response_log_fn=lambda payload: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=SilentLogger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(len(generated_prompts), 2)
        self.assertEqual(result["sections"][0]["details"][0]["Amount"], 2500)

    def test_contract_requests_all_chunks_when_amount_is_always_zero(self):
        generated_prompts = []

        def generate_with_trim(**kwargs):
            generated_prompts.append(kwargs["base_messages"][1]["content"])
            return json.dumps({
                "sections": [{
                    "master": {"SectionType": "CONTRACT"},
                    "details": [{
                        "ContractNo": "CT-001",
                        "OrderDate": "2026-08-01",
                        "RingiNo": "RINGI-01",
                        "SupplierName": "Supplier first",
                        "Currency": "USD",
                        "DeliveryTerm": "FOB HAI PHONG",
                        "PaymentTerm": "NET 30",
                        "Amount": 0,
                    }],
                }],
            })

        latest_user = "\n".join((
            "***",
            '{"Prompt_Type": "Extract"}',
            "***",
            "T\u00ean File: CT_001.pdf - D\u1eef li\u1ec7u OCR: OCR-CONTENT",
        ))

        with TemporaryDirectory() as temp_dir:
            result, status_code = process_ai_llms_models_rules(
                latest_system="LEGACY SYSTEM PROMPT",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=lambda text, **kwargs: ["CHUNK-1", "CHUNK-2", "CHUNK-3"],
                generate_with_trim_fn=generate_with_trim,
                append_response_log_fn=lambda payload: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=SilentLogger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(len(generated_prompts), 3)
        self.assertIsNone(result["sections"][0]["details"][0]["Amount"])


if __name__ == "__main__":
    unittest.main()
