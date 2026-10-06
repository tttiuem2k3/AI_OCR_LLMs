import json, re
from pathlib import Path
from collections import defaultdict

audit_dir=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Temp\DATA_BEM_NVL_Audit_20261002")
source=audit_dir/"mapping_dataset_payload_20261002.json"
out=audit_dir/"current_db_mapping_payload_20261002.json"
data=json.loads(source.read_text(encoding="utf-8"))
sheets={s["name"]:s["rows"] for s in data["sheets"]}

def norm(value):
    return re.sub(r"\s+"," ",str(value or "")).strip().lower()

def split_names(value):
    parts=re.split(r"\s*\|\s*|\r?\n",str(value or ""))
    return [p.strip() for p in parts if p.strip()]

section_by_file=defaultdict(list)
for row in sheets["04_DB_Section_Mapping"]:
    for name in split_names(row.get("Tên file")):
        section_by_file[(row.get("VoucherNo"),norm(name))].append(row)

coverage=[]
summary_counts=defaultdict(lambda:[0,0])
for row in sheets["03_Files_DinhKem"]:
    key=(row.get("VoucherNo"),norm(row.get("AttachName")))
    matched=section_by_file.get(key,[])
    section_types=sorted({str(x.get("SectionType") or "") for x in matched if x.get("SectionType")})
    section_apks=sorted({str(x.get("SectionAPK") or "") for x in matched if x.get("SectionAPK")})
    status="Có tên file trong dữ liệu trích xuất DB" if matched else "Chưa thấy tên file trong dữ liệu trích xuất DB"
    summary_counts[row.get("VoucherNo")][0 if matched else 1]+=1
    coverage.append({
        "VoucherNo":row.get("VoucherNo"),
        "AttachID":row.get("AttachID"),
        "AttachName":row.get("AttachName"),
        "DocRole_ByName":row.get("DocRole_ByName"),
        "DB_SectionCount":len(matched),
        "DB_SectionTypes":" | ".join(section_types),
        "DB_SectionAPKs":" | ".join(section_apks),
        "DB_MappingStatus":status,
        "CurrentMappingLevel":"File đang gắn với phiếu ĐNTT; dữ liệu trích xuất gắn với lần chạy AI/section. DB chưa map trực tiếp file vào từng dòng BEMT2001.",
    })

