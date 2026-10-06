# App/main_iis.py
import os, re, uuid, time, shutil, asyncio
import threading
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import List, Optional
from flask import Flask, request, jsonify, Response, send_from_directory
from werkzeug.exceptions import HTTPException

# =============================================================================
# A) ĐƯỜNG DẪN & BIẾN MÔI TRƯỜNG
# =============================================================================
from .settings_all import get_settings_all

settings_all = get_settings_all()

# Lấy đường dẫn gốc Project từ settings_all (không hard-code tuyệt đối ở file code)
PROJECT_ROOT = settings_all.PROJECT_ROOT

LOG_DIR = str(Path(PROJECT_ROOT) / "Logs")
LOG_FILE = str(Path(LOG_DIR) / "app.log")

CACHE_ROOT = str(Path(PROJECT_ROOT) / "Cache")
TEMP_DIR = str(Path(CACHE_ROOT) / "temp")

Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
Path(CACHE_ROOT).mkdir(parents=True, exist_ok=True)
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)

# Allow overriding PaddleX cache root (must be writable)
try:
    _paddlex_home_cfg = (getattr(settings_all, "PADDLEX_HOME", "Cache") or "Cache").strip()
    _paddlex_home = str((Path(PROJECT_ROOT) / _paddlex_home_cfg).resolve()) if not Path(_paddlex_home_cfg).is_absolute() else str(Path(_paddlex_home_cfg).resolve())
except Exception:
    _paddlex_home = CACHE_ROOT

os.environ["PADDLEX_HOME"] = _paddlex_home
os.environ["PADDLE_HOME"] = CACHE_ROOT
os.environ["XDG_CACHE_HOME"] = CACHE_ROOT
os.environ["TMP"] = TEMP_DIR
os.environ["TEMP"] = TEMP_DIR
os.environ["HOME"] = CACHE_ROOT
os.environ["USERPROFILE"] = CACHE_ROOT

# Force-disable torch.compile/inductor for runtime stability on server workloads.
os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["TORCH_DISABLE_TORCHINDUCTOR"] = "1"
os.environ["TORCHINDUCTOR_DISABLE"] = "1"
# Reduce CUDA allocator fragmentation after OOM in long-running process.
# NOTE: `expandable_segments` is not supported on Windows builds.
if os.name == "nt":
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128,garbage_collection_threshold:0.8")
else:
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

try:
    # DLL dirs: đọc từ settings_all.WINDOWS_DLL_DIRS (có thể để trống)
    dlls = [p.strip() for p in (settings_all.WINDOWS_DLL_DIRS or "").split(";") if p.strip()]
    if dlls:
        if hasattr(os, "add_dll_directory"):
            for d in dlls:
                p = Path(d)
                if p.exists():
                    os.add_dll_directory(str(p))
        else:
            os.environ["PATH"] = ";".join([*dlls, os.environ.get("PATH", "")])
except Exception:
    pass

# --- CUDA enforcement (MUST be set early) ---
from .LLMs_BE.llms_integration import enforce_cuda_selected_gpu, llms_paths

settings_all = get_settings_all()

# Backward-compat: if REQUIRE_CUDA_GPU0=True, force GPU_INDEX=0
gpu_index = 0 if getattr(settings_all, "REQUIRE_CUDA_GPU0", False) else int(getattr(settings_all, "GPU_INDEX", 0))
require_cuda = bool(getattr(settings_all, "REQUIRE_CUDA", True) or getattr(settings_all, "REQUIRE_CUDA_GPU0", False))

enforce_cuda_selected_gpu(gpu_index=gpu_index, require_cuda=require_cuda)

# Ensure HF caches/models use Project/Models by default (can be overridden via env)
try:
    _models_root = str(Path(PROJECT_ROOT) / "Models")
    os.environ.setdefault("HF_HOME", _models_root)
    # Prefer new cache vars; TRANSFORMERS_CACHE is deprecated in recent Transformers.
    os.environ.setdefault("HF_HUB_CACHE", str(Path(_models_root) / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.environ["HF_HUB_CACHE"])  # backward compat
except Exception:
    pass

# =============================================================================
# B) LOGGING 
# =============================================================================
import logging
from logging.handlers import RotatingFileHandler
from flask import request

class RequestIPFilter(logging.Filter):
    def filter(self, record):
        try:
            record.client_ip = request.remote_addr
        except RuntimeError:
            record.client_ip = "N/A"
        return True

logger = logging.getLogger("IIS_SERVER_OCR")
logger.setLevel(logging.INFO)


if logger.handlers:
    logger.handlers.clear()


fmt = logging.Formatter(
    "%(asctime)s | IP=%(client_ip)s | %(message)s"
)


fh = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10*1024*1024,
    backupCount=5,
    encoding="utf-8"
)
fh.setFormatter(fmt)
fh.addFilter(RequestIPFilter())
fh.setLevel(logging.INFO)
logger.addHandler(fh)

# Route LLM engine diagnostics to the same file once. Keeping propagation off
# prevents Uvicorn/root handlers from printing the same LoRA event again.
llms_logger = logging.getLogger("LLMs_BE")
llms_logger.setLevel(logging.INFO)
llms_logger.handlers.clear()
llms_logger.addHandler(fh)
llms_logger.propagate = False

logger.info("=== IIS SERVER OCR START ===")


# =============================================================================
# C) APP & CẤU HÌNH
# =============================================================================
# NOTE: settings/config đã gom về App/settings_all.py
settings = get_settings_all()

from .OCR_BE.office_text import OFFICE_TEXT_EXTENSIONS, extract_office_text
from .OCR_BE.output_artifacts import build_unique_artifact_stem, iter_file
from .OCR_BE.process_OCR import split_ocr_text
from .Rules_AI_BEM_MEIKO import clear_holiday_setting_cache, process_ai_llms_models_rules

# Thiết bị OCR được điều khiển tập trung bởi settings_all.DEVICE ("cpu" hoặc "gpu").
# LLM/CUDA vẫn dùng cấu hình GPU riêng, không phụ thuộc công tắc này.
_ocr_device = settings.ocr_device
logger.info("OCR runtime device=%s", _ocr_device)

# CPU OCR: cấu hình backend trước khi Paddle/PaddleX khởi tạo model.
# LLM qua Ollama vẫn dùng GPU độc lập và không phụ thuộc các biến này.
if _ocr_device == "cpu":
    _ocr_cpu_threads = max(1, int(getattr(settings, "OCR_CPU_THREADS", 32)))
    os.environ["OMP_NUM_THREADS"] = str(_ocr_cpu_threads)
    os.environ["MKL_NUM_THREADS"] = str(_ocr_cpu_threads)
    if bool(getattr(settings, "OCR_CPU_DISABLE_MKLDNN", True)):
        os.environ["FLAGS_use_mkldnn"] = "0"
    logger.info(
        "OCR CPU runtime configured: threads=%d disable_mkldnn=%s",
        _ocr_cpu_threads,
        bool(getattr(settings, "OCR_CPU_DISABLE_MKLDNN", True)),
    )

OUTPUT_ROOT = str(Path(settings.OUTPUT_ROOT).resolve())
NORMALIZE_TXT_PATH = (Path(PROJECT_ROOT) / "Outputs" / "normalize.txt").resolve()
SECTIONS_TXT_PATH = (Path(PROJECT_ROOT) / "Outputs" / "sections.txt").resolve()
DATA_HOLIDAYS_DIR = (Path(PROJECT_ROOT) / "App" / "Data_Holidays").resolve()
DATA_HOLIDAYS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=None)

# ==============================
# HOME (index chung + giữ nguyên 2 trang index riêng)
# ==============================
@app.route("/", methods=["GET"])
def home():
    # Trang index chung (Project/UI/index_all.html). Fallback về index_root.html nếu chưa có.
    ui_dir = str(Path(PROJECT_ROOT) / "UI")
    if (Path(ui_dir) / "index_all.html").exists():
        return send_from_directory(ui_dir, "index_all.html")
    return send_from_directory(ui_dir, "index_root.html")

@app.route("/ocr/", methods=["GET"])
def ocr_home():
    # OCR UI (moved into Project/UI)
    return send_from_directory(str(Path(PROJECT_ROOT) / "UI"), "index_ocr.html")

@app.route("/llms/", methods=["GET"])
def llms_home():
    # LLMs UI (moved into Project/UI)
    return send_from_directory(str(Path(PROJECT_ROOT) / "UI"), "index_llms.html")

@app.route("/static/<path:filename>")
def static_compat(filename):
    return send_from_directory(str(Path(PROJECT_ROOT) / "UI" / "static"), filename)

@app.route("/favicon.ico")
def favicon():
    ico = Path(PROJECT_ROOT) / "UI" / "static" / "favicon.ico"
    if (ico.exists()):
        return send_from_directory(str(ico.parent), ico.name)
    # If no favicon is bundled, return 204 instead of polluting logs with 404
    return ("", 204)

@app.before_request
def _before():
    request._t0 = time.time()
    rid = uuid.uuid4().hex[:8]
    request._rid = rid
    logger.info("[RID=%s] %s %s from %s, files=%d",
                rid, request.method, request.path, request.remote_addr,
                0 if not request.files else len(request.files))

@app.after_request
def _after(resp):
    dur = (time.time() - getattr(request, "_t0", time.time())) * 1000.0
    rid = getattr(request, "_rid", "-")
    logger.info("[RID=%s] Done %s %s -> %s in %.1f ms",
                rid, request.method, request.path, resp.status, dur)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return resp

@app.errorhandler(HTTPException)
def _on_http_error(e: HTTPException):
    """Return proper HTTP status codes for 404/405/... instead of turning them into 500."""
    rid = getattr(request, "_rid", "-")
    logger.warning("[RID=%s] HTTP error: %s %s -> %s", rid, request.method, request.path, e.code)
    return jsonify(error=e.description), e.code

@app.errorhandler(Exception)
def _on_error(e):
    rid = getattr(request, "_rid", "-")
    logger.error("[RID=%s] Unhandled error: %s", rid, repr(e), exc_info=True)
    return jsonify(error=str(e)), 500

