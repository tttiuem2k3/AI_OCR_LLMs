# App/ocr_engine_iis.py
import os
import time
import asyncio
import logging
from pathlib import Path
from typing import List, Optional

# NOTE: do NOT import PPStructureV3 at module import time; it may trigger heavy deps.

from App.settings_all import get_settings_all
from .text_format import to_txt_pages, to_pretty_txt_pages
from .annotate import save_annot_images


# Logger
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
        # Import lazily to prevent app import from crashing if optional deps are missing.
        from paddleocr import PPStructureV3

        t_all = time.time()
        s = get_settings_all()

        # Persist settings for later use
        self._s = s
        self.settings = s

        # Strictly forbid CPU
        if str(getattr(s, "DEVICE", "gpu")).lower() != "gpu":
            raise RuntimeError("CPU is forbidden. Please set DEVICE=gpu.")

        # Prefer local-only model resolution to avoid downloads at startup
        os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "LOCAL")

        project_root = Path(getattr(s, "PROJECT_ROOT", Path(__file__).resolve().parents[2]))

        def _resolve_under_project(p: str) -> Path:
            pp = Path(p)
            if pp.is_absolute():
                return pp
            return (project_root / pp).resolve()

        det_dir = _resolve_under_project(s.DET_DIR)
        rec_dir = _resolve_under_project(s.REC_DIR)

        def _looks_like_infer_dir(p: Path) -> bool:
            """Heuristic check: treat folder as valid if it has parameters + metadata.

            In this project the model folders currently contain:
            - inference.pdiparams
            - inference.yml and/or inference.json
            Some exports also include *.pdmodel, but we must not require it.
            """
            if not p.exists() or not p.is_dir():
                return False

            def _has_expected_files(d: Path) -> bool:
                has_params = any(d.glob("*.pdiparams"))
                has_meta = any(d.glob("*.yml")) or any(d.glob("*.yaml")) or any(d.glob("*.json"))
                # Keep supporting classic export layouts too
                has_pdmodel = any(d.glob("*.pdmodel"))
                return (has_params and (has_meta or has_pdmodel))

            if _has_expected_files(p):
                return True
            for child in p.iterdir():
                if child.is_dir() and _has_expected_files(child):
                    return True
            return False

        if not _looks_like_infer_dir(det_dir):
            raise RuntimeError(
                f"OCR DET_DIR không hợp lệ hoặc chưa có model infer local: {det_dir}. "
                f"Cần có *.pdiparams và (inference.yml/inference.json hoặc *.pdmodel)."
            )
        if not _looks_like_infer_dir(rec_dir):
            raise RuntimeError(
                f"OCR REC_DIR không hợp lệ hoặc chưa có model infer local: {rec_dir}. "
                f"Cần có *.pdiparams và (inference.yml/inference.json hoặc *.pdmodel)."
            )

        # Output dirs
        self.outputs_root = _resolve_under_project(getattr(s, "OUTPUT_ROOT", "Outputs"))
        self.txt_dir = self.outputs_root / "txt"
        self.annot_dir = self.outputs_root / "annot_images"
        self.txt_dir.mkdir(parents=True, exist_ok=True)
        self.annot_dir.mkdir(parents=True, exist_ok=True)

        # Lock avoiding concurrent predict
        self._lock = asyncio.Lock()

        # Disable Qt HiDPI
        if getattr(s, "DISABLE_QT_HIDPI", False):
            os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
            os.environ.setdefault("QT_SCALE_FACTOR", "1")
            os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

        # Init pipeline
        t0 = time.time()
        try:
            self.pipeline = PPStructureV3(
                device="gpu",
                text_detection_model_dir=str(det_dir),
                text_detection_model_name="PP-OCRv5_server_det",
                text_recognition_model_dir=str(rec_dir),
                text_recognition_model_name="PP-OCRv5_server_rec",
                # text_recognition_batch_size=int(getattr(s, "TEXT_REC_BS", 4)),

                # ====================================================
                # CÁC MODULE BỔ SUNG
                # ====================================================
                use_doc_orientation_classify=True,
                use_textline_orientation=True,
                use_doc_unwarping=False,
                use_seal_recognition=False,
                use_table_recognition=True,
                use_formula_recognition=False,
                use_chart_recognition=False,
                use_region_detection=True,

                # layout_detection_model_name=None,

                # text_det_limit_side_len=1600,
                # text_det_limit_type="max",
                # text_det_thresh=0.45,
                # text_det_unclip_ratio=2.4,
                # text_det_box_thresh=0.65,
                # text_rec_score_thresh=0.2,

                # layout_threshold=0.5,
                # layout_nms=True,
                # layout_unclip_ratio=1.0,
                # layout_merge_bboxes_mode="large",

                # use_doc_orientation_classify=True,
                # use_textline_orientation=True,
                # use_doc_unwarping=False,
                # use_seal_recognition=False,
                # use_table_recognition=False,
                # use_formula_recognition=False,
                # use_chart_recognition=False,
                # use_region_detection=False,

                layout_detection_model_name=None,

                text_det_limit_side_len=2560,
                text_det_limit_type="max",
                text_det_thresh=0.35,
                text_det_unclip_ratio=1.8,
                text_det_box_thresh=0.45,
                text_rec_score_thresh=0.4,


                # text_det_limit_side_len=1280,
                # text_det_limit_type="max",
                # text_det_thresh=0.45,
                # text_det_unclip_ratio=2.0,
                # text_det_box_thresh=0.60,
                # text_rec_score_thresh=0.2,
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
        logger.info("OCREngine ready in total %.2fs", time.time() - t_all)

    async def ainfer(self, input_path: str, annot_stem: Optional[str] = None) -> List[str]:
        """
        Chạy predict async cho PDF hoặc Ảnh (jpg/png/tif/webp/…).
        PPStructureV3 hỗ trợ input là đường dẫn tệp (PDF hoặc ảnh đơn).
        """
        logger.info("Predict start -> %s", input_path)
        t0 = time.time()

        p = Path(input_path)
        if not p.exists():
            logger.error("Input file NOT FOUND: %s", input_path)
            raise FileNotFoundError(f"Input not found: {input_path}")
        try:
            logger.debug("Input size = %d bytes", p.stat().st_size)
        except Exception:
            logger.debug("Input size = (unknown)")

        # Gọi predict
        try:
            async with self._lock:
                results = self.pipeline.predict(input=input_path)
        except Exception as e:
            logger.error("Pipeline.predict FAILED: %r", e, exc_info=True)
            raise

        logger.info("Predict done in %.2fs", time.time() - t0)

        # Tên thư mục annotate
        stem = annot_stem or p.stem

        # Lưu ảnh annotate
        if bool(getattr(self._s, "SAVE_ANNOTATIONS", False)):
            try:
                saved_any = False
                fmt = getattr(self._s, "ANNOTATE_FORMAT", None) or "png"
                for idx, res in enumerate(results, start=1):
                    # Một số pipeline chỉ tạo img khi truy cập; có thể phát sinh tải font online.
                    imgs = getattr(res, "img", {}) or {}
                    if imgs:
                        save_annot_images(
                            imgs,
                            self.annot_dir,
                            idx,
                            fmt=fmt,
                            stem=stem,
                        )
                        saved_any = True
                if saved_any:
                    logger.info("Annotations saved under: %s", (self.annot_dir / stem).resolve())
                else:
                    logger.info("No annotations to save for: %s", stem)
            except Exception as e:
                logger.error("Saving annotations FAILED: %r", e, exc_info=True)

        # Chuyển kết quả sang text
        try:
            # pages_txt = to_txt_pages(results)
            pages_txt = to_pretty_txt_pages(results)
        except Exception as e:
            logger.error("Converting results to text FAILED: %r", e, exc_info=True)
            raise

        logger.info("Pages extracted: %d", len(pages_txt))
        return pages_txt

    def save_txt(self, pages_text: List[str], basename: str) -> Path:
        """
        Lưu các trang text vào Outputs/txt/<basename>.txt
        """
        t0 = time.time()
        out_txt = self.txt_dir / f"{basename}.txt"
        try:
            out_txt.parent.mkdir(parents=True, exist_ok=True)
            out_txt.write_text(_with_page_end_markers(pages_text), encoding="utf-8")
        except Exception as e:
            logger.error("Saving TXT FAILED (%s): %r", out_txt, e, exc_info=True)
            raise

        dur = time.time() - t0
        try:
            sz = out_txt.stat().st_size
            logger.info("Saved TXT -> %s (size=%d) in %.2fs", out_txt, sz, dur)
            logger.info("\n")
        except Exception:
            logger.info("Saved TXT -> %s in %.2fs", out_txt, dur)
            logger.info("\n")
        return out_txt 
    

#================================================================================================================================

