import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from App.Rules_AI_BEM_MEIKO import (
    _filter_extract_system_prompt_by_doc_types,
    _normalize_extract_section_type_by_filename,
    _resolve_extract_doc_types_by_filename,
    process_ai_llms_models_rules,
)


class SilentLogger:
    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


class ExtractFilenameMappingTests(unittest.TestCase):
    def test_filename_prefixes_are_case_insensitive(self):
        cases = {
            "IV_001.pdf": ("INVOICE",),
            "inv_001.pdf": ("INVOICE",),
            "Vat_001.pdf": ("INVOICE",),
            "cus_001.xlsx": ("CUSTOMSHEET",),
            "ToKhaiHQ7N_QDTQ_108183074860.xls": ("CUSTOMSHEET",),
            "PO_001.pdf": ("PO",),
            "ring_001.pdf": ("RINGI",),
            "List_001.pdf": ("STATEMENT",),
            "com_001.pdf": ("COMMERCIALINVOICE",),
            "pl_001.pdf": ("PACKINGLIST",),
            "Bill_001.pdf": ("BILL",),
            "ct_001.pdf": ("CONTRACT",),
            "Inspec_001.pdf": ("INSPECTION",),
            "handover_001.pdf": ("HANDOVER",),
            "Other_001.pdf": ("OTHER",),
        }

        for file_name, expected in cases.items():
            with self.subTest(file_name=file_name):
                self.assertEqual(
                    _resolve_extract_doc_types_by_filename(file_name),
                    expected,
                )

    def test_combined_prefixes_are_checked_before_invoice_prefix(self):
        cases = {
            "IV_PL_001.pdf": ("INVOICE", "PACKINGLIST"),
            "INV_PL_001.pdf": ("INVOICE", "PACKINGLIST"),
            "in_pl_001.pdf": ("INVOICE", "PACKINGLIST"),
            "Com_PL_001.pdf": ("COMMERCIALINVOICE", "PACKINGLIST"),
        }

        for file_name, expected in cases.items():
            with self.subTest(file_name=file_name):
                self.assertEqual(
                    _resolve_extract_doc_types_by_filename(file_name),
                    expected,
                )

    def test_unknown_prefix_uses_unmapped_prompt_group(self):
        self.assertEqual(
            _resolve_extract_doc_types_by_filename("ABC_IV_001.pdf"),
            ("UNMAPPED",),
        )

    def test_empty_filename_does_not_use_unmapped_prompt_group(self):
        self.assertEqual(_resolve_extract_doc_types_by_filename(""), ())


class ExtractSectionTypeNormalizationTests(unittest.TestCase):
    def test_single_prefix_keeps_only_its_expected_section_type(self):
        cases = (
            ("IV_001.pdf", "COMMERCIALINVOICE", "INVOICE"),
            ("COM_001.pdf", "INVOICE", "COMMERCIALINVOICE"),
        )

        for file_name, source_type, expected_type in cases:
            with self.subTest(file_name=file_name):
                sections = [
                    {"master": {"SectionType": source_type}},
                    {"master": {"SectionType": "PO"}},
                    {"master": {"SectionType": "CUSTOMSHEET"}},
                ]

                result = _normalize_extract_section_type_by_filename(sections, file_name)

                self.assertEqual(
                    [section["master"]["SectionType"] for section in result],
                    [expected_type],
                )

    def test_pl_prefix_keeps_only_existing_packinglist_sections(self):
        sections = [
            {"master": {"SectionType": "PACKINGLIST"}},
            {"master": {"SectionType": "INVOICE"}},
            {"master": {"SectionType": "COMMERCIALINVOICE"}},
            {"master": {"SectionType": "PO"}},
        ]

        result = _normalize_extract_section_type_by_filename(sections, "PL_001.pdf")

        self.assertEqual(
            [section["master"]["SectionType"] for section in result],
            ["PACKINGLIST"],
        )

    def test_invoice_packing_prefix_keeps_two_types_and_normalizes_commercial_invoice(self):
        for file_name in ("IV_PL_001.pdf", "INV_PL_001.pdf", "IN_PL_001.pdf"):
            with self.subTest(file_name=file_name):
                sections = [
                    {"master": {"SectionType": "COMMERCIALINVOICE"}},
                    {"master": {"SectionType": "PACKINGLIST"}},
                    {"master": {"SectionType": "PO"}},
                ]

                result = _normalize_extract_section_type_by_filename(sections, file_name)

                self.assertEqual(
                    [section["master"]["SectionType"] for section in result],
                    ["INVOICE", "PACKINGLIST"],
                )

    def test_commercial_invoice_packing_prefix_keeps_two_types_and_normalizes_invoice(self):
        sections = [
            {"master": {"SectionType": "INVOICE"}},
            {"master": {"SectionType": "PACKINGLIST"}},
            {"master": {"SectionType": "CUSTOMSHEET"}},
        ]

        result = _normalize_extract_section_type_by_filename(sections, "Com_PL_001.pdf")

        self.assertEqual(
            [section["master"]["SectionType"] for section in result],
            ["COMMERCIALINVOICE", "PACKINGLIST"],
        )

    def test_inspec_prefix_keeps_inspection_section(self):
        sections = [
            {"master": {"SectionType": "INSPECTION"}},
            {"master": {"SectionType": "INVOICE"}},
        ]

        result = _normalize_extract_section_type_by_filename(
            sections,
            "Inspec_Biên bản nghiệm thu 1 năm.pdf",
        )

        self.assertEqual(
            [section["master"]["SectionType"] for section in result],
            ["INSPECTION"],
        )