# =============================================================================
# D) HỖ TRỢ & TIỆN ÍCH
# =============================================================================
PDF_EXTS    = {".pdf"}
IMAGE_EXTS  = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
OFFICE_EXTS = set(OFFICE_TEXT_EXTENSIONS)
HTM_EXTS    = {".htm", ".html"}
ALLOWED_EXTS = PDF_EXTS | IMAGE_EXTS | OFFICE_EXTS | HTM_EXTS

def sanitize_stem(name: str) -> str:
    # bỏ ký tự nguy hiểm Windows
    name = re.sub(r'[<>:"/\\|?*]+', "", name.strip())
    # thay whitespace -> _
    name = re.sub(r'\s+', '_', name)
    # nén nhiều _ liên tiếp
    name = re.sub(r'_+', '_', name)
    # bỏ . hoặc _ ở đầu/cuối
    name = name.strip('._')
    return name[:150] or uuid.uuid4().hex

def build_content_disposition(filename: str) -> str:
    try:
        ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "output.txt"
    except Exception:
        ascii_name = "output.txt"
    if not ascii_name.lower().endswith(".txt"):
        ascii_name += ".txt"
    utf8_name = quote(filename, safe="")
    return f"attachment; filename={ascii_name}; filename*=UTF-8''{utf8_name}"

def safe_unlink(p: Path, retries: int = 10, delay: float = 0.1):
    for _ in range(retries):
        try:
            p.unlink(missing_ok=True); return
        except PermissionError:
            time.sleep(delay)

# =============================================================================
# E) EAGER INIT OCREngine
# =============================================================================
_use_vlm_ocr = bool(getattr(settings, "USE_VLM_OCR", False))
if _use_vlm_ocr:
    from .OCR_BE.ocr_engine_VLM import OCREngine
    _ocr_engine_key = "paddleocr_vl"
    _ocr_engine_label = "PaddleOCR-VL"
else:
    from .OCR_BE.ocr_engine_iis import OCREngine
    _ocr_engine_key = "ppstructure_v3"
    _ocr_engine_label = "PPStructureV3"
from .OCR_BE.pdf_errors import pdf_data_format_error_pages
_engine = None
_use_ollama_llm = bool(getattr(settings_all, "LLM_USE_OLLAMA", False))
_autoload_llm_at_startup = (not _use_ollama_llm) and str(
    getattr(settings_all, "LLM_AUTOLOAD_SPECIAL", os.getenv("LLM_AUTOLOAD_SPECIAL", "false"))
).strip().lower() == "true"
if _autoload_llm_at_startup:
    logger.info(
        "OCREngine eager init skipped because LLM_AUTOLOAD_SPECIAL=true; "
        "OCR will lazy-load on the first /ocr request."
    )
else:
    try:
        t0 = time.time()
        logger.info("OCREngine eager init begin...")
        _engine = OCREngine()
        logger.info("OCREngine eager init done in %.2fs", time.time() - t0)
    except Exception as e:
        logger.error("OCREngine eager init FAILED: %s", repr(e), exc_info=True)

# =============================================================================
# E2) EAGER INIT LLMs (Transformers) + optional load SPECIAL_MODEL_ID
# =============================================================================
_llm_engine = None
_llm_registry = None
_llm_ready = False
_llm_oom_count = 0
_llm_oom_lock = threading.Lock()
_llms_train_lock = threading.Lock()
_resource_mode_lock = threading.Lock()
_llms_log_file_lock = threading.Lock()
# Local runtime mode:
# - mixed: OCR and LLMs may coexist
# - llm_only: OCR must stay unloaded to prioritize LLM inference/training
_resource_mode = "llm_only" if _autoload_llm_at_startup else "mixed"

try:
    # Thêm Project/App vào sys.path để import App.LLMs_BE.* an toàn trong mọi ngữ cảnh chạy.
    import sys

    app_root = str((Path(PROJECT_ROOT) / "App").resolve())
    if (app_root not in sys.path):
        sys.path.insert(0, app_root)

    # Khởi tạo engine/registry từ code dự án LLMs
    from .LLMs_BE.llms_integration import (
        get_llms_engine_and_registry,
        load_special_model,
        should_unload_ocr_before_ai_inference,
    )

    t0 = time.time()
    _llm_engine, _llm_registry = get_llms_engine_and_registry(settings_all, PROJECT_ROOT)

    # Load SPECIAL_MODEL_ID only when explicitly enabled
    _autoload = (not _use_ollama_llm) and str(
        getattr(settings_all, "LLM_AUTOLOAD_SPECIAL", os.getenv("LLM_AUTOLOAD_SPECIAL", "false"))
    ).lower() == "true"
    special_id = load_special_model(_llm_engine, _llm_registry, settings_all) if _autoload else None

    _llm_ready = True

    logger.info(
        "LLMs init done in %.2fs (autoload=%s, SPECIAL_MODEL_ID=%s)",
        time.time() - t0,
        _autoload,
        special_id,
    )
except Exception as e:
    _llm_ready = False
    logger.error("LLMs init FAILED: %s", repr(e), exc_info=True)

# =============================================================================
# F) ENDPOINTS (OCR)
# =============================================================================
@app.route("/ping", methods=["GET"])
def ping():
    status = "ready" if _engine is not None else "not-ready"
    return Response(f"OK ({status})", mimetype="text/plain; charset=utf-8")

@app.route("/ocr/status", methods=["GET"])
def ocr_status():
    ready = _engine is not None
    return jsonify(
        status="ready" if ready else "not-ready",
        ready=ready,
        engine=_ocr_engine_key,
        engine_label=_ocr_engine_label,
        use_vlm_ocr=_use_vlm_ocr,
    )

@app.route("/ocr", methods=["POST"])
def ocr_upload():
    if _llms_train_lock.locked():
        return jsonify(detail="LLMs training is running; OCR is temporarily unavailable"), 409

    try:
        _ensure_ocr_ready_for_request()
    except Exception as e:
        logger.error("OCR ensure/load failed: %s", repr(e), exc_info=True)
        return jsonify(detail=f"Engine not initialized: {e}"), 500

    uploads: List = []
    f1 = request.files.get("file")
    if f1: uploads.append(f1)
    uploads.extend(request.files.getlist("files"))

    if not uploads:
        logger.warning("No file uploaded")
        return jsonify(detail="Không có file được gửi lên."), 400

    txt_dir = Path(settings.OUTPUT_ROOT) / "txt"
    txt_dir.mkdir(parents=True, exist_ok=True)

    # --- 1 file ---
    if len(uploads) == 1:
        up = uploads[0]
        fname = up.filename or "input"
        ext = Path(fname).suffix.lower()
        logger.info("OCR single file: %s (ext=%s)", fname, ext)
        if ext not in ALLOWED_EXTS:
            logger.warning("Unsupported ext: %s", ext)
            return jsonify(detail=f"Chỉ hỗ trợ: {', '.join(sorted(ALLOWED_EXTS))}"), 400

        stem = sanitize_stem(Path(fname).stem)
        artifact_stem = build_unique_artifact_stem(stem, uuid.uuid4().hex)
        # Always re-run OCR and keep each request's output isolated, even when
        # multiple uploads have the same original filename.

        tmp = Path(TEMP_DIR) / f"{uuid.uuid4().hex}{ext}"
        try:
            with tmp.open("wb") as f:
                shutil.copyfileobj(up.stream, f)

            t1 = time.time()
            if ext in OFFICE_EXTS | HTM_EXTS:
                logger.info("Extract office/html text begin: %s", tmp)
                try:
                    pages = extract_office_text(tmp)
                except ValueError as ve:
                    logger.warning("Office parse 415: %s", ve)
                    return jsonify(detail=str(ve)), 415
                logger.info("Extract office/html text done in %.2fs", time.time() - t1)
            else:
                logger.info("OCR infer begin: %s", tmp)
                try:
                    pages = asyncio.run(_engine.ainfer(str(tmp), annot_stem=artifact_stem))
                except Exception as error:
                    pages = pdf_data_format_error_pages(error) if ext in PDF_EXTS else None
                    if pages is None:
                        raise
                    logger.warning("Invalid PDF data format: %s; returning OCR error text", fname)
                logger.info("OCR infer done in %.2fs", time.time() - t1)

            txt_path = _engine.save_txt(pages, artifact_stem)
            logger.info("Saved TXT: %s (size=%d)", txt_path, Path(txt_path).stat().st_size)
        finally:
            safe_unlink(tmp)

        cd = build_content_disposition(f"{stem}.txt")
        return Response(iter_file(Path(txt_path)),
                        headers={"Content-Disposition": cd},
                        mimetype="text/plain; charset=utf-8")

    
    now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    batch_name = f"batch_{now}.txt"
    out_path = Path(settings.OUTPUT_ROOT) / "txt" / batch_name
    result_lines = [f"Đã thực hiện OCR {len(uploads)} file @ {now}", ""]
    logger.info("OCR batch begin: %d files", len(uploads))

    for idx, up in enumerate(uploads, start=1):
        fname = up.filename or f"file_{idx}"
        ext = Path(fname).suffix.lower()
        logger.info("Batch item %d/%d: %s (ext=%s)", idx, len(uploads), fname, ext)

        result_lines.append(f"Nội dung: {'='*14} FILE {idx}/{len(uploads)} — {fname} {'='*14}")
        result_lines.append("")

        if ext not in ALLOWED_EXTS:
            logger.warning("Skip unsupported ext: %s", ext)
            result_lines.append(f"⚠️ Bỏ qua — Không hỗ trợ định dạng {ext}")
            result_lines.append("")
            continue

        stem = sanitize_stem(Path(fname).stem)
        # Always re-run OCR to reflect updated content, even if a file with the
        # same name was processed before. The new output will overwrite the old.

        tmp = Path(TEMP_DIR) / f"{uuid.uuid4().hex}{ext}"
        try:
            with tmp.open("wb") as f:
                shutil.copyfileobj(up.stream, f)
            if ext in OFFICE_EXTS | HTM_EXTS:
                try:
                    t2 = time.time()
                    pages = extract_office_text(tmp)
                    logger.info("Office/HTML parse %.2fs for %s", time.time() - t2, fname)
                except ValueError as ve:
                    logger.warning("Batch item %s 415: %s", fname, ve)
                    result_lines.append(f"⚠️ Bỏ qua (415): {ve}")
                    result_lines.append("")
                    continue
            else:
                t2 = time.time()
                try:
                    pages = asyncio.run(_engine.ainfer(str(tmp), annot_stem=stem))
                except Exception as error:
                    pages = pdf_data_format_error_pages(error) if ext in PDF_EXTS else None
                    if pages is None:
                        raise
                    logger.warning("Invalid PDF data format: %s; adding OCR error text", fname)
                logger.info("Infer %.2fs for %s", time.time() - t2, fname)

            for pi, page in enumerate(pages, start=1):
                page_text = (page or "").rstrip()
                if page_text:
                    result_lines.append(page_text)
                result_lines.append(f"----{pi}----")
                result_lines.append("")

        finally:
            safe_unlink(tmp)

    Path(out_path).write_text("\n".join(result_lines), encoding="utf-8")
    logger.info("Batch saved: %s (size=%d)", out_path, Path(out_path).stat().st_size)

    cd = build_content_disposition(out_path.name)
    return Response(iter_file(out_path),
                    headers={"Content-Disposition": cd},
                    mimetype="text/plain; charset=utf-8")

