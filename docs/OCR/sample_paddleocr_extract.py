"""Chạy PPStructureV3 OCR cho một file và ghi văn bản nhận diện ra TXT."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Iterable


def configure_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trích xuất văn bản từ file bằng PPStructureV3 của PaddleOCR."
    )
    parser.add_argument("input", type=Path, help="Đường dẫn file ảnh hoặc PDF cần OCR.")
    parser.add_argument(
        "--output",
        type=Path,
        help="File TXT đầu ra. Mặc định: <input>_ocr.txt.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Thiết bị chạy inference, ví dụ: cpu, gpu, gpu:0. Mặc định: cpu.",
    )
    parser.add_argument(
        "--det-model-name",
        default="PP-OCRv6_medium_det",
        help="Tên model text detection. Mặc định: PP-OCRv6_medium_det.",
    )
    parser.add_argument(
        "--rec-model-name",
        default="PP-OCRv6_medium_rec",
        help="Tên model text recognition. Mặc định: PP-OCRv6_medium_rec.",
    )
    parser.add_argument(
        "--layout-model-name",
        default="PP-DocLayout_plus-L",
        help="Tên model layout detection. Mặc định: PP-DocLayout_plus-L.",
    )
    parser.add_argument("--det-model-dir", type=Path, help="Thư mục model detection local.")
    parser.add_argument("--rec-model-dir", type=Path, help="Thư mục model recognition local.")
    parser.add_argument("--layout-model-dir", type=Path, help="Thư mục model layout local.")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Chỉ dùng model local, không tải model từ nguồn online.",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Lưu ảnh trực quan hóa kết quả OCR nếu result hỗ trợ.",
    )
    return parser.parse_args()


def optional_model_dir(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path.expanduser().resolve())


def create_engine(args: argparse.Namespace) -> Any:
    if args.local_only:
        os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "LOCAL")

    from paddleocr import PPStructureV3

    options: dict[str, Any] = {
        "device": args.device,
        "text_detection_model_name": args.det_model_name,
        "text_recognition_model_name": args.rec_model_name,
        "layout_detection_model_name": args.layout_model_name,
        "use_doc_orientation_classify": False,
        "use_textline_orientation": False,
        "use_doc_unwarping": True,
        "use_seal_recognition": False,
        "use_table_recognition": True,
        "use_formula_recognition": False,
        "use_chart_recognition": False,
        "use_region_detection": True,
        "text_det_limit_side_len": 1280,
        "text_det_limit_type": "max",
        "text_det_thresh": 0.30,
        "text_det_unclip_ratio": 1.7,
        "text_det_box_thresh": 0.45,
        "text_rec_score_thresh": 0.25,
    }

    model_dirs = {
        "text_detection_model_dir": optional_model_dir(args.det_model_dir),
        "text_recognition_model_dir": optional_model_dir(args.rec_model_dir),
        "layout_detection_model_dir": optional_model_dir(args.layout_model_dir),
    }
    options.update({key: value for key, value in model_dirs.items() if value})

    return PPStructureV3(**options)


def get_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def extract_text_from_page(page: Any) -> str:
    overall_ocr_res = get_value(page, "overall_ocr_res")
    if not isinstance(overall_ocr_res, dict):
        return ""

    recognized_texts = (
        overall_ocr_res.get("rec_texts")
        or overall_ocr_res.get("texts")
        or overall_ocr_res.get("text")
        or []
    )
    lines = [str(text).strip() for text in recognized_texts if str(text).strip()]
    return "\n".join(lines)


def extract_text_pages(results: Iterable[Any]) -> list[str]:
    return [extract_text_from_page(result) for result in results]


def join_pages_with_markers(pages_text: list[str]) -> str:
    chunks: list[str] = []
    for page_index, page_text in enumerate(pages_text, start=1):
        body = page_text.rstrip()
        marker = f"----{page_index}----"
        chunks.append(f"{body}\n{marker}" if body else marker)
    return "\n\n".join(chunks)


def save_details(results: Iterable[Any], detail_dir: Path, visualize: bool) -> None:
    detail_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        save_to_json = getattr(result, "save_to_json", None)
        if callable(save_to_json):
            save_to_json(str(detail_dir))

        if visualize:
            save_to_img = getattr(result, "save_to_img", None)
            if callable(save_to_img):
                save_to_img(str(detail_dir))


def main() -> int:
    configure_utf8_console()
    args = parse_args()
    input_path = args.input.expanduser().resolve()

    if not input_path.is_file():
        print(f"Không tìm thấy file đầu vào: {input_path}", file=sys.stderr)
        return 2

    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else input_path.with_name(f"{input_path.stem}_ocr.txt")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    detail_dir = output_path.parent / f"{output_path.stem}_details"

    print("Đang khởi tạo PPStructureV3...")
    pipeline = create_engine(args)

    print(f"Đang OCR file: {input_path}")
    results = list(pipeline.predict(input=str(input_path)))
    pages_text = extract_text_pages(results)

    output_path.write_text(join_pages_with_markers(pages_text), encoding="utf-8")
    save_details(results, detail_dir, args.visualize)

    total_lines = sum(1 for page in pages_text for line in page.splitlines() if line.strip())
    print(f"Đã xử lý {len(pages_text)} trang, {total_lines} dòng văn bản.")
    print(f"Văn bản: {output_path}")
    print(f"Chi tiết JSON: {detail_dir}")
    if args.visualize:
        print(f"Ảnh kết quả: {detail_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