relations=[
    {"STT":1,"ThanhPhanTu":"BEMT2000 - Phiếu ĐNTT","LienKetHienTai":"BEMT2000.APK = BEMT2001.APKMaster","ThanhPhanDen":"BEMT2001 - Dòng ĐNTT","DuLieuDangMap":"Invoice, PO/Contract, Ringi, số tiền, loại tiền theo từng dòng","CapMapping":"Phiếu → Dòng ĐNTT","GioiHanHienTai":"Dòng ĐNTT chưa có khóa trực tiếp tới AttachID/file đính kèm."},
    {"STT":2,"ThanhPhanTu":"BEMT2000 - Phiếu ĐNTT","LienKetHienTai":"CONVERT(varchar(36),BEMT2000.APK) = CRMT00002_REL.RelatedToID","ThanhPhanDen":"CRMT00002_REL → CRMT00002 - File đính kèm","DuLieuDangMap":"AttachID, AttachName, nội dung file, ngày tạo/sửa file","CapMapping":"Phiếu → File","GioiHanHienTai":"File được gắn ở cấp phiếu, chưa xác định file thuộc dòng ĐNTT nào."},
    {"STT":3,"ThanhPhanTu":"BEMT2000 - Phiếu ĐNTT","LienKetHienTai":"BEMT2003.APK_BEMT2000 = BEMT2000.APK","ThanhPhanDen":"BEMT2003 - Lần chạy AI","DuLieuDangMap":"Trạng thái xử lý, kết quả OK/NG, %, OCR text, AI text, lỗi","CapMapping":"Phiếu → Lần chạy AI","GioiHanHienTai":"Một phiếu có thể có nhiều lần chạy; cần xác định lần mới nhất khi đọc kết quả."},
    {"STT":4,"ThanhPhanTu":"BEMT2003 - Lần chạy AI","LienKetHienTai":"BEMT2005.APK_BEMT2003 = BEMT2003.APK","ThanhPhanDen":"BEMT2005 - Nhóm/loại chứng từ","DuLieuDangMap":"SectionType, thứ tự, tiêu đề, tổng tiền, loại tiền, chữ ký","CapMapping":"Lần chạy AI → Nhóm chứng từ","GioiHanHienTai":"Nhóm chứng từ phụ thuộc dữ liệu AI trích xuất của lần chạy tương ứng."},
    {"STT":5,"ThanhPhanTu":"BEMT2005 - Nhóm chứng từ","LienKetHienTai":"BEMT2006.APK_BEMT2005 = BEMT2005.APK","ThanhPhanDen":"BEMT2006 - Dữ liệu trích xuất","DuLieuDangMap":"Tên file và các field đã trích xuất như Invoice, PO, Ringi, số tiền, NCC","CapMapping":"Nhóm chứng từ → Field trích xuất","GioiHanHienTai":"Tên file nằm trong dữ liệu trích xuất; chưa có quan hệ DB trực tiếp từ BEMT2006 tới CRMT00002.AttachID."},
    {"STT":6,"ThanhPhanTu":"BEMT2003 - Lần chạy AI","LienKetHienTai":"BEMT2004.APK_BEMT2003 = BEMT2003.APK","ThanhPhanDen":"BEMT2004 - Kết quả tiêu chí","DuLieuDangMap":"Tiêu chí, OK/NG, diễn giải, tên file liên quan, deadline AI","CapMapping":"Lần chạy AI → Tiêu chí đối chiếu","GioiHanHienTai":"FileName là dữ liệu kết quả AI; không phải khóa ngoại trực tiếp tới AttachID."},
]

summary=[]
for row in sheets["00_Tong_quan"]:
    row=dict(row)
    yes,no=summary_counts[row.get("VoucherNo")]
    row["DB_FilesCoTenTrongDuLieuTrichXuat"]=yes
    row["DB_FilesChuaThayTenTrongDuLieuTrichXuat"]=no
    row["PhamViTaiLieu"]="Chỉ mô tả hiện trạng dữ liệu và quan hệ mapping đang có trong hệ thống/DB; không bao gồm phương án đề xuất."
    summary.append(row)

new_sheets=[
    {"name":"00_Tong_quan","rows":summary},
    {"name":"01_DNTT_Header_DB","rows":sheets["01_DNTT_Header_DB"]},
    {"name":"02_DNTT_Lines_DB","rows":sheets["02_DNTT_Lines_DB"]},
    {"name":"03_Files_DinhKem","rows":sheets["03_Files_DinhKem"]},
    {"name":"04_DB_Section_Mapping","rows":sheets["04_DB_Section_Mapping"]},
    {"name":"05_DB_Field_Long","rows":sheets["05_DB_Field_Long"]},
    {"name":"06_AI_Criteria_DB","rows":sheets["06_AI_Criteria_DB"]},
    {"name":"07_HienTrang_QuanHe_DB","rows":relations},
    {"name":"08_DB_File_Coverage","rows":coverage},
    {"name":"09_Raw_Run_Text","rows":sheets["11_Raw_Run_Text"]},
]
result={
    "workbookTitle":"Dữ liệu hiện trạng Mapping DNTT và file đính kèm - NVL",
    "createdAt":data.get("createdAt"),
    "scope":"Hiện trạng hệ thống và DB, không bao gồm mapping/kiến trúc đề xuất",
    "selectedVouchers":data.get("selectedVouchers",[]),
    "sheets":new_sheets,
}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"out":str(out),"sheets":[(x["name"],len(x["rows"])) for x in new_sheets],"coverage":dict(summary_counts)},ensure_ascii=False))
