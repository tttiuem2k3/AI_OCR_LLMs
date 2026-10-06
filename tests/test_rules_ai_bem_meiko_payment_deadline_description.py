import unittest
from pathlib import Path

from App.Rules_AI_BEM_MEIKO import (
    _build_nguyenvatlieu_payment_deadline_source,
    _build_payment_deadline_result,
)


HOLIDAYS_DIR = str(Path("App/Data_Holidays"))


def build_result(content: str, deadline: str) -> dict:
    source = _build_nguyenvatlieu_payment_deadline_source(content)
    return _build_payment_deadline_result(
        prompt_info={"Deadline": deadline},
        parsed_llm=source,
        raw_llm_text="",
        criterion_name="Hạn thanh toán",
        data_holidays_dir=HOLIDAYS_DIR,
    )["criteria"]


class PaymentDeadlineDescriptionTests(unittest.TestCase):
    def test_ams_failed_description_includes_payment_term_and_anchor(self):
        criteria = build_result(
            """
{ Loại chứng từ: PO | PaymentTerm: AMS30 | Tên file: PO.pdf }
{ Loại chứng từ: CUSTOMSHEET | Ngày hàng đến: 01/08/2026 | Tên file: CUS.xlsx }
""",
            "29/09/2026",
        )

        self.assertEqual(
            criteria["Description"],
            "Ngày hạn thanh toán trên ĐNTT là 29/09/2026. "
            "Ngày hạn thanh toán chuẩn được tính không hợp lệ: 30/09/2026. "
            "( Điều kiện thanh toán AMS30: CUS.xlsx - 01/08/2026)",
        )

    def test_ams_mixed_result_appends_passed_dates_only_when_present(self):
        criteria = build_result(
            """
{ Loại chứng từ: PO | PaymentTerm: AMS30 | Tên file: PO.pdf }
{ Loại chứng từ: CUSTOMSHEET | Ngày hàng đến: 01/07/2026 | Tên file: JUL.xlsx }
{ Loại chứng từ: CUSTOMSHEET | Ngày hàng đến: 01/08/2026 | Tên file: AUG.xlsx }
""",
            "15/09/2026",
        )

        self.assertEqual(
            criteria["Description"],
            "Ngày hạn thanh toán trên ĐNTT là 15/09/2026. "
            "Ngày hạn thanh toán chuẩn được tính không hợp lệ: 30/09/2026. "
            "( Điều kiện thanh toán AMS30: AUG.xlsx - 01/08/2026) "
            "Ngày hạn thanh toán chuẩn được tính hợp lệ: 31/08/2026.",
        )

    def test_after_bl_description_uses_invoice_date_as_anchor(self):
        criteria = build_result(
            """
{ Loại chứng từ: PO | PaymentTerm: 30 AFTER B/L | Tên file: PO.pdf }
{ Loại chứng từ: INVOICE | Ngày hóa đơn: 01/08/2026 | Tên file: INV.pdf }
""",
            "29/09/2026",
        )

        self.assertEqual(
            criteria["Description"],
            "Ngày hạn thanh toán trên ĐNTT là 29/09/2026. "
            "Ngày hạn thanh toán chuẩn được tính không hợp lệ: 30/09/2026. "
            "( Điều kiện thanh toán 30 AFTER B/L: INV.pdf - 01/08/2026)",
        )


if __name__ == "__main__":
    unittest.main()