from pathlib import Path
from flask import send_from_directory, abort, request, jsonify, url_for

@app.route("/Outputs/<path:filename>", methods=["GET"])
def serve_outputs(filename):
    root = Path(OUTPUT_ROOT).resolve()
    full = (root / filename).resolve()
    
    try:
        full.relative_to(root)
    except Exception:
        logger.warning("Blocked path traversal: %s", full)
        abort(404)
    if not full.exists():
        logger.warning("Static not found: %s", full)
        abort(404)
    return send_from_directory(OUTPUT_ROOT, filename)

@app.route("/annot-list", methods=["GET"])
def annot_list():
    stem = request.args.get("stem", type=str)
    if not stem:
        return jsonify([])
    clean = sanitize_stem(stem)
    folder = Path(OUTPUT_ROOT) / "annot_images" / clean
    if not folder.exists():
        return jsonify([])
    files = sorted([*folder.glob("*.png"), *folder.glob("*.jpg"), *folder.glob("*.jpeg")], key=lambda p: p.name)
    return jsonify([
        url_for("serve_outputs", filename=f"annot_images/{clean}/{p.name}", _external=True)
        for p in files 
    ])

# ==============================
# LLMs: Serve UI + APIs dưới prefix /llms
# ==============================

# Serve static JS/CSS của LLMs (đã gom vào Project/UI/static)
@app.route("/llms/static/<path:filename>")
def llms_static(filename):
    return send_from_directory(str(Path(PROJECT_ROOT) / "UI" / "static"), filename)

# NOTE: route /llms/ đã được khai báo ở phần HOME phía trên (llms_home)
# nên KHÔNG khai báo thêm llms_index ở đây để tránh trùng route.

@app.route("/llms/api/health", methods=["GET"])
def llms_health():
    active_name = None
    if _llm_engine is not None and getattr(_llm_engine, "cfg", None) and isinstance(_llm_engine.cfg, dict):
        active_name = _llm_engine.cfg.get("name")

    return jsonify(
        status="ok" if _llm_ready else "not-ready",
        active_model_id=None if _llm_engine is None else getattr(_llm_engine, "active_id", None),
        active_model_name=active_name,
        pid=os.getpid(),
        runtime=None if _llm_engine is None else _llm_engine.runtime_info(),
        vram=_cuda_mem_snapshot(),
        hf_home=settings_all.LLM_HF_HOME,
        ts=time.time(),
    )


