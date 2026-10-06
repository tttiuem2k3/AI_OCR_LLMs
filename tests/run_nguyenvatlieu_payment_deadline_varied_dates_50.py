from datetime import datetime, timedelta
from calendar import monthrange
from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from App.Rules_AI_BEM_MEIKO import (
    _build_nguyenvatlieu_payment_deadline_source,
    _build_payment_deadline_result,
)

HOLIDAYS = ROOT / "App" / "Data_Holidays"
PUBLIC_HOLIDAYS = [(datetime(2026,1,1), datetime(2026,1,1)), (datetime(2026,4,30), datetime(2026,5,4)), (datetime(2026,9,2), datetime(2026,9,3))]


def month_end(dt):
    return datetime(dt.year, dt.month, monthrange(dt.year, dt.month)[1])


def oracle_raw(anchor, days):
    if days % 30 == 0:
        offset = days // 30
        total = anchor.year * 12 + anchor.month - 1 + offset
        year, month0 = divmod(total, 12)
        return datetime(year, month0 + 1, monthrange(year, month0 + 1)[1])
    return month_end(anchor + timedelta(days=days))

def oracle_workday(dt):
    cur = dt
    while True:
        holiday = any(start <= cur <= end for start, end in PUBLIC_HOLIDAYS)
        if cur.weekday() < 5 and not holiday:
            return cur
        cur -= timedelta(days=1)


def po(term, filename):
    return f"{{ Loai chung tu: PO | PaymentTerm: {term} | Ten file: {filename} }}"


def cus(date, filename):
    return f"{{ Loai chung tu: CUSTOMSHEET | Ngay hang den: {date} | Ten file: {filename} }}"


def inv(date, filename, kind="INVOICE"):
    return f"{{ Loai chung tu: {kind} | Ngay hoa don: {date} | Ten file: {filename} }}"


CASES = [
    ("AMS30", "02/08/2026", "CUS"), ("AMS30", "05/08/2026", "CUS"),
    ("AMS30", "08/08/2026", "CUS"), ("AMS30", "12/08/2026", "CUS"),
    ("AMS30", "18/08/2026", "CUS"), ("AMS30", "23/08/2026", "CUS"),
    ("AMS30", "28/08/2026", "CUS"), ("AMS30", "30/08/2026", "CUS"),
    ("AMS30", "31/08/2026", "CUS"), ("AMS60", "03/07/2026", "CUS"),
    ("AMS60", "07/07/2026", "CUS"), ("AMS60", "11/07/2026", "CUS"),
    ("AMS60", "16/07/2026", "CUS"), ("AMS60", "21/07/2026", "CUS"),
    ("AMS60", "25/07/2026", "CUS"), ("AMS60", "29/07/2026", "CUS"),
    ("AMS90", "04/06/2026", "CUS"), ("AMS90", "09/06/2026", "CUS"),
    ("AMS90", "14/06/2026", "CUS"), ("AMS90", "19/06/2026", "CUS"),
    ("AMS90", "24/06/2026", "CUS"), ("AMS90", "29/06/2026", "CUS"),
    ("AMS15", "05/03/2026", "CUS"), ("AMS15", "12/03/2026", "CUS"),
    ("AMS15", "17/03/2026", "CUS"), ("AMS15", "22/03/2026", "CUS"),
    ("AMS15", "25/03/2026", "CUS"), ("AMS15", "28/03/2026", "CUS"),
    ("AMS45", "05/01/2026", "CUS"), ("AMS45", "10/01/2026", "CUS"),
    ("AMS45", "15/01/2026", "CUS"), ("AMS45", "20/01/2026", "CUS"),
    ("AMS45", "25/01/2026", "CUS"), ("AMS45", "30/01/2026", "CUS"),
    ("AMS75", "04/06/2026", "CUS"), ("AMS75", "08/06/2026", "CUS"),
    ("AMS75", "13/06/2026", "CUS"), ("AMS75", "18/06/2026", "CUS"),
    ("AMS75", "23/06/2026", "CUS"), ("AMS75", "28/06/2026", "CUS"),
    ("30 AFTER B/L", "06/08/2026", "INV"), ("30 AFTER B/L", "14/08/2026", "INV"),
    ("30 AFTER B/L", "22/08/2026", "INV"), ("60 AFTER B/L", "09/07/2026", "INV"),
    ("60 AFTER B/L", "19/07/2026", "INV"), ("45 AFTER B/L", "07/01/2026", "INV"),
    ("45 AFTER B/L", "18/01/2026", "INV"), ("45 AFTER B/L", "27/01/2026", "INV"),
    ("30 AFTER B/L", "26/09/2026", "INV"), ("30 AFTER B/L", "30/09/2026", "INV"),
]

assert len(CASES) == 50


def extract_days(term):
    return int(re.findall(r"\d+", term)[0])


def main():
    failures = []
    for idx, (term, anchor_text, source_type) in enumerate(CASES, start=1):
        anchor = datetime.strptime(anchor_text, "%d/%m/%Y")
        raw_expected = oracle_raw(anchor, extract_days(term))
        due_expected = oracle_workday(raw_expected)
        should_pass = idx % 2 == 1
        deadline = due_expected if should_pass else due_expected - timedelta(days=1)
        anchor_file = f"ANCHOR_{idx:02d}.pdf" if source_type == "INV" else f"ANCHOR_{idx:02d}.xlsx"
        docs = [po(term, f"PO_{idx:02d}.pdf")]
        if source_type == "CUS":
            docs.append(cus(anchor_text, anchor_file))
        else:
            docs.append(inv(anchor_text, anchor_file))

        source = _build_nguyenvatlieu_payment_deadline_source("\n".join(docs))
        result = _build_payment_deadline_result(
            prompt_info={"Deadline": deadline.strftime("%d/%m/%Y")},
            parsed_llm=source,
            raw_llm_text="",
            criterion_name="Han thanh toan",
            data_holidays_dir=str(HOLIDAYS),
        )
        criteria = result["criteria"]
        expected_status = "OK" if should_pass else "NG"
        expected_file = "" if should_pass else anchor_file
        errors = []
        if source.get("DueDate") != raw_expected.strftime("%d/%m/%Y"):
            errors.append("raw DueDate")
        if criteria.get("DueDateAI") != due_expected.strftime("%d/%m/%Y"):
            errors.append("DueDateAI")
        if criteria.get("CriteriaStatus") != expected_status:
            errors.append("CriteriaStatus")
        if criteria.get("FileName") != expected_file:
            errors.append("FileName")

        if errors:
            failures.append((idx, term, anchor_text, errors, source, criteria))
            print(f"[FAIL] {idx:02d} term={term} anchor={anchor_text} errors={','.join(errors)}")
        else:
            print(
                f"[PASS] {idx:02d} term={term:<14} anchor={anchor_text} "
                f"raw={source.get('DueDate')} dueAI={criteria.get('DueDateAI')} "
                f"deadline={deadline.strftime('%d/%m/%Y')} status={criteria.get('CriteriaStatus')}"
            )

    print("=" * 110)
    print(f"TOTAL={len(CASES)} PASS={len(CASES)-len(failures)} FAIL={len(failures)}")
    if failures:
        for item in failures:
            idx, term, anchor_text, errors, source, criteria = item
            print(f"FAIL_DETAIL {idx:02d}: term={term} anchor={anchor_text} errors={errors}")
            print(f"  source={source}")
            print(f"  criteria={criteria}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
