# App/ocr_engine_iis_v1.py
import os
import time
import asyncio
import logging
from pathlib import Path
from typing import List, Optional

# NOTE: do NOT import PPStructureV3 at module import time; it may trigger heavy deps.

from App.settings_all import get_settings_all
from .text_format import to_txt_pages, to_pretty_txt_pages
# vẫn import được, nhưng sẽ không dùng khi save_annotations=False
from .annotate import save_annot_images


logger = logging.getLogger("ocr_app.engine")


def _with_page_end_markers(pages_text: List[str]) -> str:
    chunks: List[str] = []
    for idx, page in enumerate(pages_text or [], start=1):
        body = (page or "").rstrip()
        marker = f"----{idx}----"
        if body:
            chunks.append(f"{body}\n{marker}")
        else:
            chunks.append(marker)
    return "\n\n".join(chunks)

class OCREngine:
    def __init__(self):
        from paddleocr import PPStructureV3

        t_all = time.time()
        s = get_settings_all()
        self._s = s

        project_root = Path(getattr(s, "PROJECT_ROOT", Path(__file__).resolve().parents[2]))

        def _resolve_under_project(p: str) -> Path:
            pp = Path(p)
            if pp.is_absolute():
                return pp
            return (project_root / pp).resolve()

        det_dir = _resolve_under_project(s.DET_DIR)
        rec_dir = _resolve_under_project(s.REC_DIR)

        # Strictly forbid CPU
        if str(getattr(s, "DEVICE", "gpu")).lower() != "gpu":
            raise RuntimeError("CPU is forbidden. Please set DEVICE=gpu.")

        # Tắt HiDPI Qt (tránh phát sinh xử lý hình ảnh không cần thiết)
        if getattr(s, "DISABLE_QT_HIDPI", False):
            os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
            os.environ.setdefault("QT_SCALE_FACTOR", "1")
            os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

        # Ưu tiên model local
        os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "LOCAL")

        # Thư mục đầu ra
        self.outputs_root = _resolve_under_project(s.OUTPUT_ROOT)
        self.txt_dir = self.outputs_root / "txt"
        self.annot_dir = self.outputs_root / "annot_images"
        self.txt_dir.mkdir(parents=True, exist_ok=True)
        # Không cần tạo annot_dir khi đã tắt, nhưng cứ tạo để an toàn nếu bật lại
        self.annot_dir.mkdir(parents=True, exist_ok=True)

        # Khoá tránh race khi predict
        self._lock = asyncio.Lock()

        # Khởi tạo pipeline
        t0 = time.time()
        try:
            self.pipeline = PPStructureV3(
                device="gpu",
                text_detection_model_dir=str(det_dir),
                text_detection_model_name="PP-OCRv5_server_det",
                text_recognition_model_dir=str(rec_dir),
                text_recognition_model_name="PP-OCRv5_server_rec",
                text_recognition_batch_size=int(getattr(s, "TEXT_REC_BS", 4)),

                use_doc_orientation_classify=True,
                use_textline_orientation=True,
                use_doc_unwarping=False,
                use_seal_recognition=False,
                use_table_recognition=False,
                use_formula_recognition=False,
                use_chart_recognition=False,
                use_region_detection=False,

                layout_detection_model_name=None,
            )
        except Exception as e:
            logger.error("PPStructureV3 init FAILED: %r", e, exc_info=True)
            raise

        init_secs = time.time() - t0
        logger.info("[Engine] Pipeline init in %.2fs", init_secs)
        logger.info("[Engine] device=%s", "gpu")
        logger.info("[Engine] det_dir=%s", str(det_dir))
        logger.info("[Engine] rec_dir=%s", str(rec_dir))
        logger.info("[Engine] output_root=%s", str(self.outputs_root.resolve()))
        logger.info("[Engine] save_annotations=%s", getattr(s, "SAVE_ANNOTATIONS", True))
        logger.info("text_recognition_batch_size=%s", int(getattr(s, "TEXT_REC_BS", 4)))
        logger.info("OCREngine ready in total %.2fs", time.time() - t_all)

    async def ainfer(self, input_path: str, annot_stem: Optional[str] = None) -> List[str]:
        """
        Chạy predict async cho PDF hoặc Ảnh (jpg/png/tif/webp/…).
        """
        logger.info("Predict start -> %s", input_path)
        t0 = time.time()

        p = Path(input_path)
        if not p.exists():
            logger.error("Input file NOT FOUND: %s", input_path)
            raise FileNotFoundError(f"Input not found: {input_path}")

        # Gọi predict
        try:
            async with self._lock:
                results = self.pipeline.predict(input=input_path)
        except Exception as e:
            logger.error("Pipeline.predict FAILED: %r", e, exc_info=True)
            raise

        logger.info("Predict done in %.2fs", time.time() - t0)

        # ❌ TẮT lưu ảnh annotate để tăng tốc
        s = self._s
        if getattr(s, "SAVE_ANNOTATIONS", True):
            try:
                saved_any = False
                stem = annot_stem or p.stem
                for idx, res in enumerate(results, start=1):
                    imgs = getattr(res, "img", {}) or {}
                    if imgs:
                        save_annot_images(
                            imgs,
                            self.annot_dir,
                            idx,
                            fmt=s.ANNOTATE_FORMAT,
                            stem=stem
                        )
                        saved_any = True
                if saved_any:
                    logger.info("Annotations saved under: %s", (self.annot_dir / stem).resolve())
                else:
                    logger.info("No annotations to save for: %s", stem)
            except Exception as e:
                logger.error("Saving annotations FAILED: %r", e, exc_info=True)
        else:
            logger.debug("save_annotations=False -> skip saving annotate images")

        # Chuyển kết quả sang text (bản pretty giữ layout tương đối)
        try:
            pages_txt = to_pretty_txt_pages(results)
        except Exception as e:
            logger.error("Converting results to text FAILED: %r", e, exc_info=True)
            raise

        logger.info("Pages extracted: %d", len(pages_txt))
        return pages_txt

    def save_txt(self, pages_text: List[str], basename: str) -> Path:
        """Lưu các trang text vào Outputs/txt/<basename>.txt"""
        t0 = time.time()
        out_txt = self.txt_dir / f"{basename}.txt"
        out_txt.parent.mkdir(parents=True, exist_ok=True)
        out_txt.write_text(_with_page_end_markers(pages_text), encoding="utf-8")

        dur = time.time() - t0
        try:
            sz = out_txt.stat().st_size
            logger.info("Saved TXT -> %s (size=%d) in %.2fs", out_txt, sz, dur)
            logger.info("\n")
        except Exception:
            logger.info("Saved TXT -> %s in %.2fs", out_txt, dur)
            logger.info("\n")
        return out_txt
