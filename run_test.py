import json
import logging
import os
import random
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Tuple
from urllib.parse import quote

from flask import Flask, Response, jsonify, request


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader for this standalone test server."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            if key:
                os.environ[key.strip()] = val.strip()


def _get_host_port() -> Tuple[str, int]:
    host = os.getenv("TEST_HOST", os.getenv("HOST", "192.168.0.134"))
    port = int(os.getenv("TEST_PORT", os.getenv("PORT", "4444")))
    return host, port


def _mock_delay_seconds() -> float:
    raw = os.getenv("TEST_MOCK_DELAY_SECONDS", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except Exception:
            pass
    return random.uniform(2.0, 8.0)


def _ocr_mock_delay_seconds() -> float:
    raw = os.getenv("TEST_OCR_MOCK_DELAY_SECONDS", os.getenv("TEST_MOCK_DELAY_SECONDS", "")).strip()
    if not raw:
        return random.uniform(2.0, 8.0)
    try:
        return max(0.0, float(raw))
    except Exception:
        return random.uniform(2.0, 8.0)


_load_dotenv(".env")

from App.settings_all import get_settings_all  # noqa: E402


settings_all = get_settings_all()
PROJECT_ROOT = str(Path(settings_all.PROJECT_ROOT).resolve())

app = Flask(__name__, static_folder=None)
_train_receive_lock = threading.Lock()
_request_seq_lock = threading.Lock()
_request_seq = 0

LOG_DIR = Path(PROJECT_ROOT) / "Logs"
LOG_FILE = LOG_DIR / "app.log"
OUTPUT_ROOT = Path(PROJECT_ROOT) / "Outputs"
LLMS_OUTPUT_DIR = OUTPUT_ROOT / "llms"
OCR_OUTPUT_DIR = OUTPUT_ROOT / "ocr"
TXT_OUTPUT_DIR = OUTPUT_ROOT / "txt"
FILES_OUTPUT_DIR = OUTPUT_ROOT / "files"
DATA_HOLIDAYS_DIR = Path(PROJECT_ROOT) / "App" / "Data_Holidays"
TEMP_DIR = Path(PROJECT_ROOT) / "Cache" / "temp"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LLMS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OCR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FILES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_HOLIDAYS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class RequestIPFilter(logging.Filter):
    def filter(self, record):
        try:
            record.client_ip = request.remote_addr or "-"
        except Exception:
            record.client_ip = "-"
        return True


logger = logging.getLogger("RUN_TEST_API")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.propagate = False

_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_handler.setFormatter(logging.Formatter("%(asctime)s | IP=%(client_ip)s | %(message)s"))
_handler.addFilter(RequestIPFilter())
_handler.setLevel(logging.INFO)
logger.addHandler(_handler)

logger.info("=== RUN_TEST MOCK API START ===")

ALLOWED_OCR_EXTS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".html", ".htm",
}


EXTRACT_SAMPLE_SECTIONS = {
    "sections": [
        {
            "master": {
                "SectionOrder": 1,
                "SectionType": "CUSTOMSHEET",
                "SectionTitle": "Tờ khai hàng hóa nhập khẩu (thông quan)",
                "TotalAmount": 4261520,
                "TotalCurrency": "JPY",
                "Signature": "VALID",
            },
            "details": [
                {
                    "DeclarationNo": "107994333640",
                    "ClearanceStatus": "YES",
                    "SupplierName": "JABURO INDUSTRY CO., LTD",
                    "StagingArea": "Địa điểm xếp hàng ở Nội bài- Hòa lạc",
                    "VoucherNo": "518-2602191",
                    "VoucherDate": "19/02/2026",
                    "DeliveryTerm": "CIP",
                    "Currency": "JPY",
                    "Amount": 2130760,
                    "Description": "ĐNCCK từ SBQT Nội Bài về Cty Meiko.TĐ:Nội Bài-Hòa Lạc.TGVC:40km/2h",
                    "ClearanceDate": "24/02/2026",
                    "OrderNo": "1",
                }
            ],
        }
    ]
}