def _llms_require_token(flask_request):
    """Validate LLM API token.

    Accepts token via:
    - Query param: ?<LLM_API_TOKEN_QUERY_KEY>=...
    - Header: Authorization: Bearer <token>
    - Header: X-API-Token: <token>
    - Header: X-Api-Token: <token>
    """

    expected = (settings_all.LLM_API_TOKEN or "").strip()
    if not expected or expected == "CHANGE_ME":
        return False, (jsonify(detail="Server chưa cấu hình LLM_API_TOKEN"), 401)

    key = (settings_all.LLM_API_TOKEN_QUERY_KEY or "Token").strip() or "Token"
    got = (flask_request.args.get(key) or "").strip()

    if not got:
        auth = (flask_request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()

    if not got:
        got = (flask_request.headers.get("X-API-Token") or "").strip()

    if not got:
        # Some clients use different casing
        got = (flask_request.headers.get("X-Api-Token") or "").strip()

    # Normalize common UI encoding mistakes: token may be wrapped in quotes
    # Example from logs: Token=%22abc%22 -> got='"abc"'
    if got.startswith('"') and got.endswith('"') and len(got) >= 2:
        got = got[1:-1].strip()

    if got != expected:
        return False, (jsonify(detail="Invalid token"), 401)

    return True, None


def _llms_load_model_best_effort(model_id: str, cfg: dict):
    """Load model with preference for local snapshot folder when available."""
    if _llm_engine is None or _llm_registry is None:
        raise RuntimeError("LLMs engine not initialized")

    if _use_ollama_llm or bool(getattr(_llm_engine, "is_ollama", False)):
        return

    # Unload old model if different
    if getattr(_llm_engine, "active_id", None) and getattr(_llm_engine, "active_id", None) != model_id:
        _llm_engine.unload()

    local_path = ""
    try:
        local_path = str(_llm_registry.resolve_local_path(model_id) or "")
    except Exception:
        local_path = ""

    _llm_engine.load(model_id, cfg, local_path=local_path or None)

@app.route("/llms/connect", methods=["GET"])
@app.route("/llms/api/connect", methods=["GET"])
def llms_connect():
    ok, err = _llms_require_token(request)
    if not ok:
        return err

    models = []
    if (_llm_registry is not None):
        models = _llm_registry.list_models(only_local=False)

    active_name = None
    if _llm_engine is not None and getattr(_llm_engine, "cfg", None) and isinstance(_llm_engine.cfg, dict):
        active_name = _llm_engine.cfg.get("name")

    return jsonify(
        status="ok",
        models=models,
        active_model_id=None if _llm_engine is None else getattr(_llm_engine, "active_id", None),
        active_model_name=active_name,
    )


@app.route("/llms/api/models", methods=["GET"])
def llms_list_models():
    if _llm_registry is None:
        return jsonify([])
    return jsonify(_llm_registry.list_models(only_local=False))


@app.route("/llms/api/models/reload", methods=["POST"])
def llms_reload_models():
    if _llm_registry is None:
        return jsonify(status="ok", count=0)
    _llm_registry.reload()
    return jsonify(status="ok", count=len(_llm_registry.list_models()))


@app.route("/llms/api/models/load", methods=["POST"])
def llms_load_model():
    ok, err = _llms_require_token(request)
    if not ok:
        return err
    if _llm_engine is None or _llm_registry is None:
        return jsonify(detail="LLMs engine not initialized"), 500

    if _use_ollama_llm:
        model_id = getattr(_llm_engine, "active_id", None) or settings_all.OLLAMA_MODEL
        return jsonify(
            status="ok",
            provider="ollama",
            active_model_id=model_id,
            active_model_name=model_id,
        )

    j = request.get_json(silent=True) or {}
    model_id = (j.get("model_id") or "").strip()
    if not model_id:
        return jsonify(detail="model_id is required"), 400
    if not _llm_registry.has(model_id):
        return jsonify(detail="Unknown model_id"), 400

    cfg = _llm_registry.get(model_id)

    # unload model cũ nếu khác
    if getattr(_llm_engine, "active_id", None) and getattr(_llm_engine, "active_id", None) != model_id:
        _llm_engine.unload()

    # ưu tiên local nếu có
    # By default we use <LLM_LOCAL_MODELS_DIR>/<local_id>.
    # For model variants that share the same HF repo, set a stable local_id, e.g.:
    #   local_id: gpt_oss_20b
    # so the on-disk folder name is decoupled from the model id.
    local_path = ""
    try:
        local_path = str(_llm_registry.resolve_local_path(model_id) or "")
    except Exception:
        local_path = ""

    try:
        _llm_engine.load(model_id, cfg, local_path=local_path or None)
        return jsonify(active_model_id=model_id, active_model_name=cfg.get("name") or model_id)
    except Exception as e:
        return jsonify(detail=f"Load failed: {e}"), 400


@app.route("/llms/api/models/unload", methods=["POST"])
def llms_unload_model():
    ok, err = _llms_require_token(request)
    if not ok:
        return err
    if _llm_engine is None:
        return jsonify(status="ok", active_model_id=None, active_model_name=None)
    if _use_ollama_llm:
        model_id = getattr(_llm_engine, "active_id", None) or settings_all.OLLAMA_MODEL
        return jsonify(
            status="ok",
            provider="ollama",
            active_model_id=model_id,
            active_model_name=model_id,
        )
    _llm_engine.unload()
    return jsonify(status="ok", active_model_id=None, active_model_name=None)


def _sse(data: dict) -> str:
    import json as _json

    return f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"


def _llms_light_cuda_cleanup() -> None:
    """Cleanup temporary CUDA caches without unloading the active model."""
    try:
        import gc

        gc.collect()
    except Exception:
        pass

    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
    except Exception:
        pass


def _cuda_mem_snapshot() -> dict:
    """Best-effort snapshot for CUDA memory diagnostics."""
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return {"cuda": False}

        dev = torch.device("cuda:0")
        free_bytes, total_bytes = torch.cuda.mem_get_info(dev)
        allocated = torch.cuda.memory_allocated(dev)
        reserved = torch.cuda.memory_reserved(dev)
        return {
            "cuda": True,
            "device": str(dev),
            "free_mb": round(float(free_bytes) / (1024 * 1024), 2),
            "total_mb": round(float(total_bytes) / (1024 * 1024), 2),
            "allocated_mb": round(float(allocated) / (1024 * 1024), 2),
            "reserved_mb": round(float(reserved) / (1024 * 1024), 2),
        }
    except Exception as e:
        return {"cuda": "unknown", "error": repr(e)}


def _llms_hard_vram_cleanup(rounds: int = 3) -> None:
    """Best-effort deep VRAM cleanup for training handoff.

    This runs multiple cleanup rounds after models are unloaded to reduce
    lingering CUDA allocations from caches and delayed frees.
    """
    try:
        import gc

        gc.collect()
    except Exception:
        pass

    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return

        for _ in range(max(1, int(rounds))):
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
            try:
                gc.collect()
            except Exception:
                pass
    except Exception:
        pass


def _ocr_hard_unload() -> None:
    """Best-effort OCR engine unload to release GPU memory before training."""
    global _engine, _resource_mode

    vram_before = _cuda_mem_snapshot()
    try:
        if _engine is not None:
            try:
                if hasattr(_engine, "pipeline"):
                    delattr(_engine, "pipeline")
            except Exception:
                pass
    finally:
        _engine = None
        _resource_mode = "llm_only"

    try:
        import gc

        gc.collect()
    except Exception:
        pass

    # Chỉ đụng Paddle CUDA khi OCR thực sự chạy GPU.
    # Ở CPU mode, package paddlepaddle-gpu vẫn có thể báo compiled_with_cuda=True,
    # nhưng OCR không được synchronize/empty-cache GPU của Ollama.
    if _ocr_device == "gpu":
        try:
            import paddle  # type: ignore

            if paddle.is_compiled_with_cuda():
                try:
                    paddle.device.synchronize()
                except Exception:
                    pass
                try:
                    paddle.device.cuda.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass

    _llms_hard_vram_cleanup(rounds=2)
    logger.info(
        "OCR hard unload VRAM: before=%s after=%s",
        vram_before,
        _cuda_mem_snapshot(),
    )


def _switch_to_llm_only(reason: str = "") -> None:
    """Ensure OCR is unloaded to prioritize LLM-only workloads."""
    global _resource_mode
    with _resource_mode_lock:
        if _engine is not None:
            logger.info("Switch resource mode -> llm_only (reason=%s): unloading OCR", reason or "-")
            _ocr_hard_unload()
        _resource_mode = "llm_only"


def _ensure_ocr_ready_for_request() -> None:
    """Ensure OCR engine is loaded before handling OCR request (lazy reload)."""
    global _engine, _resource_mode
    with _resource_mode_lock:
        if _engine is None:
            t0 = time.time()
            _engine = OCREngine()
            logger.info("OCR lazy reload done in %.2fs", time.time() - t0)
        _resource_mode = "mixed"

    # GPU cleanup chỉ dành cho OCR GPU. CPU OCR không được tạo/đụng CUDA context,
    # để Ollama có thể sử dụng GPU độc lập.
    if _ocr_device == "gpu":
        try:
            import paddle  # type: ignore

            try:
                if paddle.is_compiled_with_cuda():
                    try:
                        paddle.device.synchronize()
                    except Exception:
                        pass
                    paddle.device.cuda.empty_cache()
            except Exception:
                pass
        except Exception:
            pass

        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                try:
                    torch.cuda.ipc_collect()
                except Exception:
                    pass
        except Exception:
            pass


def _llms_optional_pressure_unload() -> None:
    """Optional emergency unload when VRAM usage ratio is above threshold.

    Disabled by default. Enable with LLM_UNLOAD_ON_VRAM_PRESSURE=true.
    """
    enabled = str(os.getenv("LLM_UNLOAD_ON_VRAM_PRESSURE", "false")).strip().lower() in {
        "1", "true", "yes", "y", "on"
    }
    if not enabled or _llm_engine is None:
        return

    threshold = float(os.getenv("LLM_VRAM_PRESSURE_THRESHOLD", "0.95"))
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return
        dev = torch.device("cuda:0")
        total = float(torch.cuda.get_device_properties(dev).total_memory)
        reserved = float(torch.cuda.memory_reserved(dev))
        if total > 0 and (reserved / total) >= threshold:
            _llm_engine.unload()
            logger.warning(
                "LLM emergency unload due to VRAM pressure (reserved=%.2f%%, threshold=%.2f%%).",
                (reserved / total) * 100.0,
                threshold * 100.0,
            )
    except Exception as _e:
        logger.warning("Failed VRAM pressure check/unload: %s", repr(_e))


def _is_cuda_oom_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    markers = [
        "cuda oom",
        "out of memory",
        "cuda out of memory",
        "cublas_status_alloc_failed",
        "cuda error: out of memory",
        "hip out of memory",
    ]
    return any(m in msg for m in markers)


def _is_context_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    markers = [
        "context limit",
        "max_model_len",
        "input_tokens=",
        "prompt is at/over context limit",
        "exceeds max context",
    ]
    return any(m in msg for m in markers)


def _llms_generate_with_oom_retry(
    *,
    model_id: str,
    cfg: dict,
    messages: list,
    max_new_tokens: int,
    temperature: float,
) -> str:
    """Generate once; if CUDA OOM happens, cleanup and retry exactly 1 time."""
    if _llm_engine is None:
        raise RuntimeError("LLMs engine not initialized")

    retry_on_oom = str(os.getenv("LLM_RETRY_ON_OOM", "true")).strip().lower() in {
        "1", "true", "yes", "y", "on"
    }
    unload_on_oom = str(os.getenv("LLM_UNLOAD_ON_OOM", "true")).strip().lower() in {
        "1", "true", "yes", "y", "on"
    }
    cleanup_every = max(1, int(os.getenv("LLM_OOM_CLEANUP_EVERY", "1")))

    last_exc: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            return _llm_engine.generate_chat(messages, max_new_tokens=max_new_tokens, temperature=temperature)
        except Exception as e:
            last_exc = e
            if (attempt == 2) or (not retry_on_oom) or (not _is_cuda_oom_error(e)):
                raise

            global _llm_oom_count
            with _llm_oom_lock:
                _llm_oom_count += 1
                oom_count = _llm_oom_count

            should_cleanup_now = (oom_count % cleanup_every == 0)
            logger.error(
                "LLM CUDA OOM: model_id=%s attempt=%d oom_count=%d cleanup_now=%s error=%s",
                model_id,
                attempt,
                oom_count,
                should_cleanup_now,
                str(e),
            )

            # Only cleanup/retry at configured cadence (default every 5 OOMs).
            if not should_cleanup_now:
                raise RuntimeError(
                    f"CUDA OOM (count={oom_count}). Skip cleanup until every {cleanup_every} OOMs."
                ) from e

            logger.warning("Running OOM cleanup and retry once (count=%d).", oom_count)
            _llms_light_cuda_cleanup()
            if unload_on_oom:
                try:
                    _llm_engine.unload()
                except Exception as _e:
                    logger.warning("Failed unload on OOM: %s", repr(_e))

            # Ensure model is loaded again before retry.
            _llms_load_model_best_effort(model_id, cfg)

    # Defensive: loop always returns or raises.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Generate failed with unknown error")


def _llms_trim_messages_to_max_tokens(messages: list, max_tokens: int):
    """Trim chat messages aggressively so prompt tokens fit `max_tokens`.

    Strategy (best effort):
    - Keep message order unchanged whenever possible.
    - Only trim/drop non-system messages (never touch role=system content).
    - First trim overflow from the tail text of latest non-system messages.
    - If still too long, drop oldest non-system messages.
    - Final fallback trims latest user message with a hard character cap.
    """
    if _llm_engine is None:
        return messages, None, False

    try:
        limit = max(1, int(max_tokens))
    except Exception:
        limit = 1

    # Shallow copy each message dict so we don't mutate request payload directly.
    work: list = []
    for m in (messages or []):
        if isinstance(m, dict):
            work.append(dict(m))
        else:
            work.append(m)

    def _count(msgs):
        try:
            return _llm_engine.count_prompt_tokens(msgs)
        except Exception:
            return None

    current_tokens = _count(work)
    if current_tokens is None or current_tokens <= limit:
        return work, current_tokens, False

    changed = False

    # 1) Trim content tail from latest to oldest NON-SYSTEM message.
    for i in range(len(work) - 1, -1, -1):
        tokens_now = _count(work)
        if tokens_now is not None and tokens_now <= limit:
            return work, tokens_now, changed

        msg = work[i]
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role", "")).lower() == "system":
            continue

        content = msg.get("content")
        if content is None:
            continue
        content = str(content)
        if not content:
            continue

        msg["content"] = ""
        changed = True
        tok_empty = _count(work)
        if tok_empty is None:
            continue
        if tok_empty > limit:
            continue

        lo, hi = 0, len(content)
        best_len = 0
        best_tokens = tok_empty
        while lo <= hi:
            mid = (lo + hi) // 2
            msg["content"] = content[:mid]
            t = _count(work)
            if t is not None and t <= limit:
                best_len = mid
                best_tokens = t
                lo = mid + 1
            else:
                hi = mid - 1

        msg["content"] = content[:best_len]
        return work, best_tokens, changed

    # 2) Drop lower-priority NON-SYSTEM messages if role/token overhead is still too large.
    # Never drop system messages.
    while len(work) > 1:
        tokens_now = _count(work)
        if tokens_now is None or tokens_now <= limit:
            return work, tokens_now, changed

        drop_idx = None

        last_user_idx = None
        for idx in range(len(work) - 1, -1, -1):
            m = work[idx]
            if isinstance(m, dict) and str(m.get("role", "")).lower() == "user":
                last_user_idx = idx
                break

        for idx in range(len(work)):
            m = work[idx]
            if not isinstance(m, dict):
                continue
            if str(m.get("role", "")).lower() == "system":
                continue
            if idx != last_user_idx:
                drop_idx = idx
                break

        if drop_idx is None:
            break
        del work[drop_idx]
        changed = True

    # 3) Final hard fallback: trim latest USER content by character cap.
    # Keep prefix (drop tail) to align with primary trimming strategy.
    latest_user_idx = None
    for idx in range(len(work) - 1, -1, -1):
        m = work[idx]
        if isinstance(m, dict) and str(m.get("role", "")).lower() == "user":
            latest_user_idx = idx
            break

    if latest_user_idx is not None and isinstance(work[latest_user_idx], dict):
        content = str(work[latest_user_idx].get("content") or "")
        if content:
            cap = max(256, min(len(content), 2048))
            work[latest_user_idx]["content"] = content[:cap]
            changed = True

    return work, _count(work), changed


@app.route("/llms/api/chat/stream", methods=["POST"])
def llms_chat_stream():
    ok, err = _llms_require_token(request)
    if not ok:
        return err
    if _llm_engine is None or _llm_registry is None:
        return jsonify(detail="LLMs engine not initialized"), 500

    req = request.get_json(silent=True) or {}
    model_id = (req.get("model_id") or "").strip()
    messages = req.get("messages") or []
    # Keep /generate responsive for short prompts when client does not specify token budget.
    # Client can still override by sending max_new_tokens explicitly.
    _req_mnt = req.get("max_new_tokens")
    if _req_mnt is None:
        max_new_tokens = int(min(int(settings_all.LLM_DEFAULT_MAX_NEW_TOKENS), 128))
    else:
        max_new_tokens = int(_req_mnt)
    temperature = req.get("temperature")
    temperature = float(settings_all.LLM_DEFAULT_TEMPERATURE if temperature is None else temperature)

    # Nếu không truyền model_id thì mặc định dùng SPECIAL_MODEL_ID
    if _use_ollama_llm:
        model_id = getattr(_llm_engine, "active_id", None) or settings_all.OLLAMA_MODEL
        cfg = getattr(_llm_engine, "cfg", None) or {}
    else:
        if not model_id:
            model_id = (settings_all.SPECIAL_MODEL_ID or "").strip()
        if not model_id or not _llm_registry.has(model_id):
            return jsonify(detail="Unknown model_id"), 400
        cfg = _llm_registry.get(model_id)
    if not isinstance(messages, list) or not messages:
        return jsonify(detail="messages is required"), 400

    # ensure model loaded
    try:
        _llms_load_model_best_effort(model_id, cfg)
    except Exception as e:
        return jsonify(detail=f"Load failed: {e}"), 400

    # chèn system prompt nếu thiếu
    if not any(isinstance(m, dict) and m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": settings_all.LLM_DEFAULT_SYSTEM_PROMPT}] + messages

    def gen():
        yield _sse({"type": "meta", "model_id": model_id, "model_name": cfg.get("name") or model_id, "ts": time.time()})
        try:
            for delta in _llm_engine.stream_chat(messages, max_new_tokens=max_new_tokens, temperature=temperature):
                if delta:
                    yield _sse({"type": "delta", "text": delta})
            yield _sse({"type": "done"})
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})

    return Response(gen(), mimetype="text/event-stream")


