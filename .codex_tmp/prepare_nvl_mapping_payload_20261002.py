import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

ROOT = Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09")
WORK = ROOT / "Mapping_DNTT_Files_NVL_Work_20261002"
OUT = ROOT / "Mapping_DNTT_Files_NVL_20261002"
ATTACH_OUT = OUT / "Files_dinh_kem"
PAYLOAD_OUT = OUT / "mapping_dataset_payload_20261002.json"
AUDIT_OUT = OUT / "audit_mapping_dataset_20261002.json"
VOUCHERS = ["NVL/09/2026/0045", "NVL/09/2026/0082", "NVL/09/2026/0529"]

OUT.mkdir(parents=True, exist_ok=True)
ATTACH_OUT.mkdir(parents=True, exist_ok=True)

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def slug(voucher):
    return voucher.replace("/", "-")

def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def norm_key(text):
    return re.sub(r"[^A-Za-z0-9]", "", str(text or "")).upper()

def number_tokens(text):
    tokens = []
    for token in re.findall(r"\d+", str(text or "")):
        tokens.append(token)
        stripped = token.lstrip("0") or "0"
        if stripped != token:
            tokens.append(stripped)
    return sorted(set(tokens), key=lambda x: (-len(x), x))

def split_codes(text):
    return [x.strip() for x in re.split(r"[;,\n]+", str(text or "")) if x.strip()]