SECTION_RULES = {
    "INVOICE": {"key": "VoucherNo", "fields": ["VoucherNo", "VoucherDate", "SupplierName", "DeliveryTerm", "Currency", "Amount"]},
    "COMMERCIALINVOICE": {"key": "VoucherNo", "fields": ["VoucherNo", "VoucherDate", "SupplierName", "DeliveryTerm", "Currency", "Amount"]},
    "CUSTOMSHEET": {"key": "DeclarationNo", "fields": ["DeclarationNo", "ClearanceStatus", "SupplierName", "StagingArea", "VoucherNo", "VoucherDate", "DeliveryTerm", "Currency", "Amount", "Description", "ClearanceDate"]},
    "PO": {"key": "ContractNo", "fields": ["ContractNo", "OrderDate", "RingiNo", "SupplierName", "Currency", "DeliveryTerm", "PaymentTerm", "Amount"]},
    "CONTRACT": {"key": "ContractNo", "fields": ["ContractNo", "OrderDate", "RingiNo", "SupplierName", "Currency", "DeliveryTerm", "PaymentTerm", "Amount"]},
    "RINGI": {"key": "RingiNo", "fields": ["RingiNo", "SupplierName", "PaymentTerm", "Currency", "Amount", "ApprovalLast"]},
    "INSPECTION": {"key": "ContractNo", "fields": ["ContractNo", "AcceptanceDate", "InspectionType", "SupplierName", "Currency", "Amount", "ApprovalLast", "RingiNo"]},
    "HANDOVER": {"key": "ContractNo", "fields": ["ContractNo", "HandoverDate", "HandoverType", "SupplierName", "RingiNo", "Currency", "Amount"]},
    "STATEMENT": {"key": "VoucherNo", "fields": ["VoucherNo", "VoucherDate", "SupplierName", "Currency", "Amount"]},
    "BILL": {"key": "BillNo", "fields": ["BillNo", "BillDate", "SupplierName", "GoodsName"]},
    "PACKINGLIST": {"key": "PackingListNo", "fields": ["PackingListNo", "PackingListDate", "SupplierName", "GoodsName", "Quantity"]},
    "OTHER": {"key": "VoucherName", "fields": ["VoucherName", "SupplierName", "Currency", "Amount", "Description"]},
}

SECTION_TITLES = {
    "INVOICE": "Invoice", "COMMERCIALINVOICE": "Commercial Invoice", "CUSTOMSHEET": "Customs Declaration Sheet",
    "PO": "Purchase Order", "CONTRACT": "Contract", "RINGI": "Ringi Approval", "INSPECTION": "Inspection Record",
    "HANDOVER": "Handover Record", "STATEMENT": "Statement", "BILL": "Bill of Lading", "PACKINGLIST": "Packing List", "OTHER": "Other Document",
}
FILENAME_SECTION_TYPE_PATTERNS = (
    ("INV_PL", ("INVOICE", "PACKINGLIST")),
    ("IV_PL", ("INVOICE", "PACKINGLIST")),
    ("IV-PL", ("INVOICE", "PACKINGLIST")),
    ("IN_PL", ("INVOICE", "PACKINGLIST")),
    ("COM_PL", ("COMMERCIALINVOICE", "PACKINGLIST")),
    ("HANDOVER_", ("HANDOVER",)),
    ("INSPEC_", ("INSPECTION",)),
    ("OTHER_", ("OTHER",)),
    ("INV_", ("INVOICE",)),
    ("IV_", ("INVOICE",)),
    ("VAT_", ("INVOICE",)),
    ("CUS_", ("CUSTOMSHEET",)),
    ("TOKHAIHQ7N_QDTQ", ("CUSTOMSHEET",)),
    ("PO_", ("PO",)),
    ("RING_", ("RINGI",)),
    ("RINGI_", ("RINGI",)),
    ("LIST_", ("STATEMENT",)),
    ("COM_", ("COMMERCIALINVOICE",)),
    ("PL_", ("PACKINGLIST",)),
    ("BILL_", ("BILL",)),
    ("CT_", ("CONTRACT",)),
    ("CSC_CT", ("CONTRACT",)),
)
PROMPT_FILENAME_RE = re.compile(
    r'(?i)(?:T?n\s*file|Ten\s*file|FileName|filename)\s*[:=]\s*["?]?(.+?)(?=(?:\s*[-??]\s*(?:D?\s*li?u\s*OCR|Du\s*lieu\s*OCR)|\s*[|}\r\n"?]|$))'
)
SUPPLIER_NAMES = ["JABURO INDUSTRY CO., LTD", "MEIKO ELECTRONICS CO., LTD", "ASOFT VIETNAM CO., LTD", "NIPPON LOGISTICS SERVICE", "FUJI MATERIAL TRADING CO., LTD"]
CURRENCIES = ["JPY", "USD", "VND", "EUR"]
DELIVERY_TERMS = ["CIP", "DAP", "FOB", "CIF", "EXW"]
PAYMENT_TERMS = ["T/T 30 days", "T/T 60 days", "L/C at sight", "Net 45", "Advance payment"]
GOODS_NAMES = ["PCB material", "Electronic components", "Copper foil", "Chemical solvent", "Machine spare parts"]
STAGING_AREAS = ["Noi Bai - Hoa Lac", "Hai Phong Port", "Tan Son Nhat Cargo", "Cat Lai Port", "Da Nang ICD"]


def _random_date(start: datetime | None = None, end: datetime | None = None) -> str:
    start = start or datetime(2026, 1, 1)
    end = end or datetime(2026, 12, 31)
    delta_days = max(0, (end - start).days)
    return (start + timedelta(days=random.randint(0, delta_days))).strftime("%d/%m/%Y")