@app.route("/llms/api/generate", methods=["POST"])
def llms_generate():
    ok, err = _llms_require_token(request)
    if not ok:
        return err
    if _llm_engine is None or _llm_registry is None:
        return jsonify(detail="LLMs engine not initialized"), 500

    req = request.get_json(silent=True) or {}
    model_id = (req.get("model_id") or "").strip()
    # Nếu không truyền model_id thì mặc định dùng SPECIAL_MODEL_ID
    if _use_ollama_llm:
        model_id = getattr(_llm_engine, "active_id", None) or settings_all.OLLAMA_MODEL
        cfg = getattr(_llm_engine, "cfg", None) or {}
    else:
        if not model_id:
            model_id = (settings_all.SPECIAL_MODEL_ID or "").strip()
        if not model_id or not _llm_registry.has(model_id):
            return jsonify(detail="Unknown model_id"), 400
        cfg = _llm_registry.get(model_id)
    try:
        _llms_load_model_best_effort(model_id, cfg)
    except Exception as e:
        return jsonify(detail=f"Load failed: {e}"), 400

    _req_mnt = req.get("max_new_tokens")
    if _req_mnt is None:
        max_new_tokens = int(min(int(settings_all.LLM_DEFAULT_MAX_NEW_TOKENS), 128))
    else:
        max_new_tokens = int(_req_mnt)
    temperature = req.get("temperature")
    temperature = float(settings_all.LLM_DEFAULT_TEMPERATURE if temperature is None else temperature)

    sys_prompt = (req.get("sys_prompt") or "").strip() or settings_all.LLM_DEFAULT_SYSTEM_PROMPT
    user_prompt = (req.get("user_prompt") or "").strip()
    if not user_prompt:
        return jsonify(detail="user_prompt is required"), 400

    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

    try:
        text = _llms_generate_with_oom_retry(
            model_id=model_id,
            cfg=cfg,
            messages=messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
        return jsonify(model_id=model_id, text=text)
    except Exception as e:
        return jsonify(detail=f"Generate failed: {e}"), 400


@app.route("/llms/api/token/status", methods=["GET"])
def llms_token_status():
    expected = (settings_all.LLM_API_TOKEN or "").strip()
    return jsonify(enabled=bool(expected and expected != "CHANGE_ME"))


def _parse_data_holiday_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for date_format in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None

@app.route("/api/data_holidays", methods=["POST"])
def data_holidays_save():
    import json as _json

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status=False, message="fail", detail="request body must be a JSON object"), 400

    master = payload.get("Master")
    detail = payload.get("Detail")
    if not isinstance(master, dict):
        return jsonify(status=False, message="fail", detail="Master is required and must be an object"), 400
    if not isinstance(detail, dict):
        return jsonify(status=False, message="fail", detail="Detail is required and must be an object"), 400

    try:
        year = int(master.get("Year"))
    except Exception:
        return jsonify(status=False, message="fail", detail="Master.Year must be an integer"), 400
    if year < 1900 or year > 3000:
        return jsonify(status=False, message="fail", detail="Master.Year is out of supported range"), 400

    weekly_days_off = detail.get("WeeklyDaysOff")
    if not isinstance(weekly_days_off, dict):
        return jsonify(status=False, message="fail", detail="Detail.WeeklyDaysOff is required and must be an object"), 400
    for key in ("IsWorkMon", "IsWorkTues", "IsWorkTue", "IsWorkWed", "IsWorkThurs", "IsWorkThu", "IsWorkFri", "IsWorkSat", "IsWorkSun"):
        if key in weekly_days_off and not isinstance(weekly_days_off.get(key), bool):
            return jsonify(status=False, message="fail", detail=f"Detail.WeeklyDaysOff.{key} must be boolean"), 400

    public_holidays = detail.get("PublicHolidays", [])
    if public_holidays is None:
        public_holidays = []
    if not isinstance(public_holidays, list):
        return jsonify(status=False, message="fail", detail="Detail.PublicHolidays must be a list"), 400

    normalized_holidays = []
    for idx, item in enumerate(public_holidays, start=1):
        if not isinstance(item, dict):
            return jsonify(status=False, message="fail", detail=f"Detail.PublicHolidays[{idx}] must be an object"), 400
        from_date = _parse_data_holiday_date(item.get("FromDate"))
        to_date = _parse_data_holiday_date(item.get("ToDate"))
        if from_date is None:
            return jsonify(status=False, message="fail", detail=f"Detail.PublicHolidays[{idx}].FromDate is invalid"), 400
        if to_date is None:
            to_date = from_date
        if to_date < from_date:
            return jsonify(status=False, message="fail", detail=f"Detail.PublicHolidays[{idx}].ToDate must be >= FromDate"), 400
        normalized_holidays.append({
            "HolidayName": item.get("HolidayName"),
            "FromDate": from_date.strftime("%d/%m/%Y"),
            "ToDate": to_date.strftime("%d/%m/%Y"),
        })

    save_payload = {
        "Master": {
            "HolidaySettingCode": str(master.get("HolidaySettingCode") or "Mã thiết lập ngày nghỉ"),
            "Year": year,
        },
        "Detail": {
            "WeeklyDaysOff": dict(weekly_days_off),
            "PublicHolidays": normalized_holidays,
        },
    }

    try:
        DATA_HOLIDAYS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_HOLIDAYS_DIR / f"{year}.json"
        tmp_path = DATA_HOLIDAYS_DIR / f".{year}.{uuid.uuid4().hex}.tmp"
        tmp_path.write_text(_json.dumps(save_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(out_path)
        clear_holiday_setting_cache()
    except Exception as e:
        logger.exception("Failed to save data holidays")
        return jsonify(status=False, message="fail", detail=f"failed to save data holidays: {e}"), 500

    logger.info("Saved data holidays: year=%s path=%s holidays=%d", year, out_path, len(normalized_holidays))
    return jsonify(status=True, message="success")

@app.route("/api/train/run", methods=["POST"])
def llms_train_lora_api():
    ok, err = _llms_require_token(request)
    if not ok:
        status_code = 401
        detail_text = "Invalid token"
        try:
            if isinstance(err, tuple):
                if len(err) >= 2 and isinstance(err[1], int):
                    status_code = err[1]
                resp_obj = err[0]
            else:
                resp_obj = err
            if hasattr(resp_obj, "get_json"):
                body = resp_obj.get_json(silent=True) or {}
                if isinstance(body, dict):
                    detail_text = str(body.get("detail") or body.get("error") or detail_text)
        except Exception:
            pass
        return jsonify(status=False, message="fail", detail=detail_text), status_code

    if _use_ollama_llm:
        return jsonify(
            status=False,
            message="fail",
            detail="Local LLM training is disabled while LLM_USE_OLLAMA=true",
        ), 409

    if not _llms_train_lock.acquire(blocking=False):
        return jsonify(status=False, message="fail", detail="Training is already running"), 409

    global _engine, _llm_engine, _llm_registry, _llm_ready

    import json as _json

    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        _llms_train_lock.release()
        return jsonify(status=False, message="fail", detail="request body must be a JSON object"), 400

    data_items = None
    for key in ("train_data", "items", "data", "samples"):
        if isinstance(req.get(key), list):
            data_items = req.get(key)
            break
    if not data_items:
        _llms_train_lock.release()
        return jsonify(status=False, message="fail", detail="train_data is required"), 400

    train_cfg = req.get("train_config")
    if isinstance(train_cfg, dict):
        cfg_src = train_cfg
    else:
        cfg_src = req

    new_model_name = str(cfg_src.get("new_model_name") or "").strip()
    old_model_raw = cfg_src.get("old_model_name", None)
    old_model_name = "" if old_model_raw is None else str(old_model_raw).strip()

    if "num_epochs" not in cfg_src:
        num_epochs = 5
    else:
        try:
            num_epochs = int(cfg_src.get("num_epochs"))
        except Exception:
            _llms_train_lock.release()
            return jsonify(status=False, message="fail", detail="num_epochs must be an integer"), 400

    if num_epochs <= 0:
        _llms_train_lock.release()
        return jsonify(status=False, message="fail", detail="num_epochs must be > 0"), 400

    if not new_model_name:
        _llms_train_lock.release()
        return jsonify(status=False, message="fail", detail="new_model_name is required"), 400

    data_dir = Path(PROJECT_ROOT) / "App" / "LLMs_Train" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "train.jsonl"
    try:
        with out_path.open("a", encoding="utf-8", newline="\n") as f:
            for item in data_items:
                if not isinstance(item, dict):
                    _llms_train_lock.release()
                    return jsonify(status=False, message="fail", detail="each train_data item must be an object"), 400

                messages = item.get("messages")
                if not isinstance(messages, list) or not messages:
                    _llms_train_lock.release()
                    return jsonify(status=False, message="fail", detail="each train_data item must include non-empty messages"), 400

                roles = {
                    str(m.get("role", "")).lower()
                    for m in messages
                    if isinstance(m, dict)
                }
                if not {"system", "user", "assistant"}.issubset(roles):
                    _llms_train_lock.release()
                    return jsonify(status=False, message="fail", detail="messages must include system, user, and assistant roles"), 400

                f.write(_json.dumps(item, ensure_ascii=False))
                f.write("\n")
    except Exception as e:
        _llms_train_lock.release()
        return jsonify(status=False, message="fail", detail=f"failed to append train_data: {e}"), 500

    training_result = None
    training_error_detail = None
    reload_error = None

    try:
        logger.info("/api/train/run begin: old_model_name=%s new_model_name=%s num_epochs=%s", old_model_name, new_model_name, num_epochs)
        logger.info("/api/train/run vram@begin: %s", _cuda_mem_snapshot())

        # 1) Unload OCR + active LLM model to clean VRAM before training.
        _llm_ready = False

        try:
            _switch_to_llm_only(reason="llms_train_begin")
        except Exception as e:
            logger.warning("Failed switching to llm_only before training: %s", repr(e))

        try:
            if _llm_engine is not None:
                _llm_engine.unload()
        except Exception as e:
            logger.warning("Failed to unload active LLM model before training: %s", repr(e))

        try:
            _ocr_hard_unload()
        except Exception as e:
            logger.warning("Failed to hard unload OCR engine before training: %s", repr(e))
            _engine = None

        _llms_hard_vram_cleanup(rounds=4)
        logger.info("/api/train/run vram@after_pre_cleanup: %s", _cuda_mem_snapshot())

        # 2) Train LoRA.
        from .LLMs_Train.train import train_lora, _train_log

        _train_log(
            "/api/train/run begin old_model_name=%s new_model_name=%s num_epochs=%s",
            old_model_name,
            new_model_name,
            num_epochs,
        )

        special_id = (settings_all.SPECIAL_MODEL_ID or "").strip()
        if not special_id or _llm_registry is None or not _llm_registry.has(special_id):
            raise RuntimeError(f"SPECIAL_MODEL_ID not found in registry: {special_id}")
        special_cfg = _llm_registry.get(special_id)
        special_base_dir = ""
        try:
            special_base_dir = str(_llm_registry.resolve_local_path(special_id) or "")
        except Exception:
            special_base_dir = ""

        training_result = train_lora(
            num_epochs=num_epochs,
            lora_name=new_model_name,
            old_lora_name=old_model_name,
            model_id=special_id,
            model_cfg=special_cfg,
            base_dir=special_base_dir or None,
        )

    except Exception as e:
        # IMPORTANT: do not keep exception object/traceback alive (can retain large tensors).
        try:
            import traceback as _traceback

            _tb = e.__traceback__
            if _tb is not None:
                _traceback.clear_frames(_tb)
        except Exception:
            pass

        training_error_detail = str(e)
        logger.error("/api/train/run failed during training: %s", repr(e), exc_info=True)
        try:
            from .LLMs_Train.train import _train_log, _train_log_exception

            _train_log("/api/train/run failed during training: %s", repr(e))
            _train_log_exception("/api/train/run traceback")
        except Exception:
            pass
        logger.info("/api/train/run vram@after_training_error: %s", _cuda_mem_snapshot())
    finally:
        # 3) Always clean VRAM again after training (success/failure) before reload.
        try:
            if _llm_engine is not None:
                _llm_engine.unload()
        except Exception as e:
            logger.warning("Failed to unload active LLM model after training: %s", repr(e))

        try:
            _ocr_hard_unload()
        except Exception as e:
            logger.warning("Failed to hard unload OCR engine after training: %s", repr(e))
            _engine = None

        _llms_hard_vram_cleanup(rounds=4)
        logger.info("/api/train/run vram@after_post_cleanup: %s", _cuda_mem_snapshot())

        # 4) Restore the same resource mode used at startup. When the special
        # LLM autoloads, keep OCR unloaded so both frameworks do not occupy
        # VRAM at the same time.
        if _autoload_llm_at_startup:
            _engine = None
            logger.info("Reload OCR skipped after training; LLM autoload mode is active.")
        else:
            try:
                _engine = OCREngine()
            except Exception as e:
                reload_error = RuntimeError(f"Reload OCR failed: {e}")
                logger.error("Reload OCR failed after training: %s", repr(e), exc_info=True)

        try:
            if _llm_engine is not None and _llm_registry is not None:
                special_id = (settings_all.SPECIAL_MODEL_ID or "").strip()
                if special_id and _llm_registry.has(special_id):
                    cfg = _llm_registry.get(special_id)
                    _llms_load_model_best_effort(special_id, cfg)
            _llm_ready = (_llm_engine is not None and _llm_registry is not None)
        except Exception as e:
            reload_error = RuntimeError(f"Reload SPECIAL_MODEL_ID failed: {e}")
            _llm_ready = False
            logger.error("Reload LLM SPECIAL_MODEL_ID failed after training: %s", repr(e), exc_info=True)

        logger.info("/api/train/run vram@after_reload: %s", _cuda_mem_snapshot())

        _llms_train_lock.release()

    if training_error_detail is not None:
        return jsonify(status=False, message="fail", detail=f"Training failed: {training_error_detail}"), 500

    if reload_error is not None:
        return jsonify(status=False, message="fail", detail=str(reload_error)), 500

    if not isinstance(training_result, dict):
        return jsonify(status=False, message="fail", detail="Unexpected training result format"), 500

    return jsonify(status=True, message="success")


@app.route("/llms/api/ai_llms_models", methods=["POST"])
def llms_ai_llms_models():
    import json as _json

    # ---------------------------------------------------------------------
    # Bước 1: Hàm trả dữ liệu theo đúng định dạng mà UI đang dùng.
    # Mọi phản hồi đều bọc trong: {"text": "..."}
    # ---------------------------------------------------------------------
    def _endpoint_text(payload: object, status_code: int = 200):
        return jsonify({"text": _json.dumps(payload, ensure_ascii=False, sort_keys=False)}), status_code

    # ---------------------------------------------------------------------
    # Bước 2: Đọc lỗi xác thực token theo format cũ.
    # Trả về: mã lỗi HTTP và nội dung lỗi ngắn gọn.
    # ---------------------------------------------------------------------
    def _extract_auth_error(err_obj) -> tuple[int, str]:
        status_code = 401
        detail_text = "Invalid token"
        try:
            if isinstance(err_obj, tuple):
                if len(err_obj) >= 2 and isinstance(err_obj[1], int):
                    status_code = err_obj[1]
                resp_obj = err_obj[0]
            else:
                resp_obj = err_obj

            if hasattr(resp_obj, "get_json"):
                body = resp_obj.get_json(silent=True) or {}
                if isinstance(body, dict):
                    detail_text = str(body.get("detail") or body.get("error") or detail_text)
        except Exception:
            pass
        return status_code, detail_text

    # ---------------------------------------------------------------------
    # Bước 3: Lấy prompt cần xử lý.
    # - Ưu tiên message user gần nhất có nội dung.
    # - Nếu không có, lấy message gần nhất có nội dung bất kỳ.
    # - Lấy thêm system prompt gần nhất (nếu có).
    # ---------------------------------------------------------------------
    def _extract_latest_prompts(messages: list) -> tuple[Optional[str], str]:
        latest_user_local = None
        for item in reversed(messages):
            if isinstance(item, dict) and str(item.get("role", "")).lower() == "user":
                txt = str(item.get("content") or "").strip()
                if txt:
                    latest_user_local = txt
                    break

        if latest_user_local is None:
            for item in reversed(messages):
                if isinstance(item, dict):
                    txt = str(item.get("content") or "").strip()
                    if txt:
                        latest_user_local = txt
                        break

        latest_system_local = ""
        for item in reversed(messages):
            if isinstance(item, dict) and str(item.get("role", "")).lower() == "system":
                latest_system_local = str(item.get("content") or "")
                break

        return latest_user_local, latest_system_local

    # ---------------------------------------------------------------------
    # Bước 4: Kiểm tra điều kiện trước khi chạy.
    # - Token hợp lệ
    # - Engine LLM đã sẵn sàng
    # - Không bị khóa bởi tiến trình train
    # ---------------------------------------------------------------------
    ok, err = _llms_require_token(request)
    if not ok:
        status_code, detail_text = _extract_auth_error(err)
        return _endpoint_text({"detail": detail_text}, status_code)

    if _llm_engine is None or _llm_registry is None:
        return _endpoint_text({"detail": "LLMs engine not initialized"}, 500)

    if _llms_train_lock.locked():
        return _endpoint_text({"detail": "LLMs training is running"}, 409)

    if should_unload_ocr_before_ai_inference(settings_all):
        try:
            _switch_to_llm_only(reason="ai_llms_models_infer")
        except Exception as e:
            return _endpoint_text({"detail": f"Failed to unload OCR before LLM inference: {e}"}, 500)

    # ---------------------------------------------------------------------
    # Bước 5: Đọc dữ liệu request và lấy prompt hiện tại.
    # ---------------------------------------------------------------------
    req = request.get_json(silent=True) or {}
    client_messages = req.get("messages") or []
    if not isinstance(client_messages, list) or not client_messages:
        return _endpoint_text({"detail": "messages is required"}, 400)

    latest_user, latest_system = _extract_latest_prompts(client_messages)

    if not latest_user:
        return _endpoint_text({"detail": "messages must contain at least one non-empty message"}, 400)

    # ---------------------------------------------------------------------
    # Bước 6: Các hàm phụ trợ bên trong endpoint.
    # Nhóm này xử lý làm sạch text, ghi log, đếm/trim token, và generate.
    # ---------------------------------------------------------------------
    def _strip_thinking(raw: object) -> str:
        if raw is None:
            return ""
        if not isinstance(raw, str):
            return str(raw)

        s = raw.strip()
        if not s:
            return ""

        low = s.lower()
        for marker in ["assistantfinal", "assistant final", "assistant_final"]:
            idx = low.rfind(marker)
            if idx != -1:
                out = s[idx + len(marker):].lstrip()
                if out.startswith(":"):
                    out = out[1:].lstrip()
                return out

        if low.startswith("analysis"):
            cut = low.find("final")
            if cut != -1:
                out = s[cut + len("final"):].lstrip()
                if out.startswith(":"):
                    out = out[1:].lstrip()
                return out
            return s[len("analysis"):].lstrip(": \n\t")

        return s

    def _append_response_log(payload: object, seq_override: Optional[int] = None) -> Optional[int]:
        try:
            import json as _json

            out_dir = Path(settings.OUTPUT_ROOT) / "llms"
            out_dir.mkdir(parents=True, exist_ok=True)

            log_path = out_dir / "respond_AI.txt"
            sep = "------------------------------------------------------"

            body = payload
            if isinstance(payload, (dict, list)):
                body = _json.dumps(payload, ensure_ascii=False, indent=2)

            ts_iso = datetime.now().isoformat(timespec="seconds")
            with _llms_log_file_lock:
                seq = int(seq_override) if seq_override is not None else 1
                if seq_override is None:
                    try:
                        if log_path.exists():
                            text = log_path.read_text(encoding="utf-8", errors="ignore")
                            nums = [int(x) for x in re.findall(r"^#(\d+)\b", text, flags=re.M)]
                            if nums:
                                seq = max(nums) + 1
                    except Exception:
                        seq = 1

                with log_path.open("a", encoding="utf-8", newline="\n") as f:
                    if log_path.exists() and log_path.stat().st_size > 0:
                        f.write("\n")
                    f.write(f"{sep}\n")
                    f.write(f"#{seq} [{ts_iso}] respond\n")
                    f.write(str(body or ""))
                    f.write("\n")
            return seq
        except Exception as _e:
            logger.warning("Failed to write Outputs/llms/respond_AI.txt: %s", repr(_e))
            return None

    def _json_dumps_preserve_order(payload: object, pretty: bool = False) -> str:
        import json as _json
        return _json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=False,
            indent=2 if pretty else None,
        )

    def _as_text_payload(payload: object):
        return jsonify({"text": _json_dumps_preserve_order(payload, pretty=False)})

    def _log_prompt_snapshot(messages: list, prompt_tokens_before: Optional[int], prompt_tokens_after: Optional[int], prompt_trimmed: bool, max_model_len: int, max_new_tokens: int, temperature: float, special_id: str, cfg: dict, extra: dict | None = None, log_filename: str = "prompt_client.txt", seq_override: Optional[int] = None) -> Optional[int]:
        try:
            import json as _json

            prompt_tokens = prompt_tokens_after
            batch_size = None
            stats = None
            try:
                stats = _llm_engine.prompt_stats(messages)
                if isinstance(stats, dict):
                    if prompt_tokens is None:
                        prompt_tokens = stats.get("prompt_tokens")
                    batch_size = stats.get("batch_size")
            except Exception:
                stats = None

            if prompt_tokens is None:
                try:
                    prompt_tokens = _llm_engine.count_prompt_tokens(messages)
                except Exception:
                    prompt_tokens = None

            out_dir = Path(settings.OUTPUT_ROOT) / "llms"
            out_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "ts": time.time(),
                "ts_iso": datetime.now().isoformat(timespec="seconds"),
                "remote_addr": request.remote_addr,
                "special_model_id": special_id,
                "model_name": (cfg.get("name") if isinstance(cfg, dict) else None) or special_id,
                "runtime": (getattr(_llm_engine, "runtime_info", lambda: None)() if _llm_engine is not None else None),
                "max_model_len": max_model_len,
                "prompt_tokens_before": prompt_tokens_before,
                "prompt_tokens": prompt_tokens,
                "prompt_trimmed": bool(prompt_trimmed),
                "batch_size": batch_size,
                "body": {
                    "messages": messages,
                    "max_new_tokens": max_new_tokens,
                    "temperature": temperature,
                },
            }
            if isinstance(extra, dict) and extra:
                payload["extra"] = extra

            log_path = out_dir / log_filename
            sep = "------------------------------------------------------"
            with _llms_log_file_lock:
                seq = int(seq_override) if seq_override is not None else 1
                if seq_override is None:
                    try:
                        if log_path.exists():
                            text = log_path.read_text(encoding="utf-8", errors="ignore")
                            nums = [int(x) for x in re.findall(r"^#(\d+)\b", text, flags=re.M)]
                            if nums:
                                seq = max(nums) + 1
                    except Exception:
                        seq = 1

                with log_path.open("a", encoding="utf-8", newline="\n") as f:
                    if log_path.exists() and log_path.stat().st_size > 0:
                        f.write("\n")
                    f.write(f"{sep}\n")
                    f.write(f"#{seq} [{datetime.now().isoformat(timespec='seconds')}] prompt\n")
                    f.write(_json.dumps(payload, ensure_ascii=False, indent=2))
                    f.write("\n")
            return seq
        except Exception as _e:
            logger.warning("Failed to write Outputs/llms/%s: %s", log_filename, repr(_e))
            return None

    def _generate_with_trim(base_messages: list, cfg: dict, special_id: str, max_new_tokens: int, temperature: float, log_prompt_snapshot: bool = False, think: Optional[bool] = None) -> str:
        if _llm_engine is None:
            raise RuntimeError("LLMs engine not initialized")

        max_model_len = int((cfg or {}).get("max_model_len") or 8192)
        trim_target = max(1, max_model_len - 8)

        messages = [dict(m) if isinstance(m, dict) else m for m in (base_messages or [])]

        prompt_tokens_before = None
        try:
            stats_before = _llm_engine.prompt_stats(messages)
            if isinstance(stats_before, dict):
                prompt_tokens_before = stats_before.get("prompt_tokens")
            if prompt_tokens_before is None:
                prompt_tokens_before = _llm_engine.count_prompt_tokens(messages)
        except Exception:
            prompt_tokens_before = None

        prompt_tokens_after = prompt_tokens_before
        prompt_trimmed = False
        if prompt_tokens_before is not None and int(prompt_tokens_before) > max_model_len:
            messages, prompt_tokens_after, prompt_trimmed = _llms_trim_messages_to_max_tokens(
                messages=messages,
                max_tokens=trim_target,
            )
            logger.warning(
                "ai_llms_models prompt trimmed: before=%s after=%s trim_target=%s max_model_len=%s",
                prompt_tokens_before,
                prompt_tokens_after,
                trim_target,
                max_model_len,
            )
        if prompt_tokens_after is not None and int(prompt_tokens_after) > trim_target:
            logger.warning(
                "ai_llms_models prompt still over trim target after trim; continue best-effort: after=%s trim_target=%s max_model_len=%s",
                prompt_tokens_after,
                trim_target,
                max_model_len,
            )

        if log_prompt_snapshot:
            _log_prompt_snapshot(
                messages=messages,
                prompt_tokens_before=prompt_tokens_before,
                prompt_tokens_after=prompt_tokens_after,
                prompt_trimmed=prompt_trimmed,
                max_model_len=max_model_len,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                special_id=special_id,
                cfg=cfg,
            )

        def _generate_once(_messages: list) -> str:
            if bool(getattr(_llm_engine, "is_ollama", False)):
                text = _llm_engine.generate_chat(
                    _messages,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    think=think,
                )
            else:
                text = _llm_engine.generate_chat(
                    _messages,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                )
            return text

        first_error = None
        try:
            text = _generate_once(messages)
        except Exception as gen_err:
            first_error = {
                "is_oom": _is_cuda_oom_error(gen_err),
                "is_context_limit": _is_context_limit_error(gen_err),
                "message": str(gen_err),
            }

        # Retry after leaving the except scope. The exception traceback retains
        # the generate() frame and CUDA tensors while that scope is active.
        if first_error is not None:
            if first_error["is_oom"]:
                before_cleanup = _cuda_mem_snapshot()
                _llms_light_cuda_cleanup()
                after_cleanup = _cuda_mem_snapshot()
                logger.warning(
                    "ai_llms_models CUDA OOM: error=%s vram_before=%s vram_after_cleanup=%s",
                    first_error["message"],
                    before_cleanup,
                    after_cleanup,
                )

                current_tokens = prompt_tokens_after
                if current_tokens is None:
                    try:
                        stats_now = _llm_engine.prompt_stats(messages)
                        if isinstance(stats_now, dict):
                            current_tokens = stats_now.get("prompt_tokens")
                    except Exception:
                        current_tokens = None
                if current_tokens is None:
                    try:
                        current_tokens = _llm_engine.count_prompt_tokens(messages)
                    except Exception:
                        current_tokens = None

                if current_tokens is not None:
                    oom_retry_target = max(1, int(current_tokens) - 1500)
                else:
                    oom_retry_target = max(1, int(trim_target) - 1500)

                messages, prompt_tokens_after, prompt_trimmed2 = _llms_trim_messages_to_max_tokens(
                    messages=messages,
                    max_tokens=oom_retry_target,
                )
                prompt_trimmed = bool(prompt_trimmed or prompt_trimmed2)
                logger.warning(
                    "ai_llms_models OOM retry with extra trim: retry_target=%s prompt_tokens_after=%s",
                    oom_retry_target,
                    prompt_tokens_after,
                )

                try:
                    text = _generate_once(messages)
                except Exception as gen_err2:
                    if _is_cuda_oom_error(gen_err2):
                        _llms_light_cuda_cleanup()
                        raise RuntimeError("OutMemory")
                    raise
            elif not first_error["is_context_limit"]:
                raise RuntimeError(first_error["message"])
            else:
                retry_target = max(1, int(trim_target * 0.85))
                messages, prompt_tokens_after, prompt_trimmed2 = _llms_trim_messages_to_max_tokens(
                    messages=messages,
                    max_tokens=retry_target,
                )
                prompt_trimmed = bool(prompt_trimmed or prompt_trimmed2)
                logger.warning(
                    "ai_llms_models context-limit retry: retry_target=%s prompt_tokens_after=%s",
                    retry_target,
                    prompt_tokens_after,
                )
                text = _generate_once(messages)

        first_error = None
        return _strip_thinking(text)

    # ---------------------------------------------------------------------
    # Bước 7: Xác định model sẽ dùng, load model, và đọc tham số cài đặt.
    # ---------------------------------------------------------------------
    if _use_ollama_llm:
        special_id = getattr(_llm_engine, "active_id", None) or settings_all.OLLAMA_MODEL
        cfg = getattr(_llm_engine, "cfg", None) or {}
    else:
        special_id = (settings_all.SPECIAL_MODEL_ID or "").strip()
        if not special_id:
            return _as_text_payload({"detail": "SPECIAL_MODEL_ID is not configured"}), 500
        if not _llm_registry.has(special_id):
            return _as_text_payload({"detail": f"SPECIAL_MODEL_ID not found in registry: {special_id}"}), 400

        cfg = _llm_registry.get(special_id)

        try:
            _llms_load_model_best_effort(special_id, cfg)
        except Exception as e:
            return _as_text_payload({"detail": f"Load failed: {e}"}), 400

    _req_mnt = req.get("max_new_tokens")
    if _req_mnt is None:
        max_new_tokens = int(min(int(settings_all.LLM_DEFAULT_MAX_NEW_TOKENS), 128))
    else:
        max_new_tokens = int(_req_mnt)
    temperature = req.get("temperature")
    temperature = float(settings_all.LLM_DEFAULT_TEMPERATURE if temperature is None else temperature)

    # ---------------------------------------------------------------------
    # Bước 8: Ghi lại snapshot prompt ban đầu để theo dõi/debug.
    # Việc này chỉ phục vụ log, không làm đổi kết quả nghiệp vụ.
    # ---------------------------------------------------------------------
    initial_client_messages = [
        {"role": "system", "content": latest_system},
        {"role": "user", "content": latest_user},
    ]
    max_model_len_log = int((cfg or {}).get("max_model_len") or 8192)
    request_log_seq: Optional[int] = None
    try:
        prompt_tokens_initial = None
        try:
            stats_initial = _llm_engine.prompt_stats(initial_client_messages)
            if isinstance(stats_initial, dict):
                prompt_tokens_initial = stats_initial.get("prompt_tokens")
            if prompt_tokens_initial is None:
                prompt_tokens_initial = _llm_engine.count_prompt_tokens(initial_client_messages)
        except Exception:
            prompt_tokens_initial = None

        request_log_seq = _log_prompt_snapshot(
            messages=initial_client_messages,
            prompt_tokens_before=prompt_tokens_initial,
            prompt_tokens_after=prompt_tokens_initial,
            prompt_trimmed=False,
            max_model_len=max_model_len_log,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            special_id=special_id,
            cfg=cfg,
        )
    except Exception as _e:
        logger.warning("Failed to log initial client prompt for /api/ai_llms_models: %s", repr(_e))

    def _append_processed_prompt_snapshot(messages: list, extra: dict | None = None) -> None:
        _log_prompt_snapshot(
            messages=messages,
            prompt_tokens_before=None,
            prompt_tokens_after=None,
            prompt_trimmed=False,
            max_model_len=max_model_len_log,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            special_id=special_id,
            cfg=cfg,
            extra=extra,
            log_filename="prompt_client_1.txt",
            seq_override=request_log_seq,
        )

    # ---------------------------------------------------------------------
    # Bước 9: Chuyển phần rẽ nhánh nghiệp vụ sang file Rules riêng.
    # Endpoint này chỉ điều phối và trả response cuối cùng.
    # ---------------------------------------------------------------------
    try:
        result_payload, status_code = process_ai_llms_models_rules(
            latest_system=latest_system,
            latest_user=latest_user,
            cfg=cfg,
            special_id=special_id,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            ocr_split_max_pages=int(getattr(settings_all, "OCR_SPLIT_MAX_PAGES", 3)),
            ocr_split_overlap_pages=int(getattr(settings_all, "OCR_SPLIT_OVERLAP_PAGES", 0)),
            ocr_split_max_chars_per_page=int(getattr(settings_all, "OCR_SPLIT_MAX_CHARS_PER_PAGE", 10000)),
            ocr_skip_page_min_chars=int(getattr(settings_all, "OCR_SKIP_PAGE_MIN_CHARS", 20000)),
            normalize_txt_path=NORMALIZE_TXT_PATH,
            sections_txt_path=SECTIONS_TXT_PATH,
            data_holidays_dir=DATA_HOLIDAYS_DIR,
            split_ocr_text_fn=split_ocr_text,
            generate_with_trim_fn=_generate_with_trim,
            append_prompt_client_snapshot_fn=_append_processed_prompt_snapshot,
            append_response_log_fn=lambda payload: _append_response_log(payload, seq_override=request_log_seq),
            light_cuda_cleanup_fn=_llms_light_cuda_cleanup,
            logger=logger,
        )
        if int(status_code) != 200:
            return _as_text_payload(result_payload), int(status_code)
        return _as_text_payload(result_payload)
    except Exception as e:
        if str(e) == "OutMemory" or _is_cuda_oom_error(e):
            _llms_light_cuda_cleanup()
            return _as_text_payload({"detail": "OutMemory"})
        return _as_text_payload({"detail": f"Generate failed: {e}"}), 400
    finally:
        _llms_light_cuda_cleanup()