class ExtractSystemPromptFilterTests(unittest.TestCase):
    SYSTEM_PROMPT = """COMMON-START
[[DOC:INVOICE]]- INVOICE[[/DOC]]
COMMON-MIDDLE-1
[[DOC:CUSTOMSHEET]]- CUSTOMSHEET[[/DOC]]
[[DOC:INVOICE]]
INVOICE-RULES
[[/DOC]]
COMMON-MIDDLE-2
[[DOC:PACKINGLIST]]
PACKINGLIST-RULES
[[/DOC]]
[[DOC:UNMAPPED]]
UNMAPPED-RULES
[[/DOC]]
COMMON-END"""

    def test_single_type_keeps_all_matching_blocks_and_common_text(self):
        filtered, metadata = _filter_extract_system_prompt_by_doc_types(
            self.SYSTEM_PROMPT,
            ("INVOICE",),
        )

        self.assertIn("- INVOICE", filtered)
        self.assertIn("INVOICE-RULES", filtered)
        self.assertNotIn("CUSTOMSHEET", filtered)
        self.assertNotIn("PACKINGLIST-RULES", filtered)
        self.assertNotIn("UNMAPPED-RULES", filtered)
        self.assertNotIn("[[DOC:", filtered)
        self.assertNotIn("[[/DOC]]", filtered)
        self.assertLess(filtered.index("COMMON-START"), filtered.index("COMMON-MIDDLE-1"))
        self.assertLess(filtered.index("COMMON-MIDDLE-1"), filtered.index("COMMON-MIDDLE-2"))
        self.assertLess(filtered.index("COMMON-MIDDLE-2"), filtered.index("COMMON-END"))
        self.assertEqual(metadata["total_doc_blocks"], 5)
        self.assertEqual(metadata["kept_doc_blocks"], 2)
        self.assertEqual(metadata["removed_doc_blocks"], 3)

    def test_combined_type_keeps_invoice_and_packinglist_blocks(self):
        filtered, metadata = _filter_extract_system_prompt_by_doc_types(
            self.SYSTEM_PROMPT,
            ("INVOICE", "PACKINGLIST"),
        )

        self.assertIn("- INVOICE", filtered)
        self.assertIn("INVOICE-RULES", filtered)
        self.assertIn("PACKINGLIST-RULES", filtered)
        self.assertNotIn("[[DOC:", filtered)
        self.assertNotIn("[[/DOC]]", filtered)
        self.assertNotIn("CUSTOMSHEET", filtered)
        self.assertEqual(metadata["kept_doc_blocks"], 3)

    def test_unmapped_type_keeps_only_unmapped_body_without_tags(self):
        filtered, metadata = _filter_extract_system_prompt_by_doc_types(
            self.SYSTEM_PROMPT,
            ("UNMAPPED",),
        )

        self.assertIn("COMMON-START", filtered)
        self.assertIn("UNMAPPED-RULES", filtered)
        self.assertIn("COMMON-END", filtered)
        self.assertNotIn("INVOICE-RULES", filtered)
        self.assertNotIn("PACKINGLIST-RULES", filtered)
        self.assertNotIn("[[DOC:", filtered)
        self.assertNotIn("[[/DOC]]", filtered)
        self.assertEqual(metadata["kept_doc_blocks"], 1)

    def test_prompt_without_doc_markers_is_returned_unchanged(self):
        prompt = "COMMON PROMPT WITHOUT TAGS"

        filtered, metadata = _filter_extract_system_prompt_by_doc_types(
            prompt,
            ("INVOICE",),
        )

        self.assertEqual(filtered, prompt)
        self.assertFalse(metadata["applied"])

    def test_missing_selected_doc_block_raises(self):
        with self.assertRaisesRegex(ValueError, "PACKINGLIST"):
            _filter_extract_system_prompt_by_doc_types(
                "[[DOC:INVOICE]]rules[[/DOC]]",
                ("INVOICE", "PACKINGLIST"),
            )

    def test_unbalanced_doc_markers_raise(self):
        with self.assertRaisesRegex(ValueError, "không hợp lệ"):
            _filter_extract_system_prompt_by_doc_types(
                "COMMON [[DOC:INVOICE]]rules",
                ("INVOICE",),
            )