def _random_code(prefix: str, digits: int = 8) -> str:
    return f"{prefix}-{random.randint(10 ** (digits - 1), (10 ** digits) - 1)}"


def _random_field_value(field_name: str, section_type: str) -> object:
    if field_name == "VoucherNo": return _random_code("INV", 8)
    if field_name == "VoucherDate": return _random_date()
    if field_name == "SupplierName": return random.choice(SUPPLIER_NAMES)
    if field_name == "DeliveryTerm": return random.choice(DELIVERY_TERMS)
    if field_name == "Currency": return random.choice(CURRENCIES)
    if field_name == "Amount": return random.randint(10_000, 9_999_999)
    if field_name == "DeclarationNo": return str(random.randint(10_000_000_000, 99_999_999_999))
    if field_name == "ClearanceStatus": return random.choice(["YES", "NO"])
    if field_name == "StagingArea": return random.choice(STAGING_AREAS)
    if field_name == "Description": return f"Mock {section_type} data for reconciliation testing"
    if field_name == "ClearanceDate": return _random_date()
    if field_name == "ContractNo": return _random_code("CTR", 7)
    if field_name == "OrderDate": return _random_date()
    if field_name == "RingiNo": return _random_code("RG", 6)
    if field_name == "PaymentTerm": return random.choice(PAYMENT_TERMS)
    if field_name == "ApprovalLast": return _random_date()
    if field_name == "AcceptanceDate": return _random_date()
    if field_name == "InspectionType": return random.choice(["Incoming", "Final", "Quality", "Acceptance"])
    if field_name == "HandoverDate": return _random_date()
    if field_name == "HandoverType": return random.choice(["Equipment", "Goods", "Document", "Service"])
    if field_name == "BillNo": return _random_code("BL", 8)
    if field_name == "BillDate": return _random_date()
    if field_name == "GoodsName": return random.choice(GOODS_NAMES)
    if field_name == "PackingListNo": return _random_code("PL", 8)
    if field_name == "PackingListDate": return _random_date()
    if field_name == "Quantity": return random.randint(1, 5000)
    if field_name == "VoucherName": return f"{section_type}-{uuid.uuid4().hex[:8].upper()}"
    return None


def _mock_section_detail(section_type: str, order_no: int) -> dict:
    detail = {field_name: _random_field_value(field_name, section_type) for field_name in SECTION_RULES[section_type]["fields"]}
    detail["OrderNo"] = str(order_no)
    return detail


def _extract_prompt_filenames(*texts: str) -> list[str]:
    filenames = []
    for text in texts:
        for match in PROMPT_FILENAME_RE.finditer(str(text or "")):
            filename = match.group(1).strip().strip("'??\"")
            if filename and filename not in filenames:
                filenames.append(filename)
    return filenames

def _section_types_for_filename(filename: str) -> tuple[str, ...]:
    normalized_name = Path(str(filename or "").strip()).name.upper()
    for prefix, section_types in FILENAME_SECTION_TYPE_PATTERNS:
        if normalized_name.startswith(prefix):
            return section_types
    return (random.choice(list(SECTION_RULES)),)

def _section_types_for_filenames(filenames: list[str]) -> tuple[str, ...] | None:
    if not filenames:
        return None

    selected_types = []
    for filename in filenames:
        for section_type in _section_types_for_filename(filename):
            if section_type not in selected_types:
                selected_types.append(section_type)
    return tuple(selected_types)

def _mock_dynamic_sections(section_types: tuple[str, ...] | None = None) -> dict:
    sections = []
    if section_types is None:
        available_types = list(SECTION_RULES)
        selected_types = random.sample(available_types, k=random.randint(2, min(5, len(available_types))))
    else:
        selected_types = list(section_types)
    for section_order, section_type in enumerate(selected_types, start=1):
        details = [_mock_section_detail(section_type, idx) for idx in range(1, random.randint(1, 3) + 1)]
        total_amount = sum(item.get("Amount") or 0 for item in details)
        total_currency = next((item.get("Currency") for item in details if item.get("Currency")), None)
        sections.append({
            "master": {"SectionOrder": section_order, "SectionType": section_type, "SectionTitle": SECTION_TITLES.get(section_type, section_type), "TotalAmount": total_amount, "TotalCurrency": total_currency, "Signature": random.choice(["VALID", "VALID", "INVALID", "BLANK"])},
            "details": details,
        })
    return {"sections": sections}


def _mock_extract_payload(*prompt_texts: str) -> dict:
    filenames = _extract_prompt_filenames(*prompt_texts)
    section_types = _section_types_for_filenames(filenames)
    return json.loads(json.dumps(_mock_dynamic_sections(section_types), ensure_ascii=False))

