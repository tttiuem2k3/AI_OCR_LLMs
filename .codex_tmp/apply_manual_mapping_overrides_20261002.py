import json
from collections import defaultdict
from pathlib import Path

OUT = Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Mapping_DNTT_Files_NVL_20261002")
payload_path = OUT / "mapping_dataset_payload_20261002.json"
audit_path = OUT / "audit_mapping_dataset_20261002.json"
payload = json.loads(payload_path.read_text(encoding="utf-8"))
sheets = {sheet["name"]: sheet["rows"] for sheet in payload["sheets"]}
line_rows = sheets["07_Target_Mapping_Line"]
link_rows = sheets["08_Target_File_Link"]
file_rows = sheets["03_Files_DinhKem"]
coverage_rows = sheets["10_File_Coverage"]

file_by_key = {(row["VoucherNo"], row["AttachName"]): row for row in file_rows}
line_by_key = {(row["VoucherNo"], str(row["DNTT_LineNo"])): row for row in line_rows}
for row in link_rows:
    row["LinkScope"] = "Dòng ĐNTT"

def doc_group(voucher, line_no, invoice):
    return f"{voucher.replace('/', '-')}__LINE_{line_no}__INV_{invoice or 'NA'}"

def append_multiline(row, key, text):
    old = str(row.get(key) or "")
    values = [item.strip() for item in old.split("\n") if item.strip()]
    if text not in values:
        values.append(text)
        row[key] = "\n".join(values)

def add_link(voucher, line_no, group_id, file_name, role, keys, confidence, scope, evidence, source, link_scope):
    file_row = file_by_key[(voucher, file_name)]
    payment_line = f"{voucher}#Line{line_no}" if str(line_no).isdigit() else ("VOUCHER_COMMON" if line_no == "Dùng chung" else "OUTSIDE_PAYMENT_SCOPE")
    row = {
        "VoucherNo": voucher,
        "DNTT_LineNo": line_no,
        "PaymentLineID_Target": payment_line,
        "DocumentGroupID_Target": group_id,
        "AttachID": file_row.get("AttachID"),
        "AttachName": file_name,
        "DocRole_Target": role,
        "MatchKeys_Target": keys,
        "MappingConfidence": confidence,
        "CriteriaScope_Target": scope,
        "MappingEvidence": evidence,
        "MappingSource": source,
        "LinkScope": link_scope,
    }
    if not any(all(existing.get(k) == row.get(k) for k in ["VoucherNo", "DNTT_LineNo", "AttachName", "DocumentGroupID_Target"]) for existing in link_rows):
        link_rows.append(row)

def add_special_line(voucher, line_no, group_id, file_name, note, evidence, gap):
    line_rows.append({
        "VoucherNo": voucher,
        "DNTT_LineNo": line_no,
        "DNTT_InvoiceNo": "",
        "DNTT_InvoiceDate": "",
        "DNTT_PO_Contract": "",
        "DNTT_RingiNo": "",
        "DNTT_Amount": "",
        "DNTT_Currency": "",
        "DocumentGroupID_Target": group_id,
        "ManualTargetMapping": note,
        "MatchedFiles_All": file_name,
        "Matched_Invoice_VAT": "",
        "Matched_CommercialInvoice": file_name if line_no == "Dùng chung" else "",
        "Matched_PackingList": file_name if line_no == "Dùng chung" else "",
        "Matched_Customs": "",
        "Matched_PO": file_name if "PO_" in file_name else "",
        "Matched_Ringi": "",
        "Matched_Contract_Inspection": "",
        "MappingEvidence": evidence,
        "MappingGap_NeedForAI": gap,
    })

# NVL/09/2026/0082: Ringi filename stores only the final number, while the DNTT stores VNNK-1304-xxxxx.
voucher = "NVL/09/2026/0082"
for line_no, ringi_file, ringi_number in [("5", "Ringi_40479.pdf", "40479"), ("6", "Ringi_40498.pdf", "40498")]:
    target = line_by_key[(voucher, line_no)]
    add_link(voucher, line_no, target["DocumentGroupID_Target"], ringi_file, "Ringi", f"RingiNo suffix={ringi_number}", "Cao", "Ringi; hạn mức; tỷ lệ/lần thanh toán", f"DNTT Ringi {target['DNTT_RingiNo']} có hậu tố {ringi_number}; DB trích xuất Số Ringi {ringi_number}.", "Mapping thủ công: đối chiếu hậu tố Ringi", "Dòng ĐNTT")
    append_multiline(target, "Matched_Ringi", ringi_file)
    append_multiline(target, "MatchedFiles_All", ringi_file)
    append_multiline(target, "MappingEvidence", f"Tên Ringi rút gọn {ringi_number} khớp DNTT {target['DNTT_RingiNo']}.")