@app.route("/connect", methods=["GET"])
@app.route("/api/connect", methods=["GET"])
def llms_connect_compat_root():
    return llms_connect()


@app.route("/api/health", methods=["GET"])
def llms_health_compat_root():
    return llms_health()


@app.route("/api/models", methods=["GET"])
def llms_list_models_compat_root():
    return llms_list_models()


@app.route("/api/models/reload", methods=["POST"])
def llms_reload_models_compat_root():
    return llms_reload_models()


@app.route("/api/models/load", methods=["POST"])
def llms_load_model_compat_root():
    return llms_load_model()


@app.route("/api/models/unload", methods=["POST"])
def llms_unload_model_compat_root():
    return llms_unload_model()


@app.route("/api/chat/stream", methods=["POST"])
def llms_chat_stream_compat_root():
    return llms_chat_stream()


@app.route("/api/generate", methods=["POST"])
def llms_generate_compat_root():
    return llms_generate()


@app.route("/api/token/status", methods=["GET"])
def llms_token_status_compat_root():
    return llms_token_status()


@app.route("/api/ai_llms_models", methods=["POST"])
def llms_ai_llms_models_compat_root():
    return llms_ai_llms_models()


# // ============================================================================
# // API SUMMARY - ENDPOINTS DÀNH CHO CLIENT GỌI SERVER
# // ============================================================================
# // [UI / Health]
# // GET  /                         -> Trang chủ UI
# // GET  /ocr/                     -> UI OCR
# // GET  /llms/                    -> UI LLMs
# // GET  /ping                     -> Kiểm tra trạng thái OCR engine
# // GET  /favicon.ico              -> Favicon
# // GET  /static/<path:filename>   -> Static files dùng chung
# // GET  /llms/static/<path:filename> -> Static files cho UI LLMs
# //
# // [OCR]
# // POST /ocr                      -> OCR 1 hoặc nhiều file
# // GET  /Outputs/<path:filename>  -> Lấy file output đã sinh
# // GET  /annot-list?stem=<stem>   -> Lấy danh sách ảnh annotate
# //
# // [LLMs - Prefix /llms/api]
# // GET  /llms/api/health
# // GET  /llms/api/connect
# // GET  /llms/connect
# // GET  /llms/api/models
# // POST /llms/api/models/reload
# // POST /llms/api/models/load
# // POST /llms/api/models/unload
# // POST /llms/api/chat/stream
# // POST /llms/api/generate
# // GET  /llms/api/token/status
# // POST /llms/api/ai_llms_models
# //
# // [LLMs - Root compatibility routes]
# // GET  /connect
# // GET  /api/connect
# // GET  /api/health
# // GET  /api/models
# // POST /api/models/reload
# // POST /api/models/load
# // POST /api/models/unload
# // POST /api/chat/stream
# // POST /api/generate
# // GET  /api/token/status
# // POST /api/train/run
# // POST /api/data_holidays       
# // POST /api/ai_llms_models