COMPARE_SAMPLE_CRITERIA = {
    "Hạn thanh toán": {
        "CriteriaName": "Hạn thanh toán",
        "CriteriaStatus": "OK",
        "FileName": "",
        "Description": "Hạn thanh toán đã hoàn toàn phù hợp.",
        "DueDateAI": "29/05/2026, 01/07/2026, 10/07/2026",
    },
    "Số hóa đơn": {
        "CriteriaName": "Số hóa đơn",
        "CriteriaStatus": "OK",
        "FileName": "INV-20260122.pdf",
        "Description": "Số hóa đơn trên chứng từ trùng với số hóa đơn trong hồ sơ thanh toán.",
    },
    "Ngày hóa đơn": {
        "CriteriaName": "Ngày hóa đơn",
        "CriteriaStatus": "OK",
        "FileName": "",
        "Description": "Ngày hóa đơn đã hoàn toàn hợp lệ và khớp với dữ liệu đối chiếu.",
    },
    "Tên nhà cung cấp": {
        "CriteriaName": "Tên nhà cung cấp",
        "CriteriaStatus": "OK",
        "FileName": "CommercialInvoice_TTST-202601220001.pdf",
        "Description": "Tên nhà cung cấp được xác định đầy đủ và không phát hiện sai lệch so với dữ liệu chuẩn.",
    },
    "Số tờ khai hải quan": {
        "CriteriaName": "Số tờ khai hải quan",
        "CriteriaStatus": "NG",
        "FileName": "CUSTOMSHEET_107962095252.pdf",
        "Description": "Số tờ khai trên chứng từ không khớp hoàn toàn với thông tin client gửi lên, cần kiểm tra lại hồ sơ gốc.",
    },
    "Tổng tiền thanh toán": {
        "CriteriaName": "Tổng tiền thanh toán",
        "CriteriaStatus": "OK",
        "FileName": "PaymentRequest_202601.pdf",
        "Description": "Tổng tiền thanh toán nằm trong ngưỡng hợp lệ và phù hợp với các chứng từ liên quan.",
    },
}