# A commercial invoice/packing list covers the overall shipment, not an individual payment line.
common_group = "NVL-09-2026-0082__COMMON_SHIPMENT_20260619"
add_special_line(voucher, "Dùng chung", common_group, "IV-PL_20260619.pdf", "Chứng từ lô hàng dùng chung cho các dòng thanh toán có Invoice VAT 504; giữ ở cấp phiếu, không gán riêng một dòng.", "DB trích xuất Commercial Invoice 20260619-MEIKO VN, ngày 19/06/2026, tổng 4.733.207.000 VND, NCC Narasaki, điều kiện DDP.", "Cần có DocumentGroupID ở cấp phiếu để LLM dùng chứng từ chung mà không nhân bản vào từng dòng.")
add_link(voucher, "Dùng chung", common_group, "IV-PL_20260619.pdf", "Commercial Invoice + Packing List", "ShipmentDate=2026-06-19 | VoucherInvoiceVAT=504", "Cao", "NCC; điều kiện giao hàng; thông tin lô hàng", "DB trích xuất Invoice/Packing List lô 19/06/2026; tất cả 21 dòng DNTT cùng Invoice VAT 504.", "Mapping thủ công: chứng từ dùng chung cấp phiếu", "Chứng từ dùng chung cấp phiếu")

# The PO is attached but not listed in any current DNTT line. Keep it out of automated line conclusion.
outside_group = "NVL-09-2026-0082__OUTSIDE_PAYMENT_SCOPE"
add_special_line(voucher, "Ngoài phạm vi", outside_group, "PO_VB74-26050001.pdf", "PO có đính kèm nhưng không có ContractNo tương ứng trên 21 dòng ĐNTT hiện tại; chỉ giữ để người dùng/AI kiểm tra khi cần.", "DB trích xuất PO VB74-26050001; không tìm thấy số này trong ContractNo của các dòng ĐNTT phiếu 0082.", "AI không dùng chứng từ ngoài phạm vi để kết luận OK/NG cho dòng ĐNTT nếu chưa được người dùng gán lại.")
add_link(voucher, "Ngoài phạm vi", outside_group, "PO_VB74-26050001.pdf", "PO", "PO/Contract=VB74-26050001", "Cần xác nhận", "Không dùng để kết luận tự động cho dòng ĐNTT", "PO tồn tại trong file đính kèm nhưng không khớp ContractNo của dòng ĐNTT hiện hành.", "Mapping thủ công: file ngoài phạm vi dòng thanh toán", "Ngoài phạm vi dòng ĐNTT")

# NVL/09/2026/0529: Packing List files share their suffix with Commercial Invoice; the Commercial Invoice has date/amount that identifies a DNTT line.
voucher = "NVL/09/2026/0529"
pl_to_line = {
    "177": ("1", "330", "31247000", "07/07/2026"),
    "179": ("2", "336", "6410000", "09/07/2026"),
    "181": ("3", "339", "7540000", "10/07/2026"),
    "184": ("4", "345", "10280000", "13/07/2026"),
    "193": ("5", "363", "11720000", "amount only; CI date 21/07 vs VAT date 22/07"),
    "207": ("6", "387", "33200000", "29/07/2026"),
    "211": ("7", "395", "7120000", "30/07/2026"),
}
for suffix, (line_no, vat_invoice, amount, evidence_date) in pl_to_line.items():
    target = line_by_key[(voucher, line_no)]
    pl_file = f"PL_{suffix}.pdf"
    add_link(voucher, line_no, target["DocumentGroupID_Target"], pl_file, "Packing List", f"PairedCommercialInvoice={suffix} | Amount={amount} VND | VATInvoice={vat_invoice}", "Cao" if suffix != "193" else "Trung bình - cần kiểm tra ngày", "Thông tin hàng/đóng gói; đối chiếu Invoice và lô hàng", f"PL_{suffix} ghép cặp Com_{suffix}; DB trích xuất Commercial Invoice có số tiền {amount} VND, khớp dòng DNTT Invoice VAT {vat_invoice}; ngày {evidence_date}.", "Mapping thủ công: PL ghép cặp Commercial Invoice cùng số", "Dòng ĐNTT")
    append_multiline(target, "Matched_PackingList", pl_file)
    append_multiline(target, "MatchedFiles_All", pl_file)
    append_multiline(target, "MappingEvidence", f"{pl_file} ghép cặp Com_{suffix}; số tiền Commercial Invoice khớp dòng ĐNTT.")

