"""Run LoRA training from App/LLMs_Train/data/train.xlsx.

The XLSX source must contain 4 columns: stt, prompt sys, prompt user, answer.
This script converts XLSX rows to the JSONL message format expected by the
existing train_lora core, then trains the current SPECIAL_MODEL_ID from
App/settings_all.py and writes LoRA output under App/LLMs_Train/models_lora.

Examples:
  py run_train.py --new-model-name my_lora --epochs 5
  py run_train.py --new-model-name my_lora --old-model-name previous_lora

Environment alternatives:
  TRAIN_NEW_MODEL_NAME=my_lora
  TRAIN_OLD_MODEL_NAME=previous_lora
  TRAIN_NUM_EPOCHS=5
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import zipfile
import xml.etree.ElementTree as ET
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train current SPECIAL_MODEL_ID using App/LLMs_Train/data/train.xlsx")
    parser.add_argument(
        "--new-model-name",
        default=os.getenv("TRAIN_NEW_MODEL_NAME", "").strip(),
        help="LoRA name to create. Env: TRAIN_NEW_MODEL_NAME. Default: auto timestamp name.",
    )
    parser.add_argument(
        "--old-model-name",
        default=os.getenv("TRAIN_OLD_MODEL_NAME", "").strip(),
        help="Optional existing LoRA name to continue from. Env: TRAIN_OLD_MODEL_NAME.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=int(os.getenv("TRAIN_NUM_EPOCHS", "5")),
        help="Training epochs. Env: TRAIN_NUM_EPOCHS. Default: 5.",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip generated train.jsonl schema validation before training.",
    )
    return parser.parse_args()



def _sample_rows() -> list[dict[str, str]]:
    extraction_system = "Bạn là AI trích xuất chứng từ kế toán. Trả về duy nhất JSON hợp lệ theo schema sections."
    compare_system = "Bạn là AI đối chiếu chứng từ kế toán. Trả về duy nhất JSON hợp lệ theo schema criteria."
    return [
        {
            "stt": "1",
            "prompt sys": extraction_system,
            "prompt user": "***\n{\"PromptType\":\"Trích xuất\"}\n***\nTên File: INV_001.pdf - Dữ liệu OCR:\nHÓA ĐƠN GIÁ TRỊ GIA TĂNG\nSố: 000001\nNgày: 05/01/2026\nĐơn vị bán: CÔNG TY ABC\nCộng tiền hàng: 1.000.000\nTiền thuế GTGT: 100.000\nTổng cộng tiền thanh toán: 1.100.000 VND",
            "answer": "{\"sections\":[{\"master\":{\"SectionOrder\":1,\"SectionType\":\"INVOICE\",\"SectionTitle\":\"Hóa đơn giá trị gia tăng\",\"TotalAmount\":1100000,\"TotalCurrency\":\"VND\",\"Signature\":\"VALID\"},\"details\":[{\"OrderNo\":\"1\",\"VoucherNo\":\"000001\",\"VoucherDate\":\"05/01/2026\",\"Amount\":1100000,\"Currency\":\"VND\",\"SupplierName\":\"CÔNG TY ABC\",\"DeliveryTerm\":null}]}]}"
        },
        {
            "stt": "2",
            "prompt sys": extraction_system,
            "prompt user": "***\n{\"PromptType\":\"Trích xuất\"}\n***\nTên File: VAT_002.pdf - Dữ liệu OCR:\nHóa đơn VAT\nSố hóa đơn: 000002\nNgày hóa đơn: 12/02/2026\nNhà cung cấp: CÔNG TY TNHH DEF\nThành tiền: 2.500.000\nVAT 8%: 200.000\nTổng tiền thanh toán: 2.700.000 VND",
            "answer": "{\"sections\":[{\"master\":{\"SectionOrder\":1,\"SectionType\":\"INVOICE\",\"SectionTitle\":\"Hóa đơn VAT\",\"TotalAmount\":2700000,\"TotalCurrency\":\"VND\",\"Signature\":\"VALID\"},\"details\":[{\"OrderNo\":\"1\",\"VoucherNo\":\"000002\",\"VoucherDate\":\"12/02/2026\",\"Amount\":2700000,\"Currency\":\"VND\",\"SupplierName\":\"CÔNG TY TNHH DEF\",\"DeliveryTerm\":null}]}]}"
        },
        {
            "stt": "3",
            "prompt sys": extraction_system,
            "prompt user": "***\n{\"PromptType\":\"Trích xuất\"}\n***\nTên File: CommercialInvoice_SK26.pdf - Dữ liệu OCR:\nCOMMERCIAL INVOICE\nInvoice No: SKS2603-02HH\nInvoice Date: 13/03/2026\nSeller: SHENZHEN TECHNOLOGY TRUST PRECISION INDUSTRY CO., LTD\nTrade term: FOB\nCurrency: USD\nTotal Amount: 25,700.00 USD",
            "answer": "{\"sections\":[{\"master\":{\"SectionOrder\":1,\"SectionType\":\"COMMERCIALINVOICE\",\"SectionTitle\":\"Commercial Invoice\",\"TotalAmount\":25700,\"TotalCurrency\":\"USD\",\"Signature\":\"VALID\"},\"details\":[{\"OrderNo\":\"1\",\"VoucherNo\":\"SKS2603-02HH\",\"VoucherDate\":\"13/03/2026\",\"Amount\":25700,\"Currency\":\"USD\",\"SupplierName\":\"SHENZHEN TECHNOLOGY TRUST PRECISION INDUSTRY CO., LTD\",\"DeliveryTerm\":\"FOB\"}]}]}"
        },
        {
            "stt": "4",
            "prompt sys": extraction_system,
            "prompt user": "***\n{\"PromptType\":\"Trích xuất\"}\n***\nTên File: PO_VG49.pdf - Dữ liệu OCR:\nPURCHASE ORDER\nPO No: VG49-26010022\nOrder Date: 20/01/2026\nSupplier: PROCESS LAB MICRON VIET NAM\nPayment Term: AMS 30 DAYS BY T/T\nAmount: 512,400 USD\nCurrency: USD",
            "answer": "{\"sections\":[{\"master\":{\"SectionOrder\":1,\"SectionType\":\"PO\",\"SectionTitle\":\"Purchase Order\",\"TotalAmount\":512400,\"TotalCurrency\":\"USD\",\"Signature\":\"VALID\"},\"details\":[{\"OrderNo\":\"1\",\"ContractNo\":\"VG49-26010022\",\"OrderDate\":\"20/01/2026\",\"RingiNo\":null,\"PaymentTerm\":\"AMS30\",\"DeliveryTerm\":null,\"Amount\":512400,\"Currency\":\"USD\",\"SupplierName\":\"PROCESS LAB MICRON VIET NAM\"}]}]}"
        },
        {
            "stt": "5",
            "prompt sys": extraction_system,
            "prompt user": "***\n{\"PromptType\":\"Trích xuất\"}\n***\nTên File: Customs_107962095252.xlsx - Dữ liệu OCR:\nTờ khai hàng hóa nhập khẩu (thông quan)\nSố tờ khai: 107962095252\nSố hóa đơn: A - TTST-202601220001\nNgày phát hành: 22/01/2026\nTổng trị giá hóa đơn: A - FOB - USD - 257000\nNgày hoàn thành kiểm tra: 05/02/2026",
            "answer": "{\"sections\":[{\"master\":{\"SectionOrder\":1,\"SectionType\":\"CUSTOMSHEET\",\"SectionTitle\":\"Tờ khai hàng hóa nhập khẩu (thông quan)\",\"TotalAmount\":257000,\"TotalCurrency\":\"USD\",\"Signature\":\"VALID\"},\"details\":[{\"OrderNo\":\"1\",\"ClearanceStatus\":\"YES\",\"DeclarationNo\":\"107962095252\",\"SupplierName\":null,\"VoucherNo\":\"TTST-202601220001\",\"VoucherDate\":\"22/01/2026\",\"DeliveryTerm\":\"FOB\",\"Amount\":257000,\"Currency\":\"USD\",\"Description\":null,\"ClearanceDate\":\"05/02/2026\"}]}]}"
        },
        {
            "stt": "6",
            "prompt sys": compare_system,
            "prompt user": "***\n{\"PromptType\":\"Đối chiếu\",\"DnttType\":\"Nguyên vật liệu\",\"FormationID\":\"Kế thừa công nợ\",\"CriterionName\":\"Số hóa đơn\"}\n***\n1. Dữ liệu đề nghị thanh toán (ĐNTT):\n{ Số hóa đơn: TTST-202601220001 }\n\n2. Dữ liệu đầu vào:\n{ Loại chứng từ: INVOICE | Số hóa đơn: TTST-202601220001 | Tên file: INV.pdf }",
            "answer": "{\"criteria\":{\"CriteriaName\":\"Số hóa đơn\",\"CriteriaStatus\":\"OK\",\"FileName\":\"\",\"Description\":\"Số hóa đơn đã hoàn toàn phù hợp.\"}}"
        },
        {
            "stt": "7",
            "prompt sys": compare_system,
            "prompt user": "***\n{\"PromptType\":\"Đối chiếu\",\"DnttType\":\"Nguyên vật liệu\",\"FormationID\":\"Kế thừa công nợ\",\"CriterionName\":\"Tên nhà cung cấp\"}\n***\n1. Dữ liệu đề nghị thanh toán (ĐNTT):\n{ Tên nhà cung cấp: CÔNG TY ABC }\n\n2. Dữ liệu đầu vào:\n{ Loại chứng từ: INVOICE | Tên nhà cung cấp: CÔNG TY XYZ | Tên file: invoice.pdf }",
            "answer": "{\"criteria\":{\"CriteriaName\":\"Tên nhà cung cấp\",\"CriteriaStatus\":\"NG\",\"FileName\":\"invoice.pdf\",\"Description\":\"Tên nhà cung cấp trên chứng từ không khớp với ĐNTT.\"}}"
        },
        {
            "stt": "8",
            "prompt sys": compare_system,
            "prompt user": "***\n{\"PromptType\":\"Đối chiếu\",\"DnttType\":\"Máy móc\",\"FormationID\":\"Chi phí\",\"CriterionName\":\"Loại tiền\"}\n***\n1. Dữ liệu đề nghị thanh toán (ĐNTT):\n{ Loại tiền: USD }\n\n2. Dữ liệu đầu vào:\n{ Loại chứng từ: PO | Loại tiền: USD | Tên file: PO.pdf }\n{ Loại chứng từ: CUSTOMSHEET | Loại tiền: USD | Tên file: CUS.xlsx }",
            "answer": "{\"criteria\":{\"CriteriaName\":\"Loại tiền\",\"CriteriaStatus\":\"OK\",\"FileName\":\"\",\"Description\":\"Loại tiền đã hoàn toàn phù hợp.\"}}"
        },
        {
            "stt": "9",
            "prompt sys": compare_system,
            "prompt user": "***\n{\"PromptType\":\"Đối chiếu\",\"DnttType\":\"Nguyên vật liệu\",\"FormationID\":\"Kế thừa công nợ\",\"CriterionName\":\"Hạn thanh toán\",\"Deadline\":\"30/06/2026\"}\n***\n1. Dữ liệu đề nghị thanh toán (ĐNTT):\n{ Hạn thanh toán: 30/06/2026 }\n\n2. Dữ liệu đầu vào:\n{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: 02/06/2026 | Tên file: CUS.xlsx }\n{ Loại chứng từ: PO | Hạn thanh toán: AMS30 | Tên file: PO.pdf }",
            "answer": "{\"DueDate\":\"02/07/2026\",\"FileName\":\"CUS.xlsx, PO.pdf\",\"Description\":\"Hạn chuẩn được tính từ ngày hoàn thành kiểm tra cộng 30 ngày.\"}"
        },
        {
            "stt": "10",
            "prompt sys": compare_system,
            "prompt user": "***\n{\"PromptType\":\"Đối chiếu\",\"DnttType\":\"Dịch vụ\",\"FormationID\":\"Chi phí\",\"CriterionName\":\"Chữ ký con dấu\"}\n***\n2. Dữ liệu đầu vào:\n{ Loại chứng từ: INVOICE | Chữ ký con dấu: VALID | Tên file: invoice.pdf }",
            "answer": "{\"criteria\":{\"CriteriaName\":\"Chữ ký con dấu\",\"CriteriaStatus\":\"OK\",\"FileName\":\"\",\"Description\":\"Chữ ký con dấu đã hoàn toàn phù hợp.\"}}"
        },
        {
            "stt": "11",
            "prompt sys": extraction_system,
            "prompt user": "***\n{\"PromptType\":\"Trích xuất\"}\n***\nTên File: Statement_2026.pdf - Dữ liệu OCR:\nBẢNG KÊ CÔNG NỢ\nSố bảng kê: ST-2026-01\nNgày: 31/01/2026\nNhà cung cấp: CÔNG TY ABC\nTổng tiền phải trả: 8.000.000 VND",
            "answer": "{\"sections\":[{\"master\":{\"SectionOrder\":1,\"SectionType\":\"STATEMENT\",\"SectionTitle\":\"Bảng kê công nợ\",\"TotalAmount\":8000000,\"TotalCurrency\":\"VND\",\"Signature\":\"VALID\"},\"details\":[{\"OrderNo\":\"1\",\"VoucherNo\":\"ST-2026-01\",\"VoucherDate\":\"31/01/2026\",\"Amount\":8000000,\"Currency\":\"VND\",\"SupplierName\":\"CÔNG TY ABC\"}]}]}"
        },
        {
            "stt": "12",
            "prompt sys": compare_system,
            "prompt user": "***\n{\"PromptType\":\"Đối chiếu\",\"DnttType\":\"Nguyên vật liệu\",\"FormationID\":\"Kế thừa công nợ\",\"CriterionName\":\"Số tiền\"}\n***\n1. Dữ liệu đề nghị thanh toán (ĐNTT):\n{ Số tiền: 1.100.000 VND }\n\n2. Dữ liệu đầu vào:\n{ Loại chứng từ: INVOICE | Số tiền: 1.100.000 | Loại tiền: VND | Tên file: INV_001.pdf }",
            "answer": "{\"criteria\":{\"CriteriaName\":\"Số tiền\",\"CriteriaStatus\":\"OK\",\"FileName\":\"\",\"Description\":\"Số tiền đã hoàn toàn phù hợp.\"}}"
        },
    ]



def _column_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _write_training_xlsx(xlsx_path: Path, rows: list[dict[str, str]]) -> None:
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["stt", "prompt sys", "prompt user", "answer"]
    all_rows = [headers]
    for row in rows:
        all_rows.append([str(row.get(header, "") or "") for header in headers])

    sheet_rows: list[str] = []
    for row_idx, values in enumerate(all_rows, start=1):
        cells: list[str] = []
        for col_idx, value in enumerate(values, start=1):
            ref = f"{_column_name(col_idx)}{row_idx}"
            escaped = html.escape(str(value or ""), quote=False)
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetData>' + ''.join(sheet_rows) + '</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="train" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )

    with zipfile.ZipFile(xlsx_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet)


def _read_existing_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists() or csv_path.stat().st_size <= 0:
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _ensure_training_xlsx(xlsx_path: Path) -> None:
    if xlsx_path.exists() and xlsx_path.stat().st_size > 0:
        return
    legacy_csv = xlsx_path.with_suffix(".csv")
    rows = _read_existing_csv_rows(legacy_csv)
    if not rows:
        rows = _sample_rows()
    _write_training_xlsx(xlsx_path, rows)


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        parts = [node.text or "" for node in cell.findall(".//m:t", ns)]
        return "".join(parts)
    value_node = cell.find("m:v", ns)
    value = "" if value_node is None else str(value_node.text or "")
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except Exception:
            return ""
    return value


def _cell_col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in str(cell_ref or "") if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return max(index, 1)


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out: list[str] = []
    for si in root.findall("m:si", ns):
        out.append("".join(node.text or "" for node in si.findall(".//m:t", ns)))
    return out


def _read_training_xlsx(xlsx_path: Path) -> list[dict[str, str]]:
    _ensure_training_xlsx(xlsx_path)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(xlsx_path, "r") as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in zf.namelist():
            raise ValueError(f"XLSX missing worksheet: {sheet_name}")
        root = ET.fromstring(zf.read(sheet_name))

    table: list[list[str]] = []
    for row in root.findall(".//m:sheetData/m:row", ns):
        values: dict[int, str] = {}
        max_col = 0
        for cell in row.findall("m:c", ns):
            col_idx = _cell_col_index(cell.attrib.get("r", ""))
            values[col_idx] = _cell_text(cell, shared_strings)
            max_col = max(max_col, col_idx)
        if max_col:
            table.append([values.get(idx, "") for idx in range(1, max_col + 1)])

    if not table:
        raise ValueError(f"XLSX file has no rows: {xlsx_path}")
    headers = [str(v or "").strip().lower() for v in table[0]]
    required = {"stt", "prompt sys", "prompt user", "answer"}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError(f"XLSX missing required column(s): {', '.join(missing)}")

    rows: list[dict[str, str]] = []
    for raw_values in table[1:]:
        row = {headers[idx]: (raw_values[idx] if idx < len(raw_values) else "") for idx in range(len(headers))}
        rows.append(row)
    return rows


def _xlsx_value(row: dict, *names: str) -> str:
    normalized = {str(k or "").strip().lower(): v for k, v in (row or {}).items()}
    for name in names:
        key = str(name or "").strip().lower()
        if key in normalized:
            return str(normalized.get(key) or "").strip()
    return ""


def _convert_xlsx_to_train_jsonl(xlsx_path: Path, jsonl_path: Path) -> int:
    rows = _read_training_xlsx(xlsx_path)
    rows_written = 0
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as dst:
        for line_no, row in enumerate(rows, start=2):
            system_prompt = _xlsx_value(row, "prompt sys")
            user_prompt = _xlsx_value(row, "prompt user")
            answer = _xlsx_value(row, "answer")
            if not system_prompt and not user_prompt and not answer:
                continue
            if not system_prompt or not user_prompt or not answer:
                stt = _xlsx_value(row, "stt") or str(line_no)
                raise ValueError(f"XLSX row stt={stt} is missing prompt sys, prompt user, or answer")
            item = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": answer},
                ]
            }
            dst.write(json.dumps(item, ensure_ascii=False))
            dst.write("\n")
            rows_written += 1

    if rows_written <= 0:
        raise ValueError(f"XLSX has no usable training rows: {xlsx_path}")
    return rows_written

def _validate_train_jsonl(path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Training data not found: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"Training data is empty: {path}")

    count = 0
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item: Any = json.loads(raw)
            except Exception as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Each JSONL row must be an object at {path}:{line_no}")
            messages = item.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError(f"Missing non-empty messages list at {path}:{line_no}")
            roles = {str(m.get("role", "")).lower() for m in messages if isinstance(m, dict)}
            if not {"system", "user", "assistant"}.issubset(roles):
                raise ValueError(f"messages must include system, user, assistant roles at {path}:{line_no}")
            count += 1

    if count <= 0:
        raise ValueError(f"Training data has no usable samples: {path}")
    return count


def _configure_environment(project_root: Path, settings_all) -> None:
    cache_root = project_root / "Cache"
    temp_dir = cache_root / "temp"
    models_root = project_root / "Models"
    cache_root.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    models_root.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("PADDLEX_HOME", str(cache_root))
    os.environ.setdefault("PADDLE_HOME", str(cache_root))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    os.environ.setdefault("TMP", str(temp_dir))
    os.environ.setdefault("TEMP", str(temp_dir))
    os.environ.setdefault("HOME", str(cache_root))
    os.environ.setdefault("USERPROFILE", str(cache_root))
    os.environ.setdefault("HF_HOME", str(models_root))
    os.environ.setdefault("HF_HUB_CACHE", str(models_root / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.environ["HF_HUB_CACHE"])

    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
    os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
    os.environ.setdefault("TORCH_DISABLE_TORCHINDUCTOR", "1")
    os.environ.setdefault("TORCHINDUCTOR_DISABLE", "1")
    if os.name == "nt":
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128,garbage_collection_threshold:0.8")
    else:
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    if getattr(settings_all, "LLM_HF_TOKEN", None):
        os.environ.setdefault("HF_TOKEN", str(settings_all.LLM_HF_TOKEN))

    gpu_index = 0 if getattr(settings_all, "REQUIRE_CUDA_GPU0", False) else int(getattr(settings_all, "GPU_INDEX", 0))
    os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", str(gpu_index))


def _cuda_cleanup() -> None:
    try:
        import gc

        gc.collect()
    except Exception:
        pass
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def main() -> int:
    project_root = _project_root()
    _load_dotenv(project_root / ".env")

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from App.settings_all import get_settings_all
    from App.LLMs_BE.registry import ModelRegistry

    settings_all = get_settings_all()
    project_root = Path(settings_all.PROJECT_ROOT).resolve()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    _configure_environment(project_root, settings_all)

    args = _parse_args()
    if args.epochs <= 0:
        raise ValueError("--epochs must be > 0")

    data_dir = (project_root / "App" / "LLMs_Train" / "data").resolve()
    xlsx_path = data_dir / "train.xlsx"
    data_path = data_dir / "train.jsonl"
    converted_count = _convert_xlsx_to_train_jsonl(xlsx_path, data_path)

    sample_count = converted_count
    if not args.skip_validate:
        sample_count = _validate_train_jsonl(data_path)

    special_id = str(settings_all.SPECIAL_MODEL_ID or "").strip()
    if not special_id:
        raise ValueError("SPECIAL_MODEL_ID is not configured")

    yaml_path = Path(settings_all.LLM_MODELS_YAML_PATH or "App/LLMs_BE/models.yaml")
    yaml_path = yaml_path if yaml_path.is_absolute() else (project_root / yaml_path).resolve()
    local_models_dir = Path(settings_all.LLM_LOCAL_MODELS_DIR or "Models")
    local_models_dir = local_models_dir if local_models_dir.is_absolute() else (project_root / local_models_dir).resolve()

    registry = ModelRegistry(str(yaml_path), local_models_dir=str(local_models_dir))
    if not registry.has(special_id):
        raise ValueError(f"SPECIAL_MODEL_ID not found in registry: {special_id}")

    model_cfg = registry.get(special_id)
    base_dir = registry.resolve_local_path(special_id) or None
    new_model_name = str(args.new_model_name or "").strip()
    if not new_model_name:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_model_name = f"{special_id}_lora_{ts}"

    print("=== RUN TRAIN ===", flush=True)
    print(f"Project root   : {project_root}", flush=True)
    print(f"XLSX source     : {xlsx_path}", flush=True)
    print(f"Train JSONL    : {data_path}", flush=True)
    print(f"Samples        : {sample_count}", flush=True)
    print(f"Model ID       : {special_id}", flush=True)
    print(f"Model name     : {model_cfg.get('name') or special_id}", flush=True)
    print(f"Base dir       : {base_dir or '(auto resolve in train_lora)'}", flush=True)
    print(f"New LoRA name  : {new_model_name}", flush=True)
    print(f"Old LoRA name  : {args.old_model_name or '(none)'}", flush=True)
    print(f"Epochs         : {args.epochs}", flush=True)

    # Import train module only after env/cache/CUDA settings are prepared.
    from App.LLMs_Train.train import train_lora, _train_log

    _train_log(
        "run_train.py begin old_model_name=%s new_model_name=%s num_epochs=%s model_id=%s xlsx_path=%s",
        args.old_model_name,
        new_model_name,
        args.epochs,
        special_id,
        str(xlsx_path),
    )

    started = time.time()
    try:
        _cuda_cleanup()
        result = train_lora(
            num_epochs=int(args.epochs),
            lora_name=new_model_name,
            old_lora_name=str(args.old_model_name or "").strip(),
            model_id=special_id,
            model_cfg=model_cfg,
            base_dir=base_dir,
        )
        elapsed = time.time() - started
        print("=== TRAIN SUCCESS ===", flush=True)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        print(f"Elapsed seconds: {elapsed:.2f}", flush=True)
        return 0
    except Exception as exc:
        print("=== TRAIN FAILED ===", flush=True)
        print(str(exc), flush=True)
        return 1
    finally:
        _cuda_cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