def _extract_criterion_name(user_prompt: str) -> str:
    match = re.search(r'"CriterionName"\s*:\s*"([^"]*)"', str(user_prompt or ""), flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _mock_compare_payload(user_prompt: str) -> dict:
    criterion_name = _extract_criterion_name(user_prompt)
    sample = COMPARE_SAMPLE_CRITERIA.get(criterion_name)
    if sample is None:
        sample = {
            "CriteriaName": criterion_name or "Không xác định",
            "CriteriaStatus": "OK",
            "FileName": "",
            "Description": "Tiêu chí đối chiếu đã hoàn toàn phù hợp.",
        }
    return {"criteria": dict(sample)}

def _next_request_seq() -> int:
    global _request_seq
    with _request_seq_lock:
        _request_seq += 1
        return _request_seq


def _request_seq_label() -> str:
    seq = getattr(request, "_seq", None)
    return f"REQ#{seq:06d}" if isinstance(seq, int) else "REQ#------"


def _json_text_payload(payload: object, status_code: int = 200):
    return jsonify({"text": json.dumps(payload, ensure_ascii=False, sort_keys=False)}), status_code


def _safe_json_body() -> object:
    try:
        return request.get_json(silent=True)
    except Exception as exc:
        return {"_parse_error": repr(exc)}


def _json_preview(payload: object, limit: int = 20000) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    except Exception:
        text = str(payload)
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"
    return text


def _append_text_log(path: Path, title: str, body: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            if path.exists() and path.stat().st_size > 0:
                f.write("\n")
            f.write("------------------------------------------------------\n")
            f.write(title.rstrip() + "\n")
            f.write(body.rstrip() + "\n")
    except Exception as exc:
        logger.warning("Failed to write input log %s: %s", path, repr(exc))


def _log_json_request_input(source: str, payload: object, extra: dict | None = None) -> None:
    seq_label = _request_seq_label()
    ts_iso = datetime.now().isoformat(timespec="seconds")
    body = {
        "ts": time.time(),
        "ts_iso": ts_iso,
        "seq": getattr(request, "_seq", None),
        "seq_label": seq_label,
        "rid": getattr(request, "_rid", "-"),
        "source": source,
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr,
        "query": request.args.to_dict(flat=False),
        "headers": {
            "Content-Type": request.headers.get("Content-Type"),
            "Authorization": "***" if request.headers.get("Authorization") else None,
            "X-API-Token": "***" if request.headers.get("X-API-Token") else None,
            "X-Api-Token": "***" if request.headers.get("X-Api-Token") else None,
        },
        "body": payload,
    }
    if extra:
        body["extra"] = extra

    _append_text_log(
        LLMS_OUTPUT_DIR / "prompt_client.txt",
        f"#{getattr(request, '_seq', 0)} [{ts_iso}] {seq_label} source={source} client_request",
        _json_preview(body),
    )


def _log_ocr_request_input(uploads: list) -> None:
    seq_label = _request_seq_label()
    ts_iso = datetime.now().isoformat(timespec="seconds")
    files = []
    for idx, upload in enumerate(uploads, start=1):
        filename = upload.filename or f"file_{idx}"
        files.append({
            "index": idx,
            "field": "file/files",
            "filename": filename,
            "extension": Path(filename).suffix.lower(),
            "content_type": getattr(upload, "content_type", None),
        })
    body = {
        "ts": time.time(),
        "ts_iso": ts_iso,
        "seq": getattr(request, "_seq", None),
        "seq_label": seq_label,
        "rid": getattr(request, "_rid", "-"),
        "source": "/ocr",
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr,
        "form": request.form.to_dict(flat=False),
        "files": files,
    }
    _append_text_log(
        OCR_OUTPUT_DIR / "request_client.txt",
        f"#{getattr(request, '_seq', 0)} [{ts_iso}] {seq_label} source=/ocr client_request",
        _json_preview(body),
    )


def _sanitize_stem(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "", str(name or "").strip())
    name = re.sub(r'\s+', "_", name)
    name = re.sub(r'_+', "_", name)
    name = name.strip("._")
    return name[:150] or uuid.uuid4().hex

def _save_original_upload_for_test(upload, filename: str, index: int) -> Path:
    """Save the exact file posted to /ocr for run_test.py-only debugging."""
    original_name = filename or f"file_{index}"
    original_path = Path(original_name)
    stem = _sanitize_stem(original_path.stem or f"file_{index}")
    ext = original_path.suffix.lower()
    seq = getattr(request, "_seq", 0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    saved_path = FILES_OUTPUT_DIR / f"{ts}_seq{seq}_{index}_{stem}{ext}"
    saved_path.parent.mkdir(parents=True, exist_ok=True)

    upload.save(str(saved_path))
    try:
        upload.stream.seek(0)
    except Exception:
        logger.warning("[%s] Could not rewind uploaded stream after saving original: %s", _request_seq_label(), original_name)

    logger.info("[%s] Saved original OCR upload: %s (size=%d)", _request_seq_label(), saved_path, saved_path.stat().st_size)
    return saved_path


def _build_content_disposition(filename: str) -> str:
    try:
        ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "output.txt"
    except Exception:
        ascii_name = "output.txt"
    if not ascii_name.lower().endswith(".txt"):
        ascii_name += ".txt"
    utf8_name = quote(filename, safe="")
    return f"attachment; filename={ascii_name}; filename*=UTF-8''{utf8_name}"


def _iter_file(path: Path, chunk: int = 65536):
    with path.open("rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            yield data


def _mock_ocr_pages(filename: str, seq_label: str) -> list[str]:
    now = datetime.now().isoformat(timespec="seconds")
    return [
        "\n".join([
            f"Mock OCR received 1 file(s) @ {now}",
            f"RequestSeq: {seq_label}",
            "",
            f"===== {filename} =====",
            "Đây là dữ liệu OCR mẫu dùng để test format request/response.",
            "Client đã gửi file đúng format multipart/form-data.",
        ])
    ]


def _save_mock_pages_txt(pages: list[str], stem: str) -> Path:
    txt_path = TXT_OUTPUT_DIR / f"{stem}.txt"
    lines: list[str] = []
    for page_index, page_text in enumerate(pages, start=1):
        if str(page_text or "").rstrip():
            lines.append(str(page_text).rstrip())
        lines.append(f"----{page_index}----")
        lines.append("")
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return txt_path


def _append_mock_response_log(payload: object) -> None:
    ts_iso = datetime.now().isoformat(timespec="seconds")
    _append_text_log(
        LLMS_OUTPUT_DIR / "respond_AI.txt",
        f"#{getattr(request, '_seq', 0)} [{ts_iso}] {_request_seq_label()} respond",
        _json_preview(payload),
    )


def _append_mock_sections_log(payload: object) -> None:
    ts_iso = datetime.now().isoformat(timespec="seconds")
    _append_text_log(
        OUTPUT_ROOT / "sections.txt",
        f"#{getattr(request, '_seq', 0)} [{ts_iso}] {_request_seq_label()} source=/api/ai_llms_models mode=PromptType=Trích xuất merged_sections",
        _json_preview(payload),
    )
    _append_text_log(
        LLMS_OUTPUT_DIR / "sections.txt",
        f"#{getattr(request, '_seq', 0)} [{ts_iso}] {_request_seq_label()} source=/api/ai_llms_models mode=PromptType=Trích xuất merged_sections",
        _json_preview(payload),
    )


def _extract_latest_prompts(messages: list) -> Tuple[str, str]:
    latest_user = ""
    latest_system = ""

    for item in reversed(messages):
        if isinstance(item, dict) and str(item.get("role", "")).lower() == "user":
            latest_user = str(item.get("content") or "").strip()
            break

    for item in reversed(messages):
        if isinstance(item, dict) and str(item.get("role", "")).lower() == "system":
            latest_system = str(item.get("content") or "").strip()
            break

    return latest_user, latest_system


def _is_extract_prompt(user_prompt: str) -> bool:
    match = re.search(r'"PromptType"\s*:\s*"([^"]*)"', str(user_prompt or ""), flags=re.IGNORECASE)
    if not match:
        return False

    no_marks = unicodedata.normalize("NFD", match.group(1))
    no_marks = "".join(ch for ch in no_marks if unicodedata.category(ch) != "Mn").lower()
    compact = "".join(ch for ch in no_marks if ch.isalnum())
    return compact == "trichxuat"


def _llms_require_token(flask_request):
    expected = (settings_all.LLM_API_TOKEN or "").strip()
    if not expected or expected == "CHANGE_ME":
        return False, (jsonify(detail="Server has not configured LLM_API_TOKEN"), 401)

    key = (settings_all.LLM_API_TOKEN_QUERY_KEY or "Token").strip() or "Token"
    got = (flask_request.args.get(key) or "").strip()

    if not got:
        auth = (flask_request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()

    if not got:
        got = (flask_request.headers.get("X-API-Token") or "").strip()

    if not got:
        got = (flask_request.headers.get("X-Api-Token") or "").strip()

    if got.startswith('"') and got.endswith('"') and len(got) >= 2:
        got = got[1:-1].strip()

    if got != expected:
        return False, (jsonify(detail="Invalid token"), 401)

    return True, None


def _extract_auth_error(err_obj) -> Tuple[int, str]:
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


@app.before_request
def _before():
    request._t0 = time.time()
    request._seq = _next_request_seq()
    request._rid = uuid.uuid4().hex[:12]
    logger.info(
        "[%s] [RID=%s] %s %s from %s, files=%d",
        _request_seq_label(),
        request._rid,
        request.method,
        request.path,
        request.remote_addr,
        0 if not request.files else len(request.files),
    )


@app.after_request
def _after(resp):
    dur = (time.time() - getattr(request, "_t0", time.time())) * 1000.0
    rid = getattr(request, "_rid", "-")
    logger.info(
        "[%s] [RID=%s] Done %s %s -> %s in %.1f ms",
        _request_seq_label(),
        rid,
        request.method,
        request.path,
        resp.status,
        dur,
    )
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-API-Token,X-Api-Token"
    return resp


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify(status="ok", service="receive-only-test-server", ts=time.time())


@app.route("/ocr", methods=["POST"])
def ocr_upload_receive_only():
    uploads = []
    single_file = request.files.get("file")
    if single_file:
        uploads.append(single_file)
    uploads.extend(request.files.getlist("files"))
    _log_ocr_request_input(uploads)

    if not uploads:
        logger.warning("[%s] No file uploaded", _request_seq_label())
        return jsonify(detail="Không có file được gửi lên."), 400

    # run_test.py-only: lưu lại file gốc client gửi để tiện debug/replay OCR.
    # Luồng production gốc không có bước này. Sau khi save, rewind stream để flow OCR mock tiếp tục dùng upload bình thường.
    try:
        for idx, upload in enumerate(uploads, start=1):
            _save_original_upload_for_test(upload, upload.filename or f"file_{idx}", idx)
    except Exception as e:
        logger.exception("[%s] Failed to save original OCR upload", _request_seq_label())
        return jsonify(detail=f"Không lưu được file gốc client gửi: {e}"), 500

    # --- 1 file: mô phỏng đúng flow gốc: nhận file -> lưu temp -> OCR infer -> save txt -> stream txt ---
    if len(uploads) == 1:
        upload = uploads[0]
        filename = upload.filename or "input"
        ext = Path(filename).suffix.lower()
        logger.info("[%s] OCR single file: %s (ext=%s)", _request_seq_label(), filename, ext)
        if ext not in ALLOWED_OCR_EXTS:
            logger.warning("[%s] Unsupported ext: %s", _request_seq_label(), ext)
            return jsonify(detail=f"Chỉ hỗ trợ: {', '.join(sorted(ALLOWED_OCR_EXTS))}"), 400

        stem = _sanitize_stem(Path(filename).stem)
        tmp = TEMP_DIR / f"{uuid.uuid4().hex}{ext}"
        try:
            upload.save(str(tmp))
            delay = _ocr_mock_delay_seconds()
            t1 = time.time()
            logger.info("[%s] OCR infer begin: %s", _request_seq_label(), tmp)
            time.sleep(delay)
            pages = _mock_ocr_pages(filename, _request_seq_label())
            logger.info("[%s] OCR infer done in %.2fs", _request_seq_label(), time.time() - t1)

            txt_path = _save_mock_pages_txt(pages, stem)
            logger.info("[%s] Saved TXT: %s (size=%d)", _request_seq_label(), txt_path, txt_path.stat().st_size)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

        cd = _build_content_disposition(txt_path.name)
        return Response(
            _iter_file(txt_path),
            headers={"Content-Disposition": cd},
            mimetype="text/plain; charset=utf-8",
        )

    # --- nhiều file: mô phỏng batch như flow gốc ---
    now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    batch_name = f"batch_{now}.txt"
    out_path = TXT_OUTPUT_DIR / batch_name
    result_lines = [f"Đã thực hiện OCR {len(uploads)} file @ {now}", ""]
    logger.info("[%s] OCR batch begin: %d files", _request_seq_label(), len(uploads))

    for idx, upload in enumerate(uploads, start=1):
        filename = upload.filename or f"file_{idx}"
        ext = Path(filename).suffix.lower()
        logger.info("[%s] Batch item %d/%d: %s (ext=%s)", _request_seq_label(), idx, len(uploads), filename, ext)

        result_lines.append(f"Nội dung: {'=' * 14} FILE {idx}/{len(uploads)} — {filename} {'=' * 14}")
        result_lines.append("")

        if ext not in ALLOWED_OCR_EXTS:
            logger.warning("[%s] Skip unsupported ext: %s", _request_seq_label(), ext)
            result_lines.append(f"⚠️ Bỏ qua — Không hỗ trợ định dạng {ext}")
            result_lines.append("")
            continue

        tmp = TEMP_DIR / f"{uuid.uuid4().hex}{ext}"
        try:
            upload.save(str(tmp))
            delay = _ocr_mock_delay_seconds()
            t2 = time.time()
            logger.info("[%s] OCR infer begin: %s", _request_seq_label(), tmp)
            time.sleep(delay)
            pages = _mock_ocr_pages(filename, _request_seq_label())
            logger.info("[%s] Infer %.2fs for %s", _request_seq_label(), time.time() - t2, filename)

            for page_index, page_text in enumerate(pages, start=1):
                if str(page_text or "").rstrip():
                    result_lines.append(str(page_text).rstrip())
                result_lines.append(f"----{page_index}----")
                result_lines.append("")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(result_lines), encoding="utf-8")
    logger.info("[%s] Batch saved: %s (size=%d)", _request_seq_label(), out_path, out_path.stat().st_size)

    cd = _build_content_disposition(out_path.name)
    return Response(
        _iter_file(out_path),
        headers={"Content-Disposition": cd},
        mimetype="text/plain; charset=utf-8",
    )


@app.route("/api/ai_llms_models", methods=["POST"])
@app.route("/llms/api/ai_llms_models", methods=["POST"])
def ai_llms_models_receive_only():
    req = _safe_json_body()
    _log_json_request_input(request.path, req)

    ok, err = _llms_require_token(request)
    if not ok:
        status_code, detail_text = _extract_auth_error(err)
        logger.warning("[%s] LLM mock rejected auth: %s", _request_seq_label(), detail_text)
        return _json_text_payload({"detail": detail_text}, status_code)

    if not isinstance(req, dict):
        logger.warning("[%s] LLM mock rejected: request body is not JSON object", _request_seq_label())
        return _json_text_payload({"detail": "request body must be a JSON object"}, 400)

    client_messages = req.get("messages") or []
    if not isinstance(client_messages, list) or not client_messages:
        logger.warning("[%s] LLM mock rejected: messages is required", _request_seq_label())
        return _json_text_payload({"detail": "messages is required"}, 400)

    for idx, message in enumerate(client_messages, start=1):
        if not isinstance(message, dict):
            logger.warning("[%s] LLM mock rejected: message %d is not object", _request_seq_label(), idx)
            return _json_text_payload({"detail": "each messages item must be an object"}, 400)
        role = str(message.get("role") or "").strip().lower()
        if role not in {"system", "user", "assistant"}:
            logger.warning("[%s] LLM mock rejected: message %d invalid role=%s", _request_seq_label(), idx, role)
            return _json_text_payload({"detail": "messages role must be system, user, or assistant"}, 400)
        content = message.get("content")
        if not isinstance(content, str):
            logger.warning("[%s] LLM mock rejected: message %d content is not string", _request_seq_label(), idx)
            return _json_text_payload({"detail": "messages content must be a string"}, 400)

    latest_user, latest_system = _extract_latest_prompts(client_messages)
    if not latest_user:
        logger.warning("[%s] LLM mock rejected: no non-empty user message", _request_seq_label())
        return _json_text_payload({"detail": "messages must contain at least one non-empty message"}, 400)

    delay = _mock_delay_seconds()
    logger.info("[%s] LLM mock processing delay %.2fs", _request_seq_label(), delay)
    time.sleep(delay)

    if _is_extract_prompt(latest_user):
        response_payload = _mock_extract_payload(latest_system, latest_user)
        mock_mode = "PromptType=Trích xuất"
        _append_mock_sections_log(response_payload)
    else:
        response_payload = _mock_compare_payload(latest_user)
        mock_mode = "PromptType=Đối chiếu"

    logger.info(
        "[%s] LLM mock success: mode=%s messages=%d latest_system_len=%d latest_user_len=%d",
        _request_seq_label(),
        mock_mode,
        len(client_messages),
        len(latest_system),
        len(latest_user),
    )
    _append_mock_response_log(response_payload)
    return _json_text_payload(response_payload)


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
        tmp_path.write_text(json.dumps(save_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(out_path)
    except Exception as e:
        logger.exception("[%s] Failed to save data holidays", _request_seq_label())
        return jsonify(status=False, message="fail", detail=f"failed to save data holidays: {e}"), 500

    logger.info("[%s] Saved data holidays: year=%s path=%s holidays=%d", _request_seq_label(), year, out_path, len(normalized_holidays))
    return jsonify(status=True, message="success")

@app.route("/api/train/run", methods=["POST"])
def llms_train_lora_api_receive_only():
    req = _safe_json_body()
    _log_json_request_input("/api/train/run", req)

    ok, err = _llms_require_token(request)
    if not ok:
        status_code, detail_text = _extract_auth_error(err)
        return jsonify(status=False, message="fail", detail=detail_text), status_code

    if not _train_receive_lock.acquire(blocking=False):
        return jsonify(status=False, message="fail", detail="Training is already running"), 409

    try:
        if not isinstance(req, dict):
            return jsonify(status=False, message="fail", detail="request body must be a JSON object"), 400

        data_items = None
        for key in ("train_data", "items", "data", "samples"):
            if isinstance(req.get(key), list):
                data_items = req.get(key)
                break
        if not data_items:
            return jsonify(status=False, message="fail", detail="train_data is required"), 400

        train_cfg = req.get("train_config")
        cfg_src = train_cfg if isinstance(train_cfg, dict) else req
        new_model_name = str(cfg_src.get("new_model_name") or "").strip()

        if "num_epochs" not in cfg_src:
            num_epochs = 5
        else:
            try:
                num_epochs = int(cfg_src.get("num_epochs"))
            except Exception:
                return jsonify(status=False, message="fail", detail="num_epochs must be an integer"), 400

        if num_epochs <= 0:
            return jsonify(status=False, message="fail", detail="num_epochs must be > 0"), 400

        if not new_model_name:
            return jsonify(status=False, message="fail", detail="new_model_name is required"), 400

        data_dir = Path(PROJECT_ROOT) / "App" / "LLMs_Train" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        out_path = data_dir / "train.jsonl"

        with out_path.open("a", encoding="utf-8", newline="\n") as f:
            for item in data_items:
                if not isinstance(item, dict):
                    return jsonify(status=False, message="fail", detail="each train_data item must be an object"), 400

                messages = item.get("messages")
                if not isinstance(messages, list) or not messages:
                    return jsonify(status=False, message="fail", detail="each train_data item must include non-empty messages"), 400

                roles = {
                    str(m.get("role", "")).lower()
                    for m in messages
                    if isinstance(m, dict)
                }
                if not {"system", "user", "assistant"}.issubset(roles):
                    return jsonify(status=False, message="fail", detail="messages must include system, user, and assistant roles"), 400

                f.write(json.dumps(item, ensure_ascii=False))
                f.write("\n")

        logger.info("[%s] Train mock success: samples=%d new_model_name=%s", _request_seq_label(), len(data_items), new_model_name)
        return jsonify(status=True, message="success")
    except Exception as e:
        logger.exception("[%s] Train mock failed", _request_seq_label())
        return jsonify(status=False, message="fail", detail=f"failed to append train_data: {e}"), 500
    finally:
        _train_receive_lock.release()


def main() -> None:
    host, port = _get_host_port()
    print(f"Starting Receive-Only Test Server at: http://{host}:{port}/")
    print("Routes: GET /ping, POST /ocr, POST /api/ai_llms_models, POST /llms/api/ai_llms_models, POST /api/data_holidays, POST /api/train/run")
    print(r"Logs: Logs\app.log, Outputs\llms\prompt_client.txt, Outputs\llms\respond_AI.txt, Outputs\ocr\request_client.txt")
    print(r"Original OCR uploads: Outputs\files")
    print("Mock delay: random 2-8s per OCR/LLM request; override with TEST_MOCK_DELAY_SECONDS=0")

    app.run(
        host=host,
        port=port,
        debug=os.getenv("TEST_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"},
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()