# Inspection is relevant to the last line but ContractNo has a one-character difference and must remain reviewable.
target = line_by_key[(voucher, "8")]
inspection_file = "Inspec_VG69-260601C-FPC.pdf"
add_link(voucher, "8", target["DocumentGroupID_Target"], inspection_file, "Inspection", "PO/Contract close match: VG69-260601C-FPC ↔ VG69-2606101C FPC", "Trung bình - cần xác nhận", "Ngày hoàn thành kiểm tra; xác nhận nghiệm thu", "Tên Contract trên file và DNTT gần khớp nhưng khác ký tự: file VG69-260601C-FPC, DNTT VG69-2606101C FPC.", "Mapping thủ công: cần MEIKO xác nhận khóa Contract chuẩn", "Dòng ĐNTT")
append_multiline(target, "Matched_Contract_Inspection", inspection_file)
append_multiline(target, "MatchedFiles_All", inspection_file)
append_multiline(target, "MappingEvidence", "Inspection có Contract gần khớp với dòng 8; giữ mức cần xác nhận.")

# Rebuild coverage from all links, distinguishing direct evidence, common evidence and file outside payment scope.
links_by_file = defaultdict(list)
for row in link_rows:
    links_by_file[(row["VoucherNo"], row["AttachName"])].append(row)
for row in coverage_rows:
    links = links_by_file[(row["VoucherNo"], row["AttachName"])]
    direct = [link for link in links if link.get("LinkScope") == "Dòng ĐNTT"]
    common = [link for link in links if link.get("LinkScope") == "Chứng từ dùng chung cấp phiếu"]
    outside = [link for link in links if link.get("LinkScope") == "Ngoài phạm vi dòng ĐNTT"]
    row["MappedLineCount_Target"] = len({str(link.get("DNTT_LineNo")) for link in direct})
    if direct:
        row["CoverageStatus"] = "Đã map tới dòng ĐNTT"
        row["Note"] = "File dùng chung nhiều dòng" if len(direct) > 1 else "File đã map 1 dòng"
    elif common:
        row["CoverageStatus"] = "Chứng từ dùng chung toàn phiếu"
        row["Note"] = "Dùng ở cấp phiếu, không gán riêng một dòng ĐNTT"
    elif outside:
        row["CoverageStatus"] = "Ngoài phạm vi dòng ĐNTT"
        row["Note"] = "Không dùng để kết luận tự động khi chưa có dòng ĐNTT tương ứng"
    else:
        row["CoverageStatus"] = "Chưa map chắc chắn - cần AI/người dùng phân loại thêm"
        row["Note"] = "File chưa đủ khóa nối Invoice/PO/Ringi/số tiền"

payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
audit = json.loads(audit_path.read_text(encoding="utf-8"))
audit["rowCounts"]["07_Target_Mapping_Line"] = len(line_rows)
audit["rowCounts"]["08_Target_File_Link"] = len(link_rows)
audit["dbCounts"]["manualLineMapping"] = 38
audit["dbCounts"]["manualFileLinks"] = len(link_rows)
audit["manualCoverage"] = {
    "directLine": sum(1 for row in coverage_rows if row["CoverageStatus"] == "Đã map tới dòng ĐNTT"),
    "voucherCommon": sum(1 for row in coverage_rows if row["CoverageStatus"] == "Chứng từ dùng chung toàn phiếu"),
    "outsidePaymentScope": sum(1 for row in coverage_rows if row["CoverageStatus"] == "Ngoài phạm vi dòng ĐNTT"),
    "needsReview": sum(1 for row in coverage_rows if row["CoverageStatus"].startswith("Chưa map")),
}
audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(audit["manualCoverage"], ensure_ascii=False))