def money_float(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None

def safe_value(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:32000]
    return value

def clean_row(row):
    return {k: safe_value(v) for k, v in row.items()}

def classify_file(name):
    upper = name.upper()
    if upper.startswith("VAT"):
        return "VAT Invoice"
    if upper.startswith("IV") or "INVOICE" in upper:
        return "Commercial Invoice"
    if upper.startswith("COM"):
        return "Commercial Invoice"
    if upper.startswith("PL") or "PACK" in upper:
        return "Packing List"
    if upper.startswith("PO"):
        return "PO"
    if "RINGI" in upper:
        return "Ringi"
    if "TOKHAI" in upper or "TO_KHAI" in upper or "HQ" in upper:
        return "Tờ khai"
    if upper.startswith("CT") or "CONTRACT" in upper:
        return "Contract"
    if "INSPEC" in upper:
        return "Inspection"
    return "Khác"

def role_group(role):
    if role in {"VAT Invoice", "Commercial Invoice"}:
        return "Invoice/VAT"
    if role == "Packing List":
        return "Packing list"
    return role

def find_source_folder(voucher, headers, attachments):
    header = headers[voucher]
    candidates = []
    for kind in ("DNTT_FINAL", "DNTT_TEMP"):
        path = ROOT / "Attached" / kind / "2026" / "9" / str(header.get("CurrencyID") or "") / str(header.get("AdvanceUserID") or "") / slug(voucher)
        if path.exists():
            candidates.append(path)
    if not candidates:
        return None
    db_names = {str(x.get("AttachName") or "").lower() for x in attachments[voucher]}
    return max(candidates, key=lambda p: sum(1 for f in p.iterdir() if f.is_file() and f.name.lower() in db_names))

def page_count(path):
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf" and PdfReader:
            return len(PdfReader(str(path), strict=False).pages), "PDF pages"
        if suffix in (".xlsx", ".xlsm"):
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            return len(wb.worksheets), "Excel sheets"
        if suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
            return 1, "image file"
        return 1, "file"
    except Exception as exc:
        return "", f"count error: {exc!r}"

db = load_json(WORK / "db_mapping_3_nvl.json")["tables"]
raw = load_json(WORK / "db_raw_and_section_mapping.json")["tables"]
headers = {x["VoucherNo"]: clean_row(x) for x in db["headers"]}
lines = defaultdict(list)
criteria = defaultdict(list)
sections = defaultdict(list)
fields = defaultdict(list)
attachments = defaultdict(list)
section_fields_by_voucher = defaultdict(list)
for row in db["lines"]:
    lines[row["VoucherNo"]].append(clean_row(row))
for row in db["criteria"]:
    criteria[row["VoucherNo"]].append(clean_row(row))
for row in db["sections"]:
    sections[row["VoucherNo"]].append(clean_row(row))
for row in db["fields"]:
    fields[row["VoucherNo"]].append(clean_row(row))
for row in db["attachments"]:
    attachments[row["VoucherNo"]].append(clean_row(row))
for row in raw["section_fields"]:
    section_fields_by_voucher[row["VoucherNo"]].append(clean_row(row))

physical_rows = []
copied_summary = {}
for voucher in VOUCHERS:
    src = find_source_folder(voucher, headers, attachments)
    dest = ATTACH_OUT / slug(voucher)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    disk = {f.name.lower(): f for f in src.iterdir() if f.is_file()} if src else {}
    total_pages = 0
    missing = 0
    for idx, att in enumerate(attachments[voucher], 1):
        name = str(att.get("AttachName") or "")
        source = disk.get(name.lower())
        exists = source is not None
        if exists:
            target = dest / name
            shutil.copy2(source, target)
            pages, page_note = page_count(target)
            if isinstance(pages, int):
                total_pages += pages
        else:
            target = None
            pages, page_note = "", "missing physical file"
            missing += 1
        physical_rows.append({
            "VoucherNo": voucher,
            "FileOrder": idx,
            "AttachID": att.get("AttachID"),
            "AttachName": name,
            "DocRole_ByName": classify_file(name),
            "AttachCreateDate": att.get("AttachCreateDate"),
            "AttachModifyDate": att.get("AttachModifyDate"),
            "AttachBytes": att.get("AttachBytes"),
            "AttachHash": att.get("AttachHash"),
            "PhysicalFound": "Có" if exists else "Không",
            "PhysicalSourceFolder": str(src) if src else "",
            "CopiedPath": str(target) if target else "",
            "PageOrSheetCount": pages,
            "PageCountNote": page_note,
        })
    copied_summary[voucher] = {"source": str(src) if src else "", "dest": str(dest), "files": len(attachments[voucher]), "missing": missing, "pages": total_pages}

field_groups = defaultdict(dict)
section_meta = {}
for row in raw["section_fields"]:
    row = clean_row(row)
    key = (row["VoucherNo"], row["SectionAPK"], row["ExtractRowAPK"])
    section_meta[key] = {
        "VoucherNo": row["VoucherNo"],
        "SectionAPK": row["SectionAPK"],
        "SectionType": row["SectionType"],
        "SectionOrder": row["SectionOrder"],
        "SectionTitle": row["SectionTitle"],
        "TotalAmount": row["TotalAmount"],
        "TotalCurrency": row["TotalCurrency"],
        "Signature": row["Signature"],
        "ExtractRowAPK": row["ExtractRowAPK"],
        "ExtractRowNo": row["ExtractRowNo"],
        "ExtractDescription": row["ExtractDescription"],
    }
    display = row.get("DisplayName") or row.get("FieldID")
    value = norm(row.get("FieldValue"))
    if display and value:
        old = field_groups[key].get(display)
        if old:
            if value not in str(old).split(" | "):
                field_groups[key][display] = old + " | " + value
        else:
            field_groups[key][display] = value

compact_section_rows = []
for key, meta in section_meta.items():
    vals = field_groups[key]
    compact_section_rows.append({
        **meta,
        "Tên file": vals.get("Tên file", ""),
        "Số hóa đơn": vals.get("Số hóa đơn", ""),
        "Ngày hóa đơn": vals.get("Ngày hóa đơn", ""),
        "Số tiền": vals.get("Số tiền", ""),
        "Loại tiền": vals.get("Loại tiền", ""),
        "Tên nhà cung cấp": vals.get("Tên nhà cung cấp", ""),
        "Số PO/Contract": vals.get("Số PO/Contract", vals.get("Số hợp đồng", "")),
        "Số Ringi": vals.get("Số Ringi", ""),
        "Điều kiện giao hàng": vals.get("Điều kiện giao hàng", ""),
        "Điều kiện thanh toán": vals.get("Điều kiện thanh toán", ""),
    })

criteria_by_role = {
    "VAT Invoice": "Số/Ngày Invoice; Số tiền; Loại tiền; NCC",
    "Commercial Invoice": "Invoice; Số tiền; Loại tiền; NCC; Điều kiện giao hàng",
    "Packing List": "Invoice; Số kiện/hàng; thông tin giao hàng",
    "Tờ khai": "Invoice; Ngày tờ khai; Loại tiền; thông tin nhập khẩu",
    "PO": "PO/Contract; Số tiền; Loại tiền; điều kiện giao hàng/thanh toán",
    "Ringi": "Ringi; hạn mức; tỷ lệ/lần thanh toán",
    "Contract": "Hợp đồng; điều kiện giao hàng/thanh toán",
    "Inspection": "Ngày hoàn thành kiểm tra; xác nhận nghiệm thu",
    "Khác": "Cần phân loại nghiệp vụ trước khi dùng đối chiếu",
}

manual_rows = []
manual_link_rows = []
for voucher in VOUCHERS:
    sec_rows = [r for r in compact_section_rows if r["VoucherNo"] == voucher]
    file_names = [r["AttachName"] for r in physical_rows if r["VoucherNo"] == voucher]
    attachment_by_name = {norm(row.get("AttachName")): row for row in attachments[voucher]}
    for line in lines[voucher]:
        invoice = norm(line.get("InvoiceNo"))
        inv_tokens = number_tokens(invoice)
        po_codes = split_codes(line.get("ContractNo"))
        ringi_codes = split_codes(line.get("RingiNo"))
        amount = money_float(line.get("RequestAmount"))
        currency = norm(line.get("CurrencyID"))
        matched_files = set()
        evidence = []
        roles = defaultdict(list)
        file_match_keys = defaultdict(list)
        file_evidence = defaultdict(list)

        for name in file_names:
            key = norm_key(name)
            role = classify_file(name)
            if invoice and any(token and token in key for token in inv_tokens):
                matched_files.add(name)
                roles[role_group(role)].append(name)
                evidence.append(f"Tên file khớp Invoice {invoice}: {name}")
                file_match_keys[name].append(f"InvoiceNo={invoice}")
                file_evidence[name].append(f"Tên file chứa số Invoice {invoice}")
            for po in po_codes:
                if norm_key(po) and norm_key(po) in key:
                    matched_files.add(name)
                    roles[role_group(role)].append(name)
                    evidence.append(f"Tên file khớp PO {po}: {name}")
                    file_match_keys[name].append(f"PO/Contract={po}")
                    file_evidence[name].append(f"Tên file chứa PO/Contract {po}")
            for ringi in ringi_codes:
                if norm_key(ringi) and norm_key(ringi) in key:
                    matched_files.add(name)
                    roles[role_group(role)].append(name)
                    evidence.append(f"Tên file khớp Ringi {ringi}: {name}")
                    file_match_keys[name].append(f"RingiNo={ringi}")
                    file_evidence[name].append(f"Tên file chứa Ringi {ringi}")

        for sec in sec_rows:
            fname = norm(sec.get("Tên file"))
            if not fname:
                continue
            role = classify_file(fname)
            sec_inv = norm(sec.get("Số hóa đơn"))
            sec_po = norm(sec.get("Số PO/Contract"))
            sec_ringi = norm(sec.get("Số Ringi"))
            sec_amount = money_float(sec.get("Số tiền")) or money_float(sec.get("TotalAmount"))
            sec_currency = norm(sec.get("Loại tiền") or sec.get("TotalCurrency"))
            matched = False
            if invoice and sec_inv and (norm_key(invoice) in norm_key(sec_inv) or norm_key(sec_inv) in norm_key(invoice) or any(token in norm_key(sec_inv) for token in inv_tokens)):
                matched = True
                evidence.append(f"DB extracted Invoice {sec_inv} từ file {fname}")
                file_match_keys[fname].append(f"InvoiceNo={invoice}")
                file_evidence[fname].append(f"DB trích xuất Invoice {sec_inv}")
            if any(norm_key(po) and norm_key(po) in norm_key(sec_po) for po in po_codes):
                matched = True
                evidence.append(f"DB extracted PO {sec_po} từ file {fname}")
                file_match_keys[fname].append(f"PO/Contract={sec_po}")
                file_evidence[fname].append(f"DB trích xuất PO/Contract {sec_po}")
            if any(norm_key(ringi) and norm_key(ringi) in norm_key(sec_ringi) for ringi in ringi_codes):
                matched = True
                evidence.append(f"DB extracted Ringi {sec_ringi} từ file {fname}")
                file_match_keys[fname].append(f"RingiNo={sec_ringi}")
                file_evidence[fname].append(f"DB trích xuất Ringi {sec_ringi}")
            if amount is not None and sec_amount is not None and currency and currency == sec_currency and abs(amount - sec_amount) < 0.01:
                matched = True
                evidence.append(f"DB extracted amount {sec_amount:g} {sec_currency} khớp dòng ĐNTT từ file {fname}")
                file_match_keys[fname].append(f"Amount={sec_amount:g} {sec_currency}")
                file_evidence[fname].append(f"DB trích xuất số tiền khớp {sec_amount:g} {sec_currency}")
            if matched:
                matched_files.add(fname)
                roles[role_group(role)].append(fname)

        doc_group_id = f"{slug(voucher)}__LINE_{line.get('OrderNo')}__INV_{invoice or 'NA'}"
        manual_rows.append({
            "VoucherNo": voucher,
            "DNTT_LineNo": line.get("OrderNo"),
            "DNTT_InvoiceNo": invoice,
            "DNTT_InvoiceDate": line.get("InvoiceDate"),
            "DNTT_PO_Contract": norm(line.get("ContractNo")),
            "DNTT_RingiNo": norm(line.get("RingiNo")),
            "DNTT_Amount": line.get("RequestAmount"),
            "DNTT_Currency": currency,
            "DocumentGroupID_Target": doc_group_id,
            "ManualTargetMapping": "Dòng ĐNTT cần được map tới nhóm chứng từ có cùng Invoice/PO/Ringi/số tiền để AI không phải dò toàn bộ file.",
            "MatchedFiles_All": "\n".join(sorted(matched_files)),
            "Matched_Invoice_VAT": "\n".join(sorted(set(roles.get("Invoice/VAT", [])))),
            "Matched_CommercialInvoice": "\n".join(sorted(set(roles.get("Commercial Invoice", [])))),
            "Matched_PackingList": "\n".join(sorted(set(roles.get("Packing list", [])))),
            "Matched_Customs": "\n".join(sorted(set(roles.get("Tờ khai", [])))),
            "Matched_PO": "\n".join(sorted(set(roles.get("PO", [])))),
            "Matched_Ringi": "\n".join(sorted(set(roles.get("Ringi", [])))),
            "Matched_Contract_Inspection": "\n".join(sorted(set(roles.get("Contract", []) + roles.get("Inspection", [])))),
            "MappingEvidence": "\n".join(dict.fromkeys(evidence)),
            "MappingGap_NeedForAI": "Cần lưu sẵn PaymentLineID + DocumentGroupID + AttachID + DocRole + MatchKey + MappingConfidence + CriteriaScope.",
        })
        for fname in sorted(matched_files):
            role = classify_file(fname)
            match_keys = list(dict.fromkeys(file_match_keys[fname]))
            strong_key = any(key.startswith(("InvoiceNo=", "PO/Contract=", "RingiNo=")) for key in match_keys)
            attach = attachment_by_name.get(fname, {})
            manual_link_rows.append({
                "VoucherNo": voucher,
                "DNTT_LineNo": line.get("OrderNo"),
                "PaymentLineID_Target": f"{voucher}#Line{line.get('OrderNo')}",
                "DocumentGroupID_Target": doc_group_id,
                "AttachID": attach.get("AttachID"),
                "AttachName": fname,
                "DocRole_Target": role,
                "MatchKeys_Target": " | ".join(match_keys),
                "MappingConfidence": "Cao" if strong_key else "Trung bình - cần kiểm tra",
                "CriteriaScope_Target": criteria_by_role.get(role, criteria_by_role["Khác"]),
                "MappingEvidence": " | ".join(dict.fromkeys(file_evidence[fname])),
                "MappingSource": "Đề xuất mapping thủ công từ dòng ĐNTT + tên file + dữ liệu DB đã trích xuất",
            })

link_count_by_file = defaultdict(int)
for row in manual_link_rows:
    link_count_by_file[(row["VoucherNo"], row["AttachName"])] += 1
file_coverage_rows = []
for row in physical_rows:
    count = link_count_by_file[(row["VoucherNo"], row["AttachName"])]
    file_coverage_rows.append({
        "VoucherNo": row["VoucherNo"],
        "AttachID": row["AttachID"],
        "AttachName": row["AttachName"],
        "DocRole_ByName": row["DocRole_ByName"],
        "MappedLineCount_Target": count,
        "CoverageStatus": "Đã map tới dòng ĐNTT" if count else "Chưa map chắc chắn - cần AI/người dùng phân loại thêm",
        "Note": "File dùng chung nhiều dòng" if count > 1 else ("File chưa đủ khóa nối Invoice/PO/Ringi/số tiền" if count == 0 else "File đã map 1 dòng"),
    })

target_schema_rows = [
    {"Field": "PaymentVoucherID", "Meaning": "APK/Số ĐNTT", "WhyNeeded": "Khóa gốc để gom toàn bộ file và kết quả AI của một phiếu."},
    {"Field": "PaymentLineID", "Meaning": "Dòng ĐNTT/OrderNo", "WhyNeeded": "Một phiếu NVL có thể có nhiều Invoice/PO; cần map theo từng dòng."},
    {"Field": "DocumentGroupID", "Meaning": "Nhóm chứng từ của một lần thanh toán", "WhyNeeded": "Gom Invoice/VAT/PO/Ringi/tờ khai/PL theo cùng nghiệp vụ."},
    {"Field": "AttachID + AttachName", "Meaning": "File vật lý trong ERP", "WhyNeeded": "Tránh AI đọc nhầm file cùng tên hoặc file ngoài nhóm."},
    {"Field": "DocRole", "Meaning": "Invoice, VAT, PO, Ringi, Customs, PackingList, Contract, Inspection", "WhyNeeded": "AI biết file dùng để kiểm tra tiêu chí nào."},
    {"Field": "MatchKey", "Meaning": "InvoiceNo, PO/ContractNo, RingiNo, Amount, Currency, Supplier, Date", "WhyNeeded": "Khóa nối ĐNTT với dữ liệu trích xuất từ từng file."},
    {"Field": "MappingConfidence", "Meaning": "Cao/Trung bình/Cần kiểm tra", "WhyNeeded": "Tách mapping chắc chắn khỏi mapping cần người xác nhận."},
    {"Field": "CriteriaScope", "Meaning": "Tiêu chí dùng file này: Số tiền, NCC, Invoice, PO/Ringi, Deadline, Incoterm", "WhyNeeded": "Giảm số file AI phải đọc lại khi check từng tiêu chí."},
]

summary_rows = []
for voucher in VOUCHERS:
    header = headers[voucher]
    summary = copied_summary[voucher]
    summary_rows.append({
        "VoucherNo": voucher,
        "NCC": header.get("AdvanceUserID"),
        "SupplierName": header.get("SupplierName"),
        "Currency": header.get("CurrencyID"),
        "DNTT_Lines": len(lines[voucher]),
        "AttachedFiles_DB": summary["files"],
        "PhysicalFilesCopied": summary["files"] - summary["missing"],
        "MissingPhysicalFiles": summary["missing"],
        "TotalPagesOrSheets": summary["pages"],
        "AI_Status": header.get("AIStatus"),
        "AI_Percentage": header.get("AIPercentage"),
        "ApprovingLevel": header.get("ApprovingLevel"),
        "AI_RunDate": header.get("RunCreateDate"),
        "WhySelected": "NVL, hơn 30 file hoặc hơn 30 trang/sheet, AI OK 100%, phù hợp phân tích mapping ĐNTT ↔ file.",
        "CopiedFolder": summary["dest"],
    })

run_rows = [clean_row({k: (str(v)[:32000] if isinstance(v, str) else v) for k, v in row.items()}) for row in raw["runs"]]
sheets = [
    {"name": "00_Tong_quan", "rows": summary_rows},
    {"name": "01_DNTT_Header_DB", "rows": list(headers.values())},
    {"name": "02_DNTT_Lines_DB", "rows": [row for voucher in VOUCHERS for row in lines[voucher]]},
    {"name": "03_Files_DinhKem", "rows": physical_rows},
    {"name": "04_DB_Section_Mapping", "rows": compact_section_rows},
    {"name": "05_DB_Field_Long", "rows": [clean_row(row) for row in raw["section_fields"]]},
    {"name": "06_AI_Criteria_DB", "rows": [row for voucher in VOUCHERS for row in criteria[voucher]]},
    {"name": "07_Target_Mapping_Line", "rows": manual_rows},
    {"name": "08_Target_File_Link", "rows": manual_link_rows},
    {"name": "09_Target_Schema_AI", "rows": target_schema_rows},
    {"name": "10_File_Coverage", "rows": file_coverage_rows},
    {"name": "11_Raw_Run_Text", "rows": run_rows},
]
payload = {
    "workbookTitle": "Bộ dữ liệu Mapping DNTT và file đính kèm - NVL",
    "createdAt": datetime.now().isoformat(timespec="seconds"),
    "selectedVouchers": VOUCHERS,
    "sheets": sheets,
}
PAYLOAD_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=safe_value), encoding="utf-8")
audit = {
    "createdAt": payload["createdAt"],
    "payload": str(PAYLOAD_OUT),
    "attachmentsFolder": str(ATTACH_OUT),
    "vouchers": VOUCHERS,
    "summary": summary_rows,
    "rowCounts": {sheet["name"]: len(sheet["rows"]) for sheet in sheets},
    "dbCounts": {
        "headers": len(headers),
        "lines": sum(len(lines[v]) for v in VOUCHERS),
        "criteria": sum(len(criteria[v]) for v in VOUCHERS),
        "sections": len(compact_section_rows),
        "fieldsLong": len(raw["section_fields"]),
        "attachments": len(physical_rows),
        "manualLineMapping": len(manual_rows),
        "manualFileLinks": len(manual_link_rows),
    },
}
AUDIT_OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=safe_value), encoding="utf-8")
print(json.dumps(audit, ensure_ascii=False, indent=2, default=safe_value))
