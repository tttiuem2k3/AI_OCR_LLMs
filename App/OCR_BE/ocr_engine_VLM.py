import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

from App.settings_all import get_settings_all
from .annotate import save_annot_images

logger = logging.getLogger("ocr_app.engine")
_NVIDIA_DLL_HANDLES: List[Any] = []


def _with_page_end_markers(pages_text: List[str]) -> str:
    chunks: List[str] = []
    for idx, page in enumerate(pages_text or [], start=1):
        body = (page or "").rstrip()
        marker = f"----{idx}----"
        chunks.append(f"{body}\n{marker}" if body else marker)
    return "\n\n".join(chunks)


def _mapping_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    getter = getattr(value, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    return None


def _result_to_page_text(result: Any) -> str:
    try:
        markdown = getattr(result, "markdown")
    except Exception:
        markdown = None
    markdown_text = _mapping_value(markdown, "markdown_texts")
    if markdown_text is not None:
        return str(markdown_text).strip()

    parsing_blocks = _mapping_value(result, "parsing_res_list") or []
    block_texts: List[str] = []
    for block in parsing_blocks:
        content = (
            _mapping_value(block, "block_content")
            or _mapping_value(block, "content")
            or _mapping_value(block, "text")
        )
        if content:
            block_texts.append(str(content).strip())
    return "\n\n".join(text for text in block_texts if text)


def _validate_local_model(model_name: str, model_dir: Path, required_files: List[str]) -> None:
    missing = [filename for filename in required_files if not (model_dir / filename).is_file()]
    if missing:
        raise RuntimeError(
            f"Dev must download the model {model_name} to {model_dir}. "
            f"Missing required files: {missing}"
        )


def _prepend_nvidia_dll_dirs(nvidia_root: Optional[Path] = None) -> None:
    if os.name != "nt":
        return
    root = nvidia_root or (Path(sys.prefix) / "Lib" / "site-packages" / "nvidia")
    if not root.is_dir():
        return

    dll_dirs = sorted(
        (package_dir / "bin").resolve()
        for package_dir in root.iterdir()
        if (package_dir / "bin").is_dir()
    )
    if not dll_dirs:
        return

    current_paths = [path for path in os.environ.get("PATH", "").split(os.pathsep) if path]
    dll_dir_strings = [str(path) for path in dll_dirs]
    remaining_paths = [path for path in current_paths if path not in dll_dir_strings]
    os.environ["PATH"] = os.pathsep.join(dll_dir_strings + remaining_paths)

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if callable(add_dll_directory):
        for dll_dir in dll_dirs:
            try:
                _NVIDIA_DLL_HANDLES.append(add_dll_directory(str(dll_dir)))
            except OSError:
                logger.warning("Cannot register NVIDIA DLL directory: %s", dll_dir)


class OCREngine:
    def __init__(self):
        started_at = time.time()
        settings = get_settings_all()
        self._s = settings
        project_root = Path(
            getattr(settings, "PROJECT_ROOT", Path(__file__).resolve().parents[2])
        ).resolve()

        def resolve_project_path(value: str) -> Path:
            path = Path(value)
            return path if path.is_absolute() else (project_root / path).resolve()

        device = str(getattr(settings, "DEVICE", "gpu")).lower()
        if not device.startswith("gpu"):
            raise RuntimeError("CPU is forbidden. Please set DEVICE=gpu or gpu:<id>.")
        if getattr(settings, "DISABLE_QT_HIDPI", False):
            os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
            os.environ.setdefault("QT_SCALE_FACTOR", "1")
            os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

        model_root = project_root / "Models"
        self.layout_model_dir = model_root / "PP-DocLayoutV3"
        self.vlm_model_dir = model_root / "PaddleOCR-VL-1.6"
        _validate_local_model(
            "PP-DocLayoutV3",
            self.layout_model_dir,
            ["inference.yml", "inference.pdiparams"],
        )
        _validate_local_model(
            "PaddleOCR-VL-1.6",
            self.vlm_model_dir,
            ["config.json", "model.safetensors"],
        )

        self.outputs_root = resolve_project_path(settings.OUTPUT_ROOT)
        self.txt_dir = self.outputs_root / "txt"
        self.annot_dir = self.outputs_root / "annot_images"
        self.txt_dir.mkdir(parents=True, exist_ok=True)
        self.annot_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

        _prepend_nvidia_dll_dirs()
        try:
            from paddleocr import PaddleOCRVL
        except (ImportError, ModuleNotFoundError) as exc:
            raise RuntimeError(
                "PaddleOCRVL requires paddleocr>=3.7.0 and a compatible paddlex installation"
            ) from exc

        init_started_at = time.time()
        try:
            self.pipeline = PaddleOCRVL(
                pipeline_version="v1.6",
                layout_detection_model_dir=str(self.layout_model_dir),
                vl_rec_model_dir=str(self.vlm_model_dir),
                vl_rec_backend="native",
                device=device,
                use_doc_orientation_classify=True,
                use_doc_unwarping=False,
                use_layout_detection=True,
                format_block_content=True,
                merge_layout_blocks=True,
            )
        except Exception as exc:
            logger.error("PaddleOCRVL init FAILED: %r", exc, exc_info=True)
            raise

        logger.info("[Engine] PaddleOCR-VL 1.6 init in %.2fs", time.time() - init_started_at)
        logger.info("[Engine] device=%s", device)
        logger.info("[Engine] layout_model_dir=%s", self.layout_model_dir)
        logger.info("[Engine] vlm_model_dir=%s", self.vlm_model_dir)
        logger.info("[Engine] output_root=%s", self.outputs_root)
        logger.info("OCREngine ready in total %.2fs", time.time() - started_at)

    async def ainfer(self, input_path: str, annot_stem: Optional[str] = None) -> List[str]:
        logger.info("Predict start -> %s", input_path)
        started_at = time.time()
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"Input not found: {input_path}")
        try:
            async with self._lock:
                results = list(self.pipeline.predict(input=input_path))
        except Exception as exc:
            logger.error("PaddleOCRVL.predict FAILED: %r", exc, exc_info=True)
            raise

        logger.info("Predict done in %.2fs", time.time() - started_at)
        if getattr(self._s, "SAVE_ANNOTATIONS", True):
            try:
                stem = annot_stem or path.stem
                for page_index, result in enumerate(results, start=1):
                    images = getattr(result, "img", {}) or {}
                    if images:
                        save_annot_images(
                            images,
                            self.annot_dir,
                            page_index,
                            fmt=self._s.ANNOTATE_FORMAT,
                            stem=stem,
                        )
            except Exception as exc:
                logger.error("Saving annotations FAILED: %r", exc, exc_info=True)

        pages_text = [_result_to_page_text(result) for result in results]
        logger.info("Pages extracted: %d", len(pages_text))
        return pages_text

    def save_txt(self, pages_text: List[str], basename: str) -> Path:
        started_at = time.time()
        out_txt = self.txt_dir / f"{basename}.txt"
        out_txt.parent.mkdir(parents=True, exist_ok=True)
        out_txt.write_text(_with_page_end_markers(pages_text), encoding="utf-8")
        logger.info(
            "Saved TXT -> %s (size=%d) in %.2fs",
            out_txt,
            out_txt.stat().st_size,
            time.time() - started_at,
        )
        return out_txt
