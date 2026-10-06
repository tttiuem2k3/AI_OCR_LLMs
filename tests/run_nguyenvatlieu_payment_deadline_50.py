from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from App.Rules_AI_BEM_MEIKO import (
    _build_nguyenvatlieu_payment_deadline_source,
    _build_payment_deadline_result,
)

HOLIDAYS = ROOT / "App" / "Data_Holidays"
CASES = []


def po(term, filename):
    return f"{{ Loai chung tu: PO | PaymentTerm: {term} | Ten file: {filename} }}"


def cus(date, filename):
    return f"{{ Loai chung tu: CUSTOMSHEET | Ngay hang den: {date} | Ten file: {filename} }}"


def inv(date, filename, kind="INVOICE"):
    return f"{{ Loai chung tu: {kind} | Ngay hoa don: {date} | Ten file: {filename} }}"

def add(name, docs, deadline, source_due, due_ai, status, filename="", desc_has=()):
    CASES.append({
        "name": name,
        "content": "\n".join(docs),
        "deadline": deadline,
        "source_due": source_due,
        "due_ai": due_ai,
        "status": status,
        "filename": filename,
        "desc_has": tuple(desc_has),
    })


# 01-15: AMS 30/60/90 theo thang lich + cuoi thang.
add("AMS30 Aug exact deadline", [po("AMS30", "P01.pdf"), cus("01/08/2026", "C01.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("AMS30 Aug deadline before", [po("AMS30", "P02.pdf"), cus("01/08/2026", "C02.xlsx")], "29/09/2026", "30/09/2026", "30/09/2026", "NG", "C02.xlsx", ("khong hop le",))
add("AMS30 mid Aug", [po("AMS 30 DAYS", "P03.pdf"), cus("15/08/2026", "C03.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("AMS30 end Aug still next month end", [po("AMS 30", "P04.pdf"), cus("31/08/2026", "C04.xlsx")], "29/09/2026", "30/09/2026", "30/09/2026", "NG", "C04.xlsx")
add("AMS60 Jul", [po("AMS60", "P05.pdf"), cus("01/07/2026", "C05.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("AMS60 mid Jul fail", [po("AMS 60 DAYS", "P06.pdf"), cus("20/07/2026", "C06.xlsx")], "29/09/2026", "30/09/2026", "30/09/2026", "NG", "C06.xlsx")
add("AMS90 Jun", [po("AMS90", "P07.pdf"), cus("01/06/2026", "C07.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("AMS90 end Jun fail", [po("AMS 90 days by TT", "P08.pdf"), cus("30/06/2026", "C08.xlsx")], "29/09/2026", "30/09/2026", "30/09/2026", "NG", "C08.xlsx")
add("AMS30 Sep weekend month end normalized", [po("AMS30", "P09.pdf"), cus("01/09/2026", "C09.xlsx")], "30/10/2026", "31/10/2026", "30/10/2026", "OK")
add("AMS30 Sep weekend fail", [po("AMS30", "P10.pdf"), cus("01/09/2026", "C10.xlsx")], "29/10/2026", "31/10/2026", "30/10/2026", "NG", "C10.xlsx")
add("AMS30 Apr Sunday month end", [po("AMS30", "P11.pdf"), cus("01/04/2026", "C11.xlsx")], "29/05/2026", "31/05/2026", "29/05/2026", "OK")
add("AMS30 Apr Sunday month end fail", [po("AMS30", "P12.pdf"), cus("01/04/2026", "C12.xlsx")], "28/05/2026", "31/05/2026", "29/05/2026", "NG", "C12.xlsx")
add("AMS30 Mar public holiday month end", [po("AMS30", "P13.pdf"), cus("01/03/2026", "C13.xlsx")], "29/04/2026", "30/04/2026", "29/04/2026", "OK")
add("AMS30 Mar holiday fail", [po("AMS30", "P14.pdf"), cus("01/03/2026", "C14.xlsx")], "28/04/2026", "30/04/2026", "29/04/2026", "NG", "C14.xlsx")
add("AMS30 Jan Saturday Feb end", [po("AMS30", "P15.pdf"), cus("01/01/2026", "C15.xlsx")], "27/02/2026", "28/02/2026", "27/02/2026", "OK")

# 16-20: ky han khong chia het cho 30, fallback cong ngay roi lay cuoi thang.
add("AMS15 Mar", [po("AMS15", "P16.pdf"), cus("01/03/2026", "C16.xlsx")], "31/03/2026", "31/03/2026", "31/03/2026", "OK")
add("AMS15 crosses Apr holiday", [po("AMS15", "P17.pdf"), cus("20/03/2026", "C17.xlsx")], "28/04/2026", "30/04/2026", "29/04/2026", "NG", "C17.xlsx")
add("AMS45 Jan to Feb weekend", [po("AMS45", "P18.pdf"), cus("01/01/2026", "C18.xlsx")], "27/02/2026", "28/02/2026", "27/02/2026", "OK")
add("AMS45 late Jan to Mar", [po("AMS45", "P19.pdf"), cus("20/01/2026", "C19.xlsx")], "30/03/2026", "31/03/2026", "31/03/2026", "NG", "C19.xlsx")
add("AMS75 Jun to Aug", [po("AMS75", "P20.pdf"), cus("01/06/2026", "C20.xlsx")], "31/08/2026", "31/08/2026", "31/08/2026", "OK")

# 21-26: nhieu ngay moc, trung DueDate, mapping FileName.
add("two anchors same due both fail files", [po("AMS30", "P21.pdf"), cus("01/08/2026", "C21A.xlsx"), cus("15/08/2026", "C21B.xlsx")], "29/09/2026", "30/09/2026", "30/09/2026", "NG", "C21A.xlsx, C21B.xlsx")
add("two anchors same due all pass filename blank", [po("AMS30", "P22.pdf"), cus("01/08/2026", "C22A.xlsx"), cus("15/08/2026", "C22B.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("mixed pass fail only failed file", [po("AMS30", "P23.pdf"), cus("01/08/2026", "C23A.xlsx"), cus("01/09/2026", "C23B.xlsx")], "15/10/2026", "30/09/2026, 31/10/2026", "30/09/2026, 30/10/2026", "NG", "C23B.xlsx", ("30/10/2026", "30/09/2026"))
add("two due dates both fail both files", [po("AMS30", "P24.pdf"), cus("01/08/2026", "C24A.xlsx"), cus("01/09/2026", "C24B.xlsx")], "29/09/2026", "30/09/2026, 31/10/2026", "30/09/2026, 30/10/2026", "NG", "C24A.xlsx, C24B.xlsx")
add("duplicate same anchor same file dedup", [po("AMS30", "P25.pdf"), cus("01/08/2026", "C25.xlsx"), cus("01/08/2026", "C25.xlsx")], "29/09/2026", "30/09/2026", "30/09/2026", "NG", "C25.xlsx")
add("same failed due multiple files plus valid due", [po("AMS30", "P26.pdf"), cus("01/08/2026", "C26A.xlsx"), cus("15/08/2026", "C26B.xlsx"), cus("01/07/2026", "C26C.xlsx")], "31/08/2026", "30/09/2026, 31/08/2026", "30/09/2026, 31/08/2026", "NG", "C26A.xlsx, C26B.xlsx")

# 27-32: AFTER B/L van dung cong thuc ky han -> cuoi thang.
add("AFTER BL30 invoice", [po("30 DAYS AFTER B/L", "P27.pdf"), inv("01/08/2026", "I27.pdf")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("AFTER BL30 commercial invoice fail", [po("30 AFTER B/L", "P28.pdf"), inv("15/08/2026", "CI28.pdf", "COMMERCIALINVOICE")], "29/09/2026", "30/09/2026", "30/09/2026", "NG", "CI28.pdf")
add("AFTER BL60 invoice", [po("60 AFTER B/L", "P29.pdf"), inv("01/07/2026", "I29.pdf")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("AFTER BL45 weekend Feb", [po("45 DAYS AFTER B/L", "P30.pdf"), inv("01/01/2026", "I30.pdf")], "27/02/2026", "28/02/2026", "27/02/2026", "OK")
add("AFTER BL mixed invoice types", [po("30 AFTER B/L", "P31.pdf"), inv("01/09/2026", "I31.pdf"), inv("01/08/2026", "CI31.pdf", "COMMERCIALINVOICE")], "15/10/2026", "31/10/2026, 30/09/2026", "30/10/2026, 30/09/2026", "NG", "I31.pdf", ("30/10/2026", "30/09/2026"))
add("AFTER BL two digit year", [po("30 days after B/L date", "P32.pdf"), inv("01/08/26", "I32.pdf")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")

# 33-38: chon PaymentTerm theo da so, hoa phieu va term khong hop le.
add("majority AMS30", [po("AMS30", "P33A.pdf"), po("AMS30", "P33B.pdf"), po("AMS60", "P33C.pdf"), cus("01/08/2026", "C33.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("majority AFTER BL30", [po("30 AFTER B/L", "P34A.pdf"), po("30 AFTER B/L", "P34B.pdf"), po("AMS30", "P34C.pdf"), inv("01/08/2026", "I34.pdf")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("tie AMS30 AMS60", [po("AMS30", "P35A.pdf"), po("AMS60", "P35B.pdf"), cus("01/08/2026", "C35.xlsx")], "30/09/2026", None, None, "NG", "P35A.pdf, P35B.pdf", ("nhieu dieu khoan thanh toan",))
add("ignore CASH select AMS60", [po("CASH", "P36A.pdf"), po("AMS60", "P36B.pdf"), cus("01/07/2026", "C36.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")
add("all invalid payment terms", [po("CASH", "P37A.pdf"), po("NET 30", "P37B.pdf")], "30/09/2026", None, None, "NG", "", ("khong tim thay dieu khoan thanh toan",))
add("conflicting invalid term ignored", [po("AMS 30 AFTER B/L", "P38A.pdf"), po("AMS30", "P38B.pdf"), cus("01/08/2026", "C38.xlsx")], "30/09/2026", "30/09/2026", "30/09/2026", "OK")

# 39-42: thieu hoac sai ngay moc.
add("AMS missing CUSTOMSHEET", [po("AMS30", "P39.pdf")], "30/09/2026", None, None, "NG", "", ("ngay hang den",))
add("AMS null arrival date", [po("AMS30", "P40.pdf"), cus("null", "C40.xlsx")], "30/09/2026", None, None, "NG", "", ("ngay hang den",))
add("AMS invalid arrival date", [po("AMS30", "P41.pdf"), cus("31/02/2026", "C41.xlsx")], "30/09/2026", None, None, "NG", "", ("ngay hang den",))
add("AFTER BL invalid invoice date", [po("30 AFTER B/L", "P42.pdf"), inv("31/02/2026", "I42.pdf"), cus("01/08/2026", "ignored.xlsx")], "30/09/2026", None, None, "NG", "", ("ngay hoa don",))

# 43-46: cac moc cuoi thang dac biet cua lich nghi 2026.
add("Jan31 Saturday normalize Jan30", [po("AMS30", "P43.pdf"), cus("01/12/2025", "C43.xlsx")], "30/01/2026", "31/01/2026", "30/01/2026", "OK")
add("Feb28 Saturday fail before normalized date", [po("AMS30", "P44.pdf"), cus("01/01/2026", "C44.xlsx")], "26/02/2026", "28/02/2026", "27/02/2026", "NG", "C44.xlsx")
add("Apr30 holiday normalize Apr29", [po("AMS30", "P45.pdf"), cus("01/03/2026", "C45.xlsx")], "29/04/2026", "30/04/2026", "29/04/2026", "OK")
add("May31 Sunday normalize May29", [po("AMS30", "P46.pdf"), cus("01/04/2026", "C46.xlsx")], "29/05/2026", "31/05/2026", "29/05/2026", "OK")

# 47-50: deadline edge cases va mo ta valid/invalid.
add("missing deadline means all fail", [po("AMS30", "P47.pdf"), cus("01/08/2026", "C47.xlsx")], None, "30/09/2026", "30/09/2026", "NG", "C47.xlsx")
add("deadline ISO format accepted", [po("AMS30", "P48.pdf"), cus("01/08/2026", "C48.xlsx")], "2026-09-30", "30/09/2026", "30/09/2026", "OK")
add("multiple all valid filename blank", [po("AMS30", "P49.pdf"), cus("01/07/2026", "C49A.xlsx"), cus("01/08/2026", "C49B.xlsx"), cus("01/09/2026", "C49C.xlsx")], "30/10/2026", "31/08/2026, 30/09/2026, 31/10/2026", "31/08/2026, 30/09/2026, 30/10/2026", "OK")
add("three due dates only last invalid", [po("AMS30", "P50.pdf"), cus("01/07/2026", "C50A.xlsx"), cus("01/08/2026", "C50B.xlsx"), cus("01/09/2026", "C50C.xlsx")], "15/10/2026", "31/08/2026, 30/09/2026, 31/10/2026", "31/08/2026, 30/09/2026, 30/10/2026", "NG", "C50C.xlsx", ("30/10/2026", "31/08/2026", "30/09/2026"))

assert len(CASES) == 50, f"Expected 50 cases, got {len(CASES)}"


def plain(value):
    import unicodedata
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower()


def execute_case(index, case):
    source = _build_nguyenvatlieu_payment_deadline_source(case["content"])
    result = _build_payment_deadline_result(
        prompt_info={"Deadline": case["deadline"]},
        parsed_llm=source,
        raw_llm_text="",
        criterion_name="Han thanh toan",
        data_holidays_dir=str(HOLIDAYS),
    )
    criteria = result["criteria"]
    errors = []
    if source.get("DueDate") != case["source_due"]:
        errors.append(f"source DueDate expected={case['source_due']!r} actual={source.get('DueDate')!r}")
    if criteria.get("DueDateAI") != case["due_ai"]:
        errors.append(f"DueDateAI expected={case['due_ai']!r} actual={criteria.get('DueDateAI')!r}")
    if criteria.get("CriteriaStatus") != case["status"]:
        errors.append(f"status expected={case['status']} actual={criteria.get('CriteriaStatus')}")
    if criteria.get("FileName") != case["filename"]:
        errors.append(f"FileName expected={case['filename']!r} actual={criteria.get('FileName')!r}")
    description_plain = plain(criteria.get("Description"))
    for token in case["desc_has"]:
        if plain(token) not in description_plain:
            errors.append(f"Description missing token={token!r}: {criteria.get('Description')!r}")
    return source, result, errors


def main():
    failures = []
    for index, case in enumerate(CASES, start=1):
        source, result, errors = execute_case(index, case)
        if errors:
            failures.append((index, case, source, result, errors))
            print(f"[FAIL] {index:02d} {case['name']}")
            for error in errors:
                print(f"       - {plain(error)}")
        else:
            criteria = result["criteria"]
            print(
                f"[PASS] {index:02d} {case['name']} | "
                f"raw={source.get('DueDate')} | normalized={criteria.get('DueDateAI')} | "
                f"status={criteria.get('CriteriaStatus')} | files={criteria.get('FileName') or '-'}"
            )

    print("=" * 100)
    print(f"TOTAL={len(CASES)} PASS={len(CASES) - len(failures)} FAIL={len(failures)}")
    if failures:
        print("FAILED_CASES=" + ",".join(str(item[0]) for item in failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
