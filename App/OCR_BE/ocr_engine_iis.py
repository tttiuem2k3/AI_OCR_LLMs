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
from .orientation import prepare_oriented_inputs, verify_prepared_orientations
from .orientation_verifier import (
    OrientationVerifierConfig,
    TextLineOrientationVerifier,
)


# Logger
logger = logging.getLogger("ocr_app.engine")


def resolve_shared_text_detector(pipeline):
    return getattr(
        getattr(
            getattr(pipeline, "paddlex_pipeline", None),
            "general_ocr_pipeline",
            None,
        ),
        "text_det_model",
        None,
    )


def build_orientation_verifier_config(settings) -> OrientationVerifierConfig:
    return OrientationVerifierConfig(
        det_side_len=int(
            getattr(settings, "OCR_ORIENTATION_VERIFY_DET_SIDE_LEN", 640)
        ),
        min_lines=int(getattr(settings, "OCR_ORIENTATION_VERIFY_MIN_LINES", 3)),
        upright_vote=float(
            getattr(settings, "OCR_ORIENTATION_VERIFY_UPRIGHT_VOTE", 0.20)
        ),
        horizontal_ratio=float(
            getattr(settings, "OCR_ORIENTATION_VERIFY_HORIZONTAL_RATIO", 0.60)
        ),
        line_aspect=float(
            getattr(settings, "OCR_ORIENTATION_VERIFY_LINE_ASPECT", 1.20)
        ),
        batch_size=int(
            getattr(settings, "OCR_ORIENTATION_VERIFY_BATCH_SIZE", 8)
        ),
    )


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
        t_all = time.time()
        s = get_settings_all()
        device = s.ocr_device

        # CPU flags phải được set trước khi import PaddleOCR/PaddleX.
        # Điều này giúp tránh việc oneDNN được khởi tạo trước khi cấu hình CPU có hiệu lực.
        if device == "cpu":
            cpu_threads = max(1, int(getattr(s, "OCR_CPU_THREADS", 32)))
            os.environ["OMP_NUM_THREADS"] = str(cpu_threads)
            os.environ["MKL_NUM_THREADS"] = str(cpu_threads)
            if bool(getattr(s, "OCR_CPU_DISABLE_MKLDNN", True)):
                os.environ["FLAGS_use_mkldnn"] = "0"

        # Import lazily to prevent app import from crashing if optional deps are missing.
        from paddleocr import PPStructureV3

        # Persist settings for later use
        self._s = s
        self.settings = s

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
        layout_dir = _resolve_under_project(s.LAYOUT_DIR)

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
        if not _looks_like_infer_dir(layout_dir):
            raise RuntimeError(
                f"OCR LAYOUT_DIR không hợp lệ hoặc chưa có model infer local: {layout_dir}. "
                f"Cần có *.pdiparams và (inference.yml/inference.json hoặc *.pdmodel)."
            )

        self.orientation_model = None
        self.orientation_min_score = float(
            getattr(s, "OCR_FAST_ORIENTATION_MIN_SCORE", 0.90)
        )
        self.orientation_min_margin = float(
            getattr(s, "OCR_FAST_ORIENTATION_MIN_MARGIN", 0.20)
        )
        self.orientation_four_way_enabled = bool(
            getattr(s, "OCR_FOUR_WAY_ORIENTATION_ENABLED", True)
        )
        self.orientation_upright_min_score = float(
            getattr(s, "OCR_ORIENTATION_UPRIGHT_MIN_SCORE", 0.60)
        )
        self.orientation_best_margin = float(
            getattr(s, "OCR_ORIENTATION_BEST_MARGIN", 0.20)
        )
        self.orientation_original_gain = float(
            getattr(s, "OCR_ORIENTATION_ORIGINAL_GAIN", 0.20)
        )
        self.orientation_batch_size = int(
            getattr(s, "OCR_ORIENTATION_BATCH_SIZE", 4)
        )
        self.orientation_verify_enabled = bool(
            getattr(s, "OCR_ORIENTATION_VERIFY_ENABLED", True)
        )
        self.orientation_verifier = None
        self.orientation_verifier_config = build_orientation_verifier_config(s)
        if bool(getattr(s, "OCR_FAST_ORIENTATION_ENABLED", True)):
            from paddlex import create_model

            orientation_model_name = str(
                getattr(s, "OCR_DOC_ORIENTATION_MODEL_NAME", "PP-LCNet_x1_0_doc_ori")
            ).strip()
            paddlex_home = _resolve_under_project(getattr(s, "PADDLEX_HOME", "Cache"))
            orientation_model_dir = (
                paddlex_home / ".paddlex" / "official_models" / orientation_model_name
            )
            if not _looks_like_infer_dir(orientation_model_dir):
                raise RuntimeError(
                    f"OCR orientation model is missing or invalid: {orientation_model_dir}"
                )
            orientation_start = time.time()
            self.orientation_model = create_model(
                orientation_model_name,
                model_dir=str(orientation_model_dir),
                device=device,
            )
            logger.info(
                "[Engine] fast orientation model=%s four_way=%s score>=%.3f "
                "margin>=%.3f gain>=%.3f batch=%d init=%.2fs",
                orientation_model_name,
                self.orientation_four_way_enabled,
                self.orientation_upright_min_score,
                self.orientation_best_margin,
                self.orientation_original_gain,
                self.orientation_batch_size,
                time.time() - orientation_start,
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
        # CPU dùng cùng package/runtime với GPU nhưng tắt oneDNN/MKLDNN nếu được cấu hình,
        # tránh nhánh oneDNN/PIR đã gây lỗi ConvertPirAttribute2RuntimeAttribute.
        pipeline_runtime_kwargs = {}
        if device == "cpu":
            # PaddleOCR/PaddleX có khác biệt nhỏ giữa các version, nên chỉ truyền
            # tham số CPU nếu constructor hiện tại hỗ trợ (hoặc nhận **kwargs).
            import inspect

            pp_signature = inspect.signature(PPStructureV3)
            pp_parameters = pp_signature.parameters
            accepts_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in pp_parameters.values()
            )
            enable_mkldnn = not bool(getattr(s, "OCR_CPU_DISABLE_MKLDNN", True))
            cpu_threads = max(1, int(getattr(s, "OCR_CPU_THREADS", 32)))

            if accepts_kwargs or "enable_mkldnn" in pp_parameters:
                pipeline_runtime_kwargs["enable_mkldnn"] = enable_mkldnn
            else:
                logger.warning(
                    "[Engine] PPStructureV3 version hiện tại không expose enable_mkldnn; "
                    "sẽ dùng FLAGS_use_mkldnn=%s làm fallback.",
                    os.environ.get("FLAGS_use_mkldnn", "<unset>"),
                )

            if accepts_kwargs or "cpu_threads" in pp_parameters:
                pipeline_runtime_kwargs["cpu_threads"] = cpu_threads
            else:
                logger.warning(
                    "[Engine] PPStructureV3 version hiện tại không expose cpu_threads; "
                    "sẽ dùng OMP_NUM_THREADS/MKL_NUM_THREADS=%d.",
                    cpu_threads,
                )

            logger.info(
                "[Engine] CPU runtime: enable_mkldnn=%s cpu_threads=%d runtime_kwargs=%s",
                enable_mkldnn,
                cpu_threads,
                sorted(pipeline_runtime_kwargs.keys()),
            )

        t0 = time.time()
        try:
            self.pipeline = PPStructureV3(
                device=device,
                text_detection_model_dir=str(det_dir),
                text_detection_model_name=s.DET_MODEL_NAME,
                text_recognition_model_dir=str(rec_dir),
                text_recognition_model_name=s.REC_MODEL_NAME,
                layout_detection_model_dir=str(layout_dir),
                layout_detection_model_name=s.LAYOUT_MODEL_NAME,
                text_recognition_batch_size=int(getattr(s, "TEXT_REC_BS", 4)),

                # ====================================================
                # CÁC MODULE BỔ SUNG
                # ====================================================
                use_doc_orientation_classify=False,
                use_textline_orientation=False,
                use_doc_unwarping=True,
                use_seal_recognition=False,
                use_table_recognition=True,
                use_formula_recognition=False,
                use_chart_recognition=False,
                use_region_detection=True,

                #layout_detection_model_name=None,
                text_det_limit_side_len=1280,
                text_det_limit_type="max",
                text_det_thresh=0.30,
                text_det_unclip_ratio=1.7,
                text_det_box_thresh=0.45,
                text_rec_score_thresh=0.25,
                **pipeline_runtime_kwargs,
            )
        except Exception as e:
            logger.error("PPStructureV3 init FAILED: %r", e, exc_info=True)
            raise

        if (
            self.orientation_verify_enabled
            and self.orientation_four_way_enabled
            and self.orientation_model is not None
        ):
            try:
                detector = resolve_shared_text_detector(self.pipeline)
                if detector is None:
                    raise RuntimeError(
                        "shared PPStructure text detector is unavailable"
                    )
                from paddlex import create_model

                textline_model_name = str(
                    getattr(
                        s,
                        "OCR_TEXTLINE_ORIENTATION_MODEL_NAME",
                        "PP-LCNet_x1_0_textline_ori",
                    )
                ).strip()
                paddlex_home = _resolve_under_project(getattr(s, "PADDLEX_HOME", "Cache"))
                textline_model_dir = (
                    paddlex_home / ".paddlex" / "official_models" / textline_model_name
                )
                if not _looks_like_infer_dir(textline_model_dir):
                    raise RuntimeError(
                        f"OCR text-line orientation model is missing or invalid: "
                        f"{textline_model_dir}"
                    )
                verify_start = time.time()
                textline_model = create_model(
                    textline_model_name,
                    model_dir=str(textline_model_dir),
                    device=device,
                )
                self.orientation_verifier = TextLineOrientationVerifier(
                    detector,
                    textline_model,
                    self.orientation_verifier_config,
                )
                logger.info(
                    "[Engine] orientation verifier model=%s det_side=%d min_lines=%d "
                    "vote>=%.3f horizontal>=%.3f aspect>=%.3f batch=%d init=%.2fs",
                    textline_model_name,
                    self.orientation_verifier_config.det_side_len,
                    self.orientation_verifier_config.min_lines,
                    self.orientation_verifier_config.upright_vote,
                    self.orientation_verifier_config.horizontal_ratio,
                    self.orientation_verifier_config.line_aspect,
                    self.orientation_verifier_config.batch_size,
                    time.time() - verify_start,
                )
            except Exception as verifier_error:
                logger.warning(
                    "Orientation verifier unavailable; non-zero candidates will be kept "
                    "unrotated: %r",
                    verifier_error,
                    exc_info=True,
                )

        init_secs = time.time() - t0
        logger.info("[Engine] Pipeline init in %.2fs", init_secs)
        logger.info("[Engine] device=%s", device)
        logger.info("[Engine] det_model=%s", s.DET_MODEL_NAME)
        logger.info("[Engine] det_dir=%s", str(det_dir))
        logger.info("[Engine] rec_model=%s", s.REC_MODEL_NAME)
        logger.info("[Engine] rec_dir=%s", str(rec_dir))
        logger.info("[Engine] layout_model=%s", s.LAYOUT_MODEL_NAME)
        logger.info("[Engine] layout_dir=%s", str(layout_dir))
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
                predict_input = input_path
                if self.orientation_model is not None:
                    try:
                        prepared_images, orientation_decisions = prepare_oriented_inputs(
                            self.orientation_model,
                            input_path,
                            min_score=self.orientation_min_score,
                            min_margin=(
                                self.orientation_best_margin
                                if self.orientation_four_way_enabled
                                else self.orientation_min_margin
                            ),
                            four_way_enabled=self.orientation_four_way_enabled,
                            upright_min_score=self.orientation_upright_min_score,
                            original_gain=self.orientation_original_gain,
                            orientation_batch_size=self.orientation_batch_size,
                        )
                        verification_traces = [None] * len(orientation_decisions)
                        if (
                            self.orientation_verify_enabled
                            and self.orientation_four_way_enabled
                        ):
                            if self.orientation_verifier is not None:
                                verifier = self.orientation_verifier.verify
                            else:
                                def verifier(source_image, angle):
                                    raise RuntimeError(
                                        "orientation verifier is unavailable"
                                    )

                            (
                                prepared_images,
                                orientation_decisions,
                                verification_traces,
                            ) = verify_prepared_orientations(
                                prepared_images,
                                orientation_decisions,
                                verifier,
                            )
                        predict_input = prepared_images
                        for page_index, (decision, verification_trace) in enumerate(
                            zip(orientation_decisions, verification_traces),
                            start=1,
                        ):
                            if verification_trace is not None:
                                for attempt_name, verification_result in (
                                    ("selected", verification_trace.selected),
                                    ("opposite", verification_trace.opposite),
                                ):
                                    if verification_result is None:
                                        continue
                                    logger.info(
                                        "Orientation verify page=%d attempt=%s angle=%d "
                                        "boxes=%d crops=%d horizontal=%.4f vote=%.4f "
                                        "passed=%s reason=%s",
                                        page_index,
                                        attempt_name,
                                        verification_result.angle,
                                        verification_result.detected_box_count,
                                        verification_result.retained_crop_count,
                                        verification_result.horizontal_ratio,
                                        verification_result.upright_vote,
                                        verification_result.passed,
                                        verification_result.reason,
                                    )
                                if verification_trace.error is not None:
                                    logger.warning(
                                        "Orientation verify page=%d failed closed: %r",
                                        page_index,
                                        verification_trace.error,
                                    )
                            if decision.upright_scores:
                                upright_scores = dict(decision.upright_scores)
                                logger.info(
                                    "Orientation page=%d mode=%s upright_scores="
                                    "0:%.4f,90:%.4f,180:%.4f,270:%.4f selected=%d "
                                    "score=%.4f margin=%.4f gain=%.4f applied=%d",
                                    page_index,
                                    decision.decision_source,
                                    upright_scores.get(0, 0.0),
                                    upright_scores.get(90, 0.0),
                                    upright_scores.get(180, 0.0),
                                    upright_scores.get(270, 0.0),
                                    decision.predicted_angle,
                                    decision.top_score,
                                    decision.margin,
                                    decision.original_gain,
                                    decision.applied_angle,
                                )
                            else:
                                logger.info(
                                    "Orientation page=%d mode=%s predicted=%d score=%.4f "
                                    "runner_up=%.4f margin=%.4f applied=%d",
                                    page_index,
                                    decision.decision_source,
                                    decision.predicted_angle,
                                    decision.top_score,
                                    decision.runner_up_score,
                                    decision.margin,
                                    decision.applied_angle,
                                )
                    except Exception as orientation_error:
                        logger.warning(
                            "Fast orientation preprocessing failed; using original input: %r",
                            orientation_error,
                            exc_info=True,
                        )
                results = list(self.pipeline.predict(input=predict_input))
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
    