class ExtractPromptFilterIntegrationTests(unittest.TestCase):
    SYSTEM_PROMPT = """COMMON-START
[[DOC:INVOICE]]INVOICE-ONE[[/DOC]]
[[DOC:CUSTOMSHEET]]CUSTOMSHEET-RULES[[/DOC]]
[[DOC:INVOICE]]INVOICE-TWO[[/DOC]]
[[DOC:UNMAPPED]]UNMAPPED-RULES[[/DOC]]
COMMON-END"""

    def _run_extract(
        self,
        *,
        system_prompt,
        file_name="IV_105.pdf",
        ocr_content="OCR-CONTENT",
        split_fn=None,
        prompt_snapshot_fn=None,
    ):
        captured_calls = []
        split_calls = []

        def default_split(text, **kwargs):
            split_calls.append((text, kwargs))
            return ["OCR-CHUNK-1", "OCR-CHUNK-2"]

        def generate_with_trim(**kwargs):
            captured_calls.append(kwargs)
            return '{"sections": []}'

        latest_user = f'''***
{{
 "Prompt_Type": "Trích xuất"
}}
***
        Tên File: {file_name} - Dữ liệu OCR: {ocr_content}'''

        with TemporaryDirectory() as temp_dir:
            result, status_code = process_ai_llms_models_rules(
                latest_system=system_prompt,
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                split_ocr_text_fn=split_fn or default_split,
                generate_with_trim_fn=generate_with_trim,
                append_prompt_client_snapshot_fn=prompt_snapshot_fn,
                append_response_log_fn=lambda result: None,
                light_cuda_cleanup_fn=lambda: None,
                logger=SilentLogger(),
            )

        return result, status_code, split_calls, captured_calls

    def test_customs_declaration_uses_three_pages_per_llm_chunk(self):
        result, status_code, split_calls, _ = self._run_extract(
            system_prompt=self.SYSTEM_PROMPT,
            file_name="CUS_105.xlsx",
            ocr_content="[Sheet] Customs\n<IMP>\nDECLARATION DATA",
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result, {"sections": []})
        self.assertEqual(len(split_calls), 1)
        self.assertEqual(split_calls[0][1]["max_pages"], 3)

    def test_processed_prompt_snapshot_runs_once_before_ocr_split(self):
        events = []
        snapshots = []

        def capture_snapshot(messages, extra):
            events.append("snapshot")
            snapshots.append((messages, extra))

        def split_after_snapshot(text, **kwargs):
            events.append("split")
            self.assertEqual(len(snapshots), 1)
            return [text]

        result, status_code, _, _ = self._run_extract(
            system_prompt=self.SYSTEM_PROMPT,
            split_fn=split_after_snapshot,
            prompt_snapshot_fn=capture_snapshot,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result, {"sections": []})
        self.assertEqual(events, ["snapshot", "split"])
        self.assertEqual(len(snapshots), 1)

        messages, extra = snapshots[0]
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("INVOICE-ONE", messages[0]["content"])
        self.assertIn("INVOICE-TWO", messages[0]["content"])
        self.assertNotIn("CUSTOMSHEET-RULES", messages[0]["content"])
        self.assertNotIn("[[DOC:", messages[0]["content"])
        self.assertNotIn("[[/DOC]]", messages[0]["content"])
        self.assertIn("Tên File: IV_105.pdf", messages[1]["content"])
        self.assertIn("Dữ liệu OCR: OCR-CONTENT", messages[1]["content"])
        self.assertNotIn('"Prompt_Type"', messages[1]["content"])
        self.assertEqual(extra["file_name"], "IV_105.pdf")
        self.assertEqual(extra["stage"], "after_doc_filter_before_ocr_split")
        self.assertEqual(extra["doc_filter"]["selected_doc_types"], ["INVOICE"])

    def test_filename_filter_is_applied_once_and_used_for_every_chunk(self):
        result, status_code, split_calls, captured_calls = self._run_extract(
            system_prompt=self.SYSTEM_PROMPT,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result, {"sections": []})
        self.assertEqual(len(split_calls), 1)
        self.assertEqual(len(captured_calls), 2)
        for call in captured_calls:
            messages = call["base_messages"]
            filtered_system = messages[0]["content"]
            self.assertIn("COMMON-START", filtered_system)
            self.assertIn("INVOICE-ONE", filtered_system)
            self.assertIn("INVOICE-TWO", filtered_system)
            self.assertIn("COMMON-END", filtered_system)
            self.assertNotIn("CUSTOMSHEET-RULES", filtered_system)
            self.assertNotIn("UNMAPPED-RULES", filtered_system)
            self.assertNotIn("[[DOC:", filtered_system)
            self.assertNotIn("[[/DOC]]", filtered_system)

    def test_unknown_filename_prefix_uses_unmapped_prompt_for_every_chunk(self):
        result, status_code, split_calls, captured_calls = self._run_extract(
            system_prompt=self.SYSTEM_PROMPT,
            file_name="ABC_105.pdf",
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result, {"sections": []})
        self.assertEqual(len(split_calls), 1)
        self.assertEqual(len(captured_calls), 2)
        for call in captured_calls:
            messages = call["base_messages"]
            filtered_system = messages[0]["content"]
            self.assertIn("COMMON-START", filtered_system)
            self.assertIn("UNMAPPED-RULES", filtered_system)
            self.assertIn("COMMON-END", filtered_system)
            self.assertNotIn("INVOICE-ONE", filtered_system)
            self.assertNotIn("CUSTOMSHEET-RULES", filtered_system)
            self.assertNotIn("[[DOC:", filtered_system)
            self.assertNotIn("[[/DOC]]", filtered_system)

    def test_missing_unmapped_block_returns_400_before_split_or_llm(self):
        split_called = []

        def fail_split(*args, **kwargs):
            split_called.append(True)
            raise AssertionError("Không được chia chunk khi thiếu DOC:UNMAPPED")

        result, status_code, _, captured_calls = self._run_extract(
            system_prompt="COMMON [[DOC:INVOICE]]rules[[/DOC]]",
            file_name="ABC_105.pdf",
            split_fn=fail_split,
        )

        self.assertEqual(status_code, 400)
        self.assertIn("UNMAPPED", result["detail"])
        self.assertEqual(split_called, [])
        self.assertEqual(captured_calls, [])

    def test_prompt_without_doc_markers_keeps_backward_compatible_flow(self):
        legacy_prompt = "LEGACY SYSTEM PROMPT"

        _, status_code, _, captured_calls = self._run_extract(
            system_prompt=legacy_prompt,
            file_name="ABC_105.pdf",
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(len(captured_calls), 2)
        self.assertTrue(all(call["base_messages"][0]["content"] == legacy_prompt for call in captured_calls))

    def test_ringi_extraction_requests_ollama_thinking_for_every_chunk(self):
        result, status_code, _, captured_calls = self._run_extract(
            system_prompt="LEGACY SYSTEM PROMPT",
            file_name="RING_105.pdf",
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result, {"sections": []})
        self.assertEqual(len(captured_calls), 2)
        self.assertTrue(all(call.get("think") is True for call in captured_calls))

    def test_non_ringi_extraction_does_not_request_thinking(self):
        result, status_code, _, captured_calls = self._run_extract(
            system_prompt=self.SYSTEM_PROMPT,
            file_name="IV_105.pdf",
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result, {"sections": []})
        self.assertEqual(len(captured_calls), 2)
        self.assertTrue(all("think" not in call for call in captured_calls))

    def test_invalid_doc_structure_returns_400_before_split_or_llm(self):
        invalid_prompts = (
            "COMMON [[DOC:INVOICE]]rules",
            "COMMON [[DOC:CUSTOMSHEET]]rules[[/DOC]]",
        )

        for invalid_prompt in invalid_prompts:
            with self.subTest(invalid_prompt=invalid_prompt):
                split_called = []

                def fail_split(*args, **kwargs):
                    split_called.append(True)
                    raise AssertionError("Không được chia chunk khi DOC blocks không hợp lệ")

                result, status_code, _, captured_messages = self._run_extract(
                    system_prompt=invalid_prompt,
                    split_fn=fail_split,
                )

                self.assertEqual(status_code, 400)
                self.assertIn("detail", result)
                self.assertEqual(split_called, [])
                self.assertEqual(captured_messages, [])


if __name__ == "__main__":
    unittest.main()
