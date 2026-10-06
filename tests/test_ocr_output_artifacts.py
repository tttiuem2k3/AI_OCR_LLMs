import tempfile
import unittest
from pathlib import Path

from App.OCR_BE.output_artifacts import build_unique_artifact_stem, iter_file


class OCROutputArtifactTests(unittest.TestCase):
    def test_same_original_filename_uses_separate_output_files_and_responses(self):
        request_ids = [
            "11111111111111111111111111111111",
            "22222222222222222222222222222222",
            "33333333333333333333333333333333",
        ]
        expected_contents = ["OCR-A", "OCR-B", "OCR-C"]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            output_paths = []

            for request_id, content in zip(request_ids, expected_contents):
                artifact_stem = build_unique_artifact_stem("VAT_273", request_id)
                output_path = output_dir / f"{artifact_stem}.txt"
                output_path.write_text(content, encoding="utf-8")
                output_paths.append(output_path)

            self.assertEqual(len(set(output_paths)), 3)
            self.assertEqual(
                [b"".join(iter_file(path)).decode("utf-8") for path in output_paths],
                expected_contents,
            )

    def test_artifact_stem_rejects_empty_request_id(self):
        with self.assertRaises(ValueError):
            build_unique_artifact_stem("VAT_273", "")


if __name__ == "__main__":
    unittest.main()
